import os
import json
import logging
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Import shared conversation history
try:
    from .conversation_state import conversation_history
except ImportError:
    # Fallback if run directly or structure changes
    conversation_history = []
    logging.warning("Could not import shared conversation_history from .conversation_state")

# --- Gemini Safety Settings ---
# Adjust as needed, be cautious about blocking potentially valid responses
# NOTE: Initial configuration removed. Configuration should happen based on UI settings.
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# Import formatting functions from utils
try:
    from .gemini_utils import format_tools_for_gemini
    from .history_utils import format_history_for_gemini
except ImportError:
    logging.error("Failed to import Gemini utility functions.")
    # Define dummy functions if import fails
    def format_tools_for_gemini(*args, **kwargs): return None
    def format_history_for_gemini(*args, **kwargs): return []

# format_tools_for_gemini function removed (moved to gemini_utils.py)

# format_history_for_gemini function removed (moved to history_utils.py)

def get_gemini_response(connection_mgr, gemini_model_name, user_input):

    if not all_mcp_tools:
        return None

    for server_name, tool_list in all_mcp_tools.items():
        if tool_list:
            for tool in tool_list:
                tool_name = getattr(tool, 'name', None)
                description = getattr(tool, 'description', 'No description available.')
                input_schema = getattr(tool, 'inputSchema', None)

                if not tool_name or not input_schema:
                    logging.warning(f"Skipping tool from server '{server_name}' due to missing name or schema: {tool}")
                    continue

                # Gemini requires specific schema format (OpenAPI subset)
                # Basic conversion attempt:
                gemini_schema = {
                    "type": input_schema.get("type", "OBJECT").upper(), # Default to OBJECT
                    "properties": {},
                    "required": input_schema.get("required", [])
                }

                # Handle properties, including arrays and empty objects
                input_properties = input_schema.get("properties")
                if input_properties: # Check if properties exist and are not empty
                    for prop_name, prop_details in input_properties.items():
                        prop_type = prop_details.get("type", "string").upper()
                        gemini_prop = {
                            "type": prop_type,
                            "description": prop_details.get("description", "")
                        }

                        # Handle array types: add 'items' schema
                        if prop_type == "ARRAY":
                            # Try to get item type from MCP schema, default to STRING
                            items_schema = prop_details.get("items", {})
                            items_type = items_schema.get("type", "string").upper()
                            # Define the items schema structure
                            gemini_items_schema = {"type": items_type}
                            # Copy item description if available
                            if "description" in items_schema:
                                gemini_items_schema["description"] = items_schema["description"]
                            # If items are objects, add required non-empty properties schema
                            if items_type == "OBJECT":
                                # FIXED: Add a placeholder property for OBJECT items to satisfy API requirements
                                gemini_items_schema["properties"] = {
                                    "_placeholder": {
                                        "type": "STRING", 
                                        "description": "Placeholder property to satisfy API requirements"
                                    }
                                }
                            # Assign the constructed items schema
                            gemini_prop["items"] = gemini_items_schema

                        # Handle enums if present
                        if "enum" in prop_details:
                            gemini_prop["enum"] = prop_details["enum"]

                        gemini_schema["properties"][prop_name] = gemini_prop
                
                # FIXED: Ensure all OBJECT types have at least one property
                if gemini_schema["type"] == "OBJECT" and (not gemini_schema["properties"] or len(gemini_schema["properties"]) == 0):
                    # If type is OBJECT but no properties are defined, add a placeholder property
                    gemini_schema["properties"] = {
                        "_placeholder": {
                            "type": "STRING",
                            "description": "Placeholder property to satisfy API requirements"
                        }
                    }

                # Gemini uses FunctionDeclaration
                gemini_tools.append({
                    "name": f"{server_name}__{tool_name}", # Use double underscore to separate server/tool
                    "description": f"(Server: {server_name}) {description}",
                    "parameters": gemini_schema
                })

    return gemini_tools if gemini_tools else None


def format_history_for_gemini(history):
    """Formats the conversation history for the Gemini API."""
    gemini_history = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")

        # Gemini uses 'user' and 'model' roles
        gemini_role = "user" if role == "user" else "model"

        # Handle tool calls and results stored in history
        if role == "tool":
            try:
                tool_data = json.loads(content)
                server_name = tool_data.get("server", "unknown_server")
                tool_name = tool_data.get("tool_name", "unknown_tool")
                result = tool_data.get("result", {"error": "Result missing"})
                # Format for Gemini FunctionResponse
                gemini_history.append({
                    "role": "model", # The request for the tool call comes from the model
                    "parts": [{
                        "function_call": {
                            "name": f"{server_name}__{tool_name}",
                            # Args not available here, Gemini doesn't need them in history response part
                        }
                    }]
                })
                gemini_history.append({
                    "role": "user", # The result is provided *by* the user/function
                    "parts": [{
                        "function_response": {
                            "name": f"{server_name}__{tool_name}",
                            "response": {"result": result} # Wrap result
                        }
                    }]
                })
            except Exception as e:
                logging.warning(f"Could not parse tool message for Gemini history: {e} - Content: {content[:100]}")
                # Append as simple text if parsing fails
                gemini_history.append({"role": gemini_role, "parts": [{"text": f"[Unparseable Tool Message: {content[:100]}...]"}]})

        elif role == "assistant":
             # If assistant message contains function call, it's handled above by the subsequent 'tool' role
             # If it's just text, add it.
             if isinstance(content, str):
                  gemini_history.append({"role": "model", "parts": [{"text": content}]})
             # If it's Anthropic's list format, try to extract text
             elif isinstance(content, list):
                  text_parts = [block.get("text") for block in content if isinstance(block, dict) and block.get("type") == "text"]
                  if text_parts:
                       gemini_history.append({"role": "model", "parts": [{"text": "\n".join(text_parts)}]})

        elif role == "user":
            # Simple user message
            if isinstance(content, str):
                 gemini_history.append({"role": "user", "parts": [{"text": content}]})
            # Handle potential list content from Anthropic tool results in user role
            elif isinstance(content, list):
                 # Try to represent the tool result structure as text
                 try:
                      text_representation = f"[Tool Result: {json.dumps(content)}]"
                      gemini_history.append({"role": "user", "parts": [{"text": text_representation[:1000]}]}) # Limit length
                 except Exception:
                      gemini_history.append({"role": "user", "parts": [{"text": "[Complex Tool Result]"}]})


    # Ensure history doesn't have consecutive messages from the same role
    cleaned_history = []
    if gemini_history:
        cleaned_history.append(gemini_history[0])
        for i in range(1, len(gemini_history)):
            if gemini_history[i]["role"] != cleaned_history[-1]["role"]:
                cleaned_history.append(gemini_history[i])
            else:
                # Attempt to merge parts if consecutive roles match (basic merge)
                try:
                    cleaned_history[-1]["parts"].extend(gemini_history[i]["parts"])
                except Exception as merge_err:
                     logging.warning(f"Could not merge consecutive history parts: {merge_err}")
                     # If merge fails, just keep the last message
                     cleaned_history[-1] = gemini_history[i]


    return cleaned_history


def get_gemini_response(connection_mgr, gemini_model_name, user_input):
    """Handles interaction with Gemini, including function calls."""
    global conversation_history

    # 1. Prepare Tools
    gemini_tools = format_tools_for_gemini(connection_mgr)

    # 2. Prepare History
    gemini_history = format_history_for_gemini(conversation_history)

    # 3. Check API Key and Configure if necessary before initializing model
    try:
        # Check QSettings first, then environment variable
        from PyQt6.QtCore import QSettings
        from ui.dialogs import CONFIG_ORGANIZATION, CONFIG_APPLICATION # Import config constants
        settings = QSettings(CONFIG_ORGANIZATION, CONFIG_APPLICATION)
        api_key = settings.value("google_api_key", os.getenv('GOOGLE_API_KEY', ""))

        if not api_key:
            raise ValueError("Google API Key not found in settings or environment variables. Please configure it.")

        # Configure the client with the found key. Re-configuring is safe.
        logging.info("Configuring Gemini client with API key from settings/env...")
        genai.configure(api_key=api_key)

        # Initialize Model and Chat
        model = genai.GenerativeModel(gemini_model_name, safety_settings=safety_settings)
        chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=False) # Manual calling
    except ImportError:
         # Handle case where PyQt6/QSettings might not be available if run standalone
         error_msg = "Error: Could not import QSettings to check for API key."
         logging.error(error_msg)
         return error_msg
    except Exception as e:
        error_msg = f"Error initializing Gemini model/chat or configuring API key: {e}"
        logging.error(error_msg)
        # Don't add user input to history if model init fails
        return error_msg

    # 4. Send User Message
    try:
        logging.info(f"Sending to Gemini model: {gemini_model_name}")
        response = chat.send_message(user_input, tools=gemini_tools)
        logging.info("Received response from Gemini.")

        # Add user input to global history *after* successful send
        conversation_history.append({"role": "user", "content": user_input})

        # 5. Process Response (Check for Function Call)
        response_part = response.parts[0] if response.parts else None
        if response_part and response_part.function_call:
            function_call = response_part.function_call
            fc_name = function_call.name
            fc_args = function_call.args

            logging.info(f"Gemini requested function call: {fc_name} with args: {fc_args}")

            # Add assistant's function call request to history
            conversation_history.append({"role": "assistant", "content": response.text or f"[Requesting tool: {fc_name}]"}) # Use text if available

            # Parse server and tool name
            try:
                server_name, tool_name = fc_name.split("__", 1)
            except ValueError:
                error_msg = f"Error: Could not parse server/tool name from Gemini function call '{fc_name}'"
                logging.error(error_msg)
                # Send error back to Gemini? Or just return error to user?
                # For now, return error to user and add to history
                conversation_history.append({"role": "tool", "content": json.dumps({"error": error_msg})})
                return error_msg

            # 6. Execute MCP Tool
            try:
                tool_result = connection_mgr.call_tool(server_name, tool_name, dict(fc_args))
                logging.info(f"Tool '{tool_name}' on server '{server_name}' executed.")

                # Safely extract content for Gemini FunctionResponse
                tool_result_content = None
                if tool_result is None:
                    tool_result_content = {"error": "No result returned from tool"}
                elif isinstance(tool_result, bool):
                    tool_result_content = {"success": tool_result}
                elif isinstance(tool_result, (str, int, float)):
                     tool_result_content = tool_result # Send simple types directly
                elif hasattr(tool_result, 'content'):
                    raw_content = tool_result.content
                    if isinstance(raw_content, bytes):
                        try: tool_result_content = raw_content.decode('utf-8')
                        except UnicodeDecodeError: tool_result_content = f"Binary content (length {len(raw_content)})"
                    else: tool_result_content = raw_content
                else:
                    tool_result_content = {"result": str(tool_result)} # Fallback

                # Add tool result to global history (as JSON string for consistency with Ollama path)
                history_tool_result_str = json.dumps({
                    "server": server_name,
                    "tool_name": tool_name,
                    "result": tool_result_content
                })
                conversation_history.append({"role": "tool", "content": history_tool_result_str})

                # 7. Send Tool Result back to Gemini
                logging.info("Sending tool result back to Gemini.")
                function_response = {
                    "function_response": {
                        "name": fc_name,
                        "response": {"result": tool_result_content} # Wrap result
                    }
                }
                response = chat.send_message(function_response) # Send FunctionResponse part

            except Exception as tool_exec_error:
                logging.exception(f"Error executing MCP tool '{tool_name}' on server '{server_name}'")
                error_str = f"Error executing tool: {type(tool_exec_error).__name__}"
                # Add error to global history
                history_tool_error_str = json.dumps({
                    "server": server_name,
                    "tool_name": tool_name,
                    "error": error_str
                })
                conversation_history.append({"role": "tool", "content": history_tool_error_str})

                # Send error back to Gemini
                logging.info("Sending tool execution error back to Gemini.")
                function_response = {
                    "function_response": {
                        "name": fc_name,
                        "response": {"error": error_str} # Send error detail
                    }
                }
                response = chat.send_message(function_response)

        # 8. Process Final Response
        final_text = response.text
        logging.info(f"Received final response from Gemini: {final_text}")

        # Add final assistant response to global history
        conversation_history.append({"role": "assistant", "content": final_text})

        return final_text

    except Exception as e:
        error_msg = f"Error during Gemini interaction: {e}"
        logging.exception("Error during Gemini interaction")
        # Avoid adding user input if the initial send failed
        if "response" not in locals():
             pass # Don't add user input if send_message failed
        else:
             # If send succeeded but processing failed, user input is already added
             # Add the error as the assistant response
             conversation_history.append({"role": "assistant", "content": f"[Error: {error_msg}]"})
        return error_msg
