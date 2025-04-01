import os
from mcp import StdioServerParameters

def select_mcp_server(mcp_servers_config):
    """Lists available MCP servers from config and prompts user for selection."""
    if not mcp_servers_config:
        print("No enabled MCP servers found in configuration.")
        return None, None # Return None for name and config

    print("\nAvailable MCP Servers:")
    server_names = list(mcp_servers_config.keys())
    for i, name in enumerate(server_names):
        print(f"{i + 1}. {name}")

    selected_server_name = None
    while selected_server_name is None:
        try:
            server_choice = input(f"Select a server (1-{len(server_names)}): ")
            index = int(server_choice) - 1
            if 0 <= index < len(server_names):
                selected_server_name = server_names[index]
            else:
                print("Invalid choice.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    selected_config = mcp_servers_config[selected_server_name]
    print(f"Selected server: {selected_server_name}")
    return selected_server_name, selected_config

def prepare_server_parameters(selected_config):
    """Prepares StdioServerParameters from the selected server config."""
    if not selected_config:
        return None

    command = selected_config.get("command")
    args = selected_config.get("args", [])
    env_vars = os.environ.copy()
    if "env" in selected_config:
        env_vars.update(selected_config["env"])

    if not command:
        print(f"Error: 'command' not specified for server in config.")
        return None

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env_vars
    )
    return server_params
