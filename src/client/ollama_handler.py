import json
import logging
import ollama

# Import shared conversation history
try:
    from .conversation_state import conversation_history
except ImportError:
    # Fallback if run directly or structure changes
    conversation_history = []
    logging.warning("Could not import shared conversation_history from .conversation_state")


def get_ollama_response(connection_mgr, selected_ollama_model, user_input):
    """Handles interaction with Ollama, including tool calls (synchronous version)."""
    global conversation_history

    # Get available tools from all connected servers
    all_available_tools = connection_mgr.get_all_tools() # Returns {server_name: [tools]}

    # Format the tools description including server names
    tools_description = "\nAvailable Tools:\n"
    if not all_available_tools:
        tools_description += "No tools available from any connected server."
    else:
        for server_name, tools_list in all_available_tools.items():
            if tools_list:
                tools_description += f"\n--- Server: '{server_name}' ---\n"
                for tool in tools_list:
                    # Safely access attributes
                    tool_name = getattr(tool, 'name', 'Unknown Tool')
                    tool_desc = getattr(tool, 'description', 'No description')
                    input_schema = getattr(tool, 'inputSchema', {})
                    try:
                        schema_str = json.dumps(input_schema)
                    except TypeError:
                        schema_str = str(input_schema) # Fallback
                    tools_description += f"- {tool_name}: {tool_desc}\n  Input Schema: {schema_str}\n"
            else:
                 tools_description += f"\n--- Server: '{server_name}' (No tools reported) ---\n"


    # Update system prompt to require server name in TOOL_CALL, be more strict, and add an example
    system_prompt = f"""You are a helpful assistant connected to multiple MCP servers.
{tools_description}
When a user asks for an action that requires using one of the tools listed above, you MUST respond with **ONLY** the following JSON format on a single line, and nothing else:
TOOL_CALL: {{"server": "target_server_name", "name": "tool_name_to_use", "arguments": {{arg1: value1, arg2: value2,...}}}}

**IMPORTANT RULES:**
- Your response MUST start *exactly* with `TOOL_CALL: ` followed by the JSON object.
- The JSON object MUST contain the keys "server", "name", and "arguments".
- The "server" value must be the name of the server providing the tool (e.g., "filesystem", "github").
- The "name" value must be the exact name of the tool to use.
- The "arguments" value must be a JSON object containing the parameters required by the tool's Input Schema.
- If no tool is needed, or you cannot fulfill the request with the available tools, respond directly to the user in a conversational manner, without using the TOOL_CALL format.

**EXAMPLE:** If the user asks "Read the file /projects/my_file.txt using the filesystem server", your response should be exactly:
TOOL_CALL: {{"server": "filesystem", "name": "read_file", "arguments": {{"path": "/projects/my_file.txt"}}}}

Do not add any explanation before or after the TOOL_CALL line if you are calling a tool.
If you are not calling a tool, just respond naturally."""

    current_messages = conversation_history + [{"role": "user", "content": user_input}]
    messages_for_ollama = [m for m in current_messages if m['role'] != 'system']
    messages_for_ollama.insert(0, {'role': 'system', 'content': system_prompt})

    try:
        logging.info(f"Sending to Ollama model: {selected_ollama_model}")
        response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
        assistant_response_content = response['message']['content'].strip()
        logging.info(f"Received from Ollama: {assistant_response_content}")

        if assistant_response_content.startswith("TOOL_CALL:"):
            tool_call_json_str = assistant_response_content[len("TOOL_CALL:"):].strip()
            # --- Add Validation Step ---
            try:
                tool_call_data = json.loads(tool_call_json_str)
                # Validate structure
                if not isinstance(tool_call_data, dict):
                    raise ValueError("TOOL_CALL content is not a JSON object.")
                server_name = tool_call_data.get("server")
                tool_name = tool_call_data.get("name")
                tool_args = tool_call_data.get("arguments") # Get arguments, check type later
                if not server_name or not tool_name or tool_args is None:
                     raise ValueError("TOOL_CALL JSON missing required keys ('server', 'name', 'arguments').")
                if not isinstance(tool_args, dict):
                     # Allow empty args, but ensure it's a dict if present
                     if tool_args is not None: # Check if it exists but isn't a dict
                          raise ValueError("TOOL_CALL 'arguments' field must be a JSON object.")
                     tool_args = {} # Default to empty dict if arguments key exists but value is null/not dict

                # --- Validation Passed ---
                logging.info(f"Validated TOOL_CALL: Server='{server_name}', Name='{tool_name}'")

                # Proceed with tool call logic...
                # (tool_args is already extracted and validated above)

                logging.info(f"Calling MCP tool '{tool_name}' on server '{server_name}' with args: {tool_args}")
                tool_result = connection_mgr.call_tool(server_name, tool_name, tool_args)
                logging.info(f"Tool '{tool_name}' on server '{server_name}' result received")

                # Safely extract content from tool result
                tool_result_content = None
                # Check type explicitly first
                if tool_result is None:
                    tool_result_content = {"error": "No result returned from tool"}
                elif isinstance(tool_result, bool):
                    tool_result_content = {"success": tool_result}
                elif isinstance(tool_result, (str, int, float)):
                     tool_result_content = tool_result
                elif hasattr(tool_result, 'content'): # Check hasattr only if not simple type
                    # Normal case with content attribute
                    # Ensure content is serializable (e.g., handle bytes if necessary)
                    raw_content = tool_result.content
                    if isinstance(raw_content, bytes):
                        try:
                            tool_result_content = raw_content.decode('utf-8')
                        except UnicodeDecodeError:
                            tool_result_content = f"Binary content (length {len(raw_content)})"
                    else:
                         tool_result_content = raw_content
                # ADDED: Handle cases where result might be a simple string or number directly
                else:
                    # Fallback for other unexpected types
                    tool_result_content = {"result": str(tool_result)} # Convert unexpected types to string

                # Include server and tool name in the result context for the LLM
                tool_result_context_for_llm = {
                    "server": server_name,
                    "tool_name": tool_name,
                    "result": tool_result_content
                }
                tool_result_content_str = json.dumps(tool_result_context_for_llm)

                messages_for_ollama.append({'role': 'assistant', 'content': assistant_response_content})
                messages_for_ollama.append({'role': 'tool', 'content': tool_result_content_str})

                logging.info(f"Sending tool result to Ollama model: {selected_ollama_model}")
                final_response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
                final_text = final_response['message']['content']
                
                # Update global history
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': assistant_response_content})
                conversation_history.append({'role': 'tool', 'content': tool_result_content_str})
                conversation_history.append({'role': 'assistant', 'content': final_text})
                
                return final_text

            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Error parsing/validating TOOL_CALL: {e}")
                error_msg = f"Error: Could not parse tool call instruction from LLM: {e}"
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': error_msg})
                return error_msg # Return specific parse/validation error to user

            # --- Catch Validation Errors ---
            except (json.JSONDecodeError, ValueError) as validation_error:
                 logging.warning(f"Invalid TOOL_CALL format received from Ollama: {validation_error}. Raw: {assistant_response_content}")
                 # Treat as a normal text response instead of failing
                 conversation_history.append({"role": "user", "content": user_input})
                 conversation_history.append({"role": "assistant", "content": assistant_response_content}) # Return the raw (invalid) response
                 return assistant_response_content
            # --- End Validation Step ---

            # --- Original Tool Execution Exception Handling ---
            except Exception as e:
                # Include server name in error logging and message (This part handles errors *during* tool execution)
                called_server_name = tool_call_data.get("server", "unknown") if 'tool_call_data' in locals() else "unknown"
                called_tool_name = tool_call_data.get("name", "unknown") if 'tool_call_data' in locals() else "unknown"
                # Log the full error including traceback for debugging
                logging.exception(f"Error calling MCP tool '{called_tool_name}' on server '{called_server_name}'")
                # Create a concise, safe error message for the LLM history
                # Use only the exception type name to avoid complex/multi-line strings
                error_str = f"Error executing tool: {type(e).__name__}"
                error_message_for_llm = json.dumps({
                    "server": called_server_name,
                    "tool_name": called_tool_name,
                    "error": error_str # Use the concise error string
                })
                messages_for_ollama.append({'role': 'assistant', 'content': assistant_response_content})
                messages_for_ollama.append({'role': 'tool', 'content': error_message_for_llm}) # Add the clean JSON error string for the immediate follow-up

                error_response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
                final_text = error_response['message']['content']

                # Create the structured error dictionary for the global history
                structured_error_for_history = {
                    "server": called_server_name,
                    "tool_name": called_tool_name,
                    "error": error_str # Use the concise error string
                }

                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': assistant_response_content})
                # Add the STRUCTURED error to the global history, not the JSON string
                conversation_history.append({'role': 'tool', 'content': json.dumps(structured_error_for_history)})
                conversation_history.append({'role': 'assistant', 'content': final_text})
                
                return final_text
        else:
            # Simple text response without tool calls
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": assistant_response_content})
            return assistant_response_content

    except Exception as e:
        error_msg = f"Error communicating with Ollama: {e}"
        logging.error(error_msg)
        return error_msg
