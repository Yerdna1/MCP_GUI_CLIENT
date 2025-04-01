from mcp import ClientSession, types
from mcp.client.stdio import stdio_client
import logging
import asyncio

# Import refactored components
from config_loader import load_mcp_config
from llm_selector import select_llm_provider, select_ollama_model, initialize_anthropic_client, ensure_llm_provider_ready
from mcp_connector import select_mcp_server, prepare_server_parameters
from llm_interaction import get_ollama_response, get_anthropic_response

logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)

async def run():
    # --- LLM Setup ---
    llm_provider = select_llm_provider()
    selected_ollama_model = None
    anthropic_client = None
    anthropic_model = None

    if llm_provider == 'ollama':
        selected_ollama_model = select_ollama_model()
    elif llm_provider == 'anthropic':
        anthropic_client, anthropic_model = initialize_anthropic_client()
        if not anthropic_client:
            return # Exit if Anthropic client failed to initialize

    # --- MCP Server Setup ---
    mcp_servers_config = load_mcp_config()
    if not mcp_servers_config:
        print("No enabled MCP servers found in configuration. Exiting.")
        return

    selected_server_name, selected_config = select_mcp_server(mcp_servers_config)
    if not selected_server_name:
        return # Exit if no server selected

    server_params = prepare_server_parameters(selected_config)
    if not server_params:
        return # Exit if params couldn't be prepared

    # --- Ensure LLM Ready ---
    if not ensure_llm_provider_ready(llm_provider, selected_ollama_model, anthropic_client):
        return # Exit if selected LLM provider isn't ready

    # --- Main Connection and Interaction Loop ---
    print(f"\n===== MCP CLIENT ({llm_provider.capitalize()} Mode) - Connecting to {selected_server_name} =====\n")
    session = None
    available_tools_list = []
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                try:
                    tools_list_response = await session.list_tools()
                    available_tools_list = tools_list_response.tools
                    print(f"Available tools: {[tool.name for tool in available_tools_list]}")
                except Exception as e:
                    print(f"Warning: Could not list tools for {selected_server_name}. Error: {e}")
                    print("Proceeding without tool list...")

                print("\nEnter your query or type 'exit' to quit.")
                while True:
                    user_input = input("\nYou: ").strip()
                    if user_input.lower() == "exit":
                        print("Exiting...")
                        break

                    # Call the appropriate LLM interaction function
                    if llm_provider == 'ollama':
                        await get_ollama_response(session, selected_ollama_model, available_tools_list, user_input)
                    elif llm_provider == 'anthropic':
                        await get_anthropic_response(session, anthropic_client, anthropic_model, available_tools_list, user_input)

    except Exception as e:
        print(f"\nFATAL ERROR during MCP session with {selected_server_name}: {e}")
    finally:
        print("Client run finished.")


if __name__ == "__main__":
    # Add imports needed at the top level if not already there
    import sys
    try:
        import ollama
        import anthropic
        from mcp import ClientSession, StdioServerParameters, types
        from mcp.client.stdio import stdio_client
    except ImportError as e:
        print(f"Error: Missing required library. Please ensure 'mcp', 'ollama', and 'anthropic' are installed. Details: {e}")
        sys.exit(1)

    asyncio.run(run())
