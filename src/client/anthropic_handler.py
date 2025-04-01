import json
import logging
from anthropic import Anthropic

# Import shared conversation history
try:
    from .conversation_state import conversation_history
except ImportError:
    # Fallback if run directly or structure changes
    conversation_history = []
    logging.warning("Could not import shared conversation_history from .conversation_state")


def get_anthropic_response(connection_mgr, anthropic_client, anthropic_model, user_input):
    """Handles interaction with Anthropic, including tool calls (synchronous version)."""
    global conversation_history

    # Get available tools from all connected servers
    all_available_tools = connection_mgr.get_all_tools() # Returns {server_name: [tools]}

    # Format tools for Anthropic API, prepending server name to tool name
    anthropic_tools = []
    if all_available_tools:
        for server_name, tools_list in all_available_tools.items():
            if tools_list:
                for tool in tools_list:
                    # Safely access attributes
                    tool_name = getattr(tool, 'name', 'Unknown Tool')
                    tool_desc = getattr(tool, 'description', 'No description')
                    input_schema = getattr(tool, 'inputSchema', {})
                    # Prepend server name to tool name for uniqueness
                    anthropic_tools.append({
                        "name": f"{server_name}/{tool_name}", # Format: "server/tool"
                        "description": f"(Server: {server_name}) {tool_desc}", # Add server to description too
                        "input_schema": input_schema
                    })

    # Ensure messages have the correct format for Anthropic
    # Add user input to history temporarily for processing, but don't modify global history yet
    current_interaction_messages = conversation_history + [{"role": "user", "content": user_input}]
    messages_for_anthropic = []

    logging.debug(f"Processing history for Anthropic. Current length: {len(conversation_history)}")

    # More robust history processing and sanitization
    for i, msg in enumerate(current_interaction_messages):
        role = msg.get("role")
        content = msg.get("content")
        processed_message = None

        logging.debug(f"Processing message {i}: role={role}, type={type(content)}")

        if not role or content is None:
            logging.warning(f"Skipping message {i} due to missing role or content.")
            continue

        # --- Start of Corrected Indentation Block ---
        try: # Level 0 relative to loop start
            if role == "assistant": # Level 1
                if isinstance(content, list): # Level 2
                    processed_message = {"role": role, "content": content}
                elif isinstance(content, str): # Level 2
                    sanitized_content = content.splitlines()[0]
                    max_len = 1000
                    if len(sanitized_content) > max_len:
                        sanitized_content = sanitized_content[:max_len] + "..."
                    processed_message = {"role": role, "content": sanitized_content}
                else: # Level 2
                    logging.warning(f"Skipping assistant message {i} with unexpected content type: {type(content)}") # Level 3

            elif role == "user": # Level 1
                if isinstance(content, list): # Level 2
                    valid_blocks = []
                    malformed = False
                    try: # Level 3
                        for block in content: # Level 4
                            if isinstance(block, dict) and "type" in block: # Level 5
                                valid_blocks.append(block)
                            else: # Level 5
                                malformed = True
                                logging.warning(f"Malformed block in user message {i} content: {block}") # Level 6
                                break
                    except Exception as e: # Level 3
                        malformed = True
                        logging.warning(f"Error processing user message {i} content blocks: {e}") # Level 4

                    if not malformed: # Level 3
                        processed_message = {"role": "user", "content": valid_blocks}
                    else: # Level 3
                        processed_message = {"role": "user", "content": "[Malformed tool result content skipped]"}

                elif isinstance(content, str): # Level 2
                    sanitized_content = content.splitlines()[0]
                    max_len = 1000
                    if len(sanitized_content) > max_len:
                        sanitized_content = sanitized_content[:max_len] + "..."
                    processed_message = {"role": role, "content": sanitized_content}
                else: # Level 2
                    logging.warning(f"Skipping user message {i} with unexpected content type: {type(content)}") # Level 3

            elif role == "tool": # Level 1
                logging.debug(f"Converting 'tool' role message {i} for Anthropic.") # Level 2
                tool_use_id = "unknown_id"
                try: # Level 2
                    tool_data = json.loads(content)
                    result_blocks = []
                    if "error" in tool_data: # Level 3
                        error_text = f"Error executing tool {tool_data.get('tool_name', 'unknown')}: {tool_data['error']}"
                        result_blocks = [{"type": "text", "text": error_text[:500]}]
                    else: # Level 3
                        result_content = tool_data.get("result", "[No result found in tool message]")
                        if isinstance(result_content, list): # Level 4
                            result_blocks = result_content
                        else: # Level 4
                            result_blocks = [{"type": "text", "text": str(result_content)}]

                    processed_message = { # Level 3
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result_blocks}]
                    }
                except Exception as parse_error: # Level 2
                    logging.warning(f"Failed to parse 'tool' role content for message {i}: {parse_error}. Content: {content[:100]}...") # Level 3
                    processed_message = {"role": "user", "content": "[Unparseable tool result skipped]"} # Level 3

            else: # Level 1
                logging.warning(f"Skipping message {i} with unknown role: {role}") # Level 2

            if processed_message: # Level 1
                messages_for_anthropic.append(processed_message)
                logging.debug(f"Added processed message {i} for Anthropic: role={processed_message['role']}") # Level 2

        except Exception as outer_e: # Level 0 (aligned with the 'try')
            logging.exception(f"Unexpected error processing message {i} for Anthropic: {outer_e}") # Level 1
            # Skip this message entirely if unexpected error occurs during processing # Level 1
        # --- End of Corrected Indentation Block ---


    # Now messages_for_anthropic should contain only sanitized/valid messages
    if not messages_for_anthropic:
         logging.error("Failed to process any messages for Anthropic API call.")
         return "Error: Could not process conversation history for Anthropic."

    try:
        logging.info(f"Sending to Anthropic model: {anthropic_model}")
        response = anthropic_client.messages.create(
            model=anthropic_model,
            max_tokens=1024,
            messages=messages_for_anthropic,
            tools=anthropic_tools
        )

        assistant_response_content_blocks = response.content
        tool_calls_to_make = []
        text_response_parts = []

        for content_block in assistant_response_content_blocks:
            if content_block.type == 'text':
                text_response_parts.append(content_block.text)
            elif content_block.type == 'tool_use':
                tool_calls_to_make.append({
                    "id": content_block.id,
                    "name": content_block.name,
                    "input": content_block.input
                })

        # Update history with user input and initial assistant response
        # Ensure we only add valid content to the global history
        if isinstance(assistant_response_content_blocks, list):
             conversation_history.append({"role": "user", "content": user_input}) # Add user input first
             conversation_history.append({"role": "assistant", "content": assistant_response_content_blocks}) # Add valid assistant response
        else:
             logging.error("Anthropic initial response content was not a list of blocks.")
             # Decide how to handle this - maybe add a sanitized string version?
             # For now, just log the error and don't add the malformed response to history.
             # conversation_history.append({"role": "user", "content": user_input}) # Still add user input


        if not tool_calls_to_make:
            # Simple text response without tool calls
            return ''.join(text_response_parts)
        else:
            tool_results_for_anthropic = []
            # Use the sanitized messages list for the final call, NOT the global history directly
            messages_for_final_call = messages_for_anthropic.copy() # Start with the sanitized list

            for tool_call in tool_calls_to_make:
                # Parse server_name and actual_tool_name from the combined name
                combined_name = tool_call["name"]
                try:
                    server_name, actual_tool_name = combined_name.split('/', 1)
                except ValueError:
                    logging.error(f"Could not parse server/tool name from Anthropic response: '{combined_name}'")
                    # Handle error: maybe skip this tool call or return an error message
                    tool_results_for_anthropic.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call["id"],
                        "content": [{"type": "text", "text": f"Error: Invalid tool name format received '{combined_name}'"}],
                        "is_error": True
                    })
                    continue # Skip to next tool call

                tool_args = tool_call["input"]
                tool_use_id = tool_call["id"]
                logging.info(f"Calling MCP tool '{actual_tool_name}' on server '{server_name}' with args: {tool_args}")

                try:
                    # Call tool using parsed server and tool names
                    mcp_tool_result = connection_mgr.call_tool(server_name, actual_tool_name, tool_args)

                    # Safely extract content from tool result
                    result_content_blocks = [] # Anthropic expects a list of content blocks
                    if mcp_tool_result is None:
                        result_content_blocks = [{"type": "text", "text": "No result returned from tool"}]
                    elif isinstance(mcp_tool_result, bool):
                        result_content_blocks = [{"type": "text", "text": f"Operation {'succeeded' if mcp_tool_result else 'failed'}"}]
                    elif hasattr(mcp_tool_result, 'content'):
                        raw_content = mcp_tool_result.content
                        # Ensure content is a list of blocks or convert simple text
                        if isinstance(raw_content, list):
                             # Assume it's already in the correct block format if it's a list
                             # TODO: Add validation/conversion if needed based on actual content structure
                             result_content_blocks = raw_content
                        elif isinstance(raw_content, str):
                             result_content_blocks = [{"type": "text", "text": raw_content}]
                        elif isinstance(raw_content, bytes):
                             try:
                                 result_content_blocks = [{"type": "text", "text": raw_content.decode('utf-8')}]
                             except UnicodeDecodeError:
                                 result_content_blocks = [{"type": "text", "text": f"Binary content (length {len(raw_content)})"}]
                        else:
                             result_content_blocks = [{"type": "text", "text": str(raw_content)}] # Fallback
                    else:
                        result_content_blocks = [{"type": "text", "text": str(mcp_tool_result)}] # Fallback

                    tool_results_for_anthropic.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_content_blocks # Pass the list of blocks
                    })
                except Exception as e:
                    # Include server name in error logging
                    logging.error(f"Error calling MCP tool '{actual_tool_name}' on server '{server_name}': {e}")
                    tool_results_for_anthropic.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": f"Error executing tool {actual_tool_name} on {server_name}: {str(e)}"}],
                        "is_error": True
                    })

            # Add the user message containing tool results to the list for the final API call
            messages_for_final_call.append({
                "role": "user",
                "content": tool_results_for_anthropic
            })

            logging.info(f"Sending tool results to Anthropic model: {anthropic_model}")
            final_response = anthropic_client.messages.create(
                model=anthropic_model,
                max_tokens=1024,
                messages=messages_for_final_call, # Use the constructed list
                tools=anthropic_tools
            )

            final_text = "".join([block.text for block in final_response.content if block.type == 'text'])
            
            # Add the tool results and final assistant response to the global history
            # Ensure content is valid before adding
            if isinstance(tool_results_for_anthropic, list):
                 conversation_history.append({"role": "user", "content": tool_results_for_anthropic})
            if isinstance(final_response.content, list):
                 conversation_history.append({"role": "assistant", "content": final_response.content})
            else:
                 logging.error("Anthropic final response content was not a list of blocks.")

            return final_text

    except Exception as e:
        error_msg = f"Error communicating with Anthropic: {e}"
        logging.error(error_msg)
        # Avoid adding potentially problematic user input to history on API error
        # conversation_history.append({"role": "user", "content": user_input}) # Maybe remove this?
        # conversation_history.append({"role": "assistant", "content": error_msg}) # Add error message? Needs sanitization.
        return error_msg
