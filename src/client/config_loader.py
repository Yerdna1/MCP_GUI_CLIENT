import json
import os
import logging

CONFIG_FILENAME = "mcp_config.json"

def load_mcp_config():
    """Loads MCP server configuration from mcp_config.json in the current working directory."""
    config_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logging.info(f"Configuration loaded successfully from {config_path}")
            # Return only enabled servers
            enabled_servers = {name: cfg for name, cfg in config.get("mcpServers", {}).items() if not cfg.get("disabled", False)}
            if not enabled_servers:
                 logging.warning(f"No enabled servers found in {config_path}")
            return enabled_servers
    except FileNotFoundError:
        logging.error(f"Error: Configuration file not found at {config_path}")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Error: Could not decode JSON from {config_path}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred loading config: {e}")
        return {}
