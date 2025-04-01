import json
import re
import ollama
from anthropic import Anthropic # Keep import for type hinting if needed

# Global conversation history (consider passing as argument instead)
conversation_history = []

async def get_ollama_response(session, selected_ollama_model, available_tools_list, user_input):
    """Handles interaction with Ollama, including tool calls."""
    global conversation_history # Use global for now, better to pass/return

    tools_description = "\nAvailable Tools:\n"
    for tool in available_tools_list:
        tools_description += f"- {tool.name}: {tool.description}\n  Input Schema: {json.dumps(tool.inputSchema)}\n"
    if not available_tools_list:
         tools_description = "\nNo tools available or failed to list them."

    system_prompt = f"""You are a helpful assistant connected to an MCP server.
{tools_description}
If you need to use a tool based on the user's request, respond ONLY with the following format on a single line, ensuring the arguments match the Input Schema:
TOOL_CALL: {{"name": "tool_name", "arguments": {{...}}}}
Otherwise, respond directly to the user."""

    current_messages = conversation_history + [{"role": "user", "content": user_input}]
    messages_for_ollama = [m for m in current_messages if m['role'] != 'system']
    messages_for_ollama.insert(0, {'role': 'system', 'content': system_prompt})

    try:
        print(f"\n[Sending to Ollama model: {selected_ollama_model}]")
        response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
        assistant_response_content = response['message']['content'].strip()
        print(f"--- Received from Ollama: ---\n{assistant_response_content}\n---------------------------")

        if assistant_response_content.startswith("TOOL_CALL:"):
            tool_call_json_str = assistant_response_content[len("TOOL_CALL:"):].strip()
            try:
                tool_call_data = json.loads(tool_call_json_str)
                tool_name = tool_call_data.get("name")
                tool_args = tool_call_data.get("arguments", {})
                if not tool_name: raise ValueError("Tool name missing")

                print(f"\n[Attempting to call MCP tool '{tool_name}' with args: {tool_args}]")
                tool_result = await session.call_tool(tool_name, arguments=tool_args)
                print(f"[Tool '{tool_name}' result: {tool_result}]")

                tool_result_content_str = json.dumps({"tool_name": tool_name, "result": tool_result.content})
                messages_for_ollama.append({'role': 'assistant', 'content': assistant_response_content})
                messages_for_ollama.append({'role': 'tool', 'content': tool_result_content_str})

                print(f"\n[Sending tool result to Ollama model: {selected_ollama_model}]")
                final_response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
                final_text = final_response['message']['content']
                print(f"\nAssistant: {final_text}")
                # Update global history
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': assistant_response_content})
                conversation_history.append({'role': 'tool', 'content': tool_result_content_str})
                conversation_history.append({'role': 'assistant', 'content': final_text})

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing/validating TOOL_CALL: {e}")
                print(f"\nAssistant: Error: Could not parse tool call instruction from LLM.")
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': assistant_response_content})
            except Exception as e:
                called_tool_name = tool_call_data.get("name", "unknown") if 'tool_call_data' in locals() else "unknown"
                print(f"Error calling MCP tool '{called_tool_name}': {e}")
                error_message_for_llm = f"Error executing tool {called_tool_name}: {str(e)}"
                messages_for_ollama.append({'role': 'assistant', 'content': assistant_response_content})
                messages_for_ollama.append({'role': 'tool', 'content': error_message_for_llm})
                print(f"\n[Sending tool error to Ollama model: {selected_ollama_model}]")
                error_response = ollama.chat(model=selected_ollama_model, messages=messages_for_ollama)
                final_text = error_response['message']['content']
                print(f"\nAssistant: {final_text}")
                conversation_history.append({"role": "user", "content": user_input})
                conversation_history.append({'role': 'assistant', 'content': assistant_response_content})
                conversation_history.append({'role': 'tool', 'content': error_message_for_llm})
                conversation_history.append({'role': 'assistant', 'content': final_text})
        else:
            print(f"\nAssistant: {assistant_response_content}")
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": assistant_response_content})

    except Exception as e:
        print(f"\nError communicating with Ollama: {e}")


async def get_anthropic_response(session, anthropic_client, anthropic_model, available_tools_list, user_input):
    """Handles interaction with Anthropic, including tool calls."""
    global conversation_history # Use global for now, better to pass/return

    anthropic_tools = [{
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema
    } for tool in available_tools_list]

    # Ensure messages have the correct format for Anthropic
    current_messages = conversation_history + [{"role": "user", "content": user_input}]
    messages_for_anthropic = []
    for msg in current_messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, list):
            messages_for_anthropic.append(msg)
        elif role == "tool":
            try:
                tool_data = json.loads(content)
                tool_use_id = "unknown_id" # Placeholder
                if len(conversation_history) > 1 and conversation_history[-2]["role"] == "assistant":
                    assistant_content = conversation_history[-2]["content"]
                    if isinstance(assistant_content, list):
                        for block in assistant_content:
                            if block.type == "tool_use" and block.name == tool_data.get("tool_name"):
                                tool_use_id = block.id
                                break
                messages_for_anthropic.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": tool_data.get("result", [])}]
                })
            except (json.JSONDecodeError, AttributeError):
                 messages_for_anthropic.append({"role": "user", "content": f"Tool result (unparseable): {content}"})
        else:
            messages_for_anthropic.append({"role": role, "content": content})

    try:
        print(f"\n[Sending to Anthropic model: {anthropic_model}]")
        response = anthropic_client.messages.create(
            model=anthropic_model,
            max_tokens=1024,
            messages=messages_for_anthropic,
            tools=anthropic_tools
        )
        print(f"--- Received from Anthropic ---")

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

        print(f"  Text Parts: {''.join(text_response_parts)}")
        print(f"  Tool Calls: {tool_calls_to_make}")
        print("---------------------------------")

        # Update history with user input and initial assistant response
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": assistant_response_content_blocks})

        if not tool_calls_to_make:
            print(f"\nAssistant: {''.join(text_response_parts)}")
        else:
            tool_results_for_anthropic = []
            messages_for_final_call = conversation_history # Use history up to this point

            for tool_call in tool_calls_to_make:
                tool_name = tool_call["name"]
                tool_args = tool_call["input"]
                tool_use_id = tool_call["id"]
                print(f"\n[Attempting to call MCP tool '{tool_name}' with args: {tool_args}]")
                try:
                    mcp_tool_result = await session.call_tool(tool_name, arguments=tool_args)
                    print(f"[Tool '{tool_name}' result: {mcp_tool_result}]")
                    result_content = mcp_tool_result.content if isinstance(mcp_tool_result.content, list) else [mcp_tool_result.content]
                    tool_results_for_anthropic.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_content
                    })
                except Exception as e:
                    print(f"Error calling MCP tool '{tool_name}': {e}")
                    tool_results_for_anthropic.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": f"Error executing tool: {str(e)}"}],
                        "is_error": True
                    })

            # Send tool results back to Anthropic
            messages_for_final_call.append({
                "role": "user",
                "content": tool_results_for_anthropic
            })

            print(f"\n[Sending tool results to Anthropic model: {anthropic_model}]")
            final_response = anthropic_client.messages.create(
                model=anthropic_model,
                max_tokens=1024,
                messages=messages_for_final_call,
                tools=anthropic_tools
            )

            final_text = "".join([block.text for block in final_response.content if block.type == 'text'])
            print(f"\nAssistant: {final_text}")
            # Add final assistant response to history
            conversation_history.append({"role": "assistant", "content": final_response.content})

    except Exception as e:
        print(f"\nError communicating with Anthropic: {e}")
