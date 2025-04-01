import json
import logging

# This module contains utilities for formatting conversation history for different LLM APIs.

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

# TODO: Consider moving Anthropic history sanitization loop here as well
