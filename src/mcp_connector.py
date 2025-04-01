import os
from mcp import StdioServerParameters
import logging

def get_mcp_server_names(mcp_servers_config):
    """Returns a list of available MCP server names from the config."""
    if not mcp_servers_config:
        logging.warning("No enabled MCP servers found in configuration.")
        return [] # Return empty list

    server_names = list(mcp_servers_config.keys())
    return server_names

def prepare_server_parameters(selected_server_name, mcp_servers_config):
    """Prepares StdioServerParameters for the selected server name."""
    if not selected_server_name or not mcp_servers_config:
        return None

    selected_config = mcp_servers_config.get(selected_server_name)
    if not selected_config:
        logging.error(f"Configuration for server '{selected_server_name}' not found.")
        return None

    command = selected_config.get("command")
    args = selected_config.get("args", [])
    env_vars = os.environ.copy()
    if "env" in selected_config:
        env_vars.update(selected_config["env"])

    if not command:
        logging.error(f"Error: 'command' not specified for server '{selected_server_name}' in config.")
        return None

    logging.info(f"Preparing parameters for server '{selected_server_name}' with command '{command}'")
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env_vars
    )
    return server_params
