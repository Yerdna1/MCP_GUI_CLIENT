import logging
import json
from PyQt6.QtCore import QThread, pyqtSignal

# Import LLM interaction functions from their new handler files
try:
    from src.client.ollama_handler import get_ollama_response
except ImportError:
    logging.error("Failed to import get_ollama_response from src.client.ollama_handler.")
    def get_ollama_response(*args, **kwargs): return "Error: Ollama function not loaded."
try:
    from src.client.anthropic_handler import get_anthropic_response
except ImportError:
    logging.error("Failed to import get_anthropic_response from src.client.anthropic_handler.")
    def get_anthropic_response(*args, **kwargs): return "Error: Anthropic function not loaded."
try:
    from src.client.gemini_handler import get_gemini_response
except ImportError:
    logging.error("Failed to import get_gemini_response from src.client.gemini_handler.")
    def get_gemini_response(*args, **kwargs): return "Error: Gemini function not loaded."

# Placeholder for Anthropic client if needed by LLMChatWorker
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

class MCPToolCallWorker(QThread):
    """Worker thread for calling MCP tools to avoid freezing the UI."""
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    # Modified __init__ to accept server_name
    def __init__(self, connection_mgr, server_name, tool_name, tool_args):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.server_name = server_name # Store the server name
        self.tool_name = tool_name
        self.tool_args = tool_args

    def run(self):
        try:
            # Call the updated 'call_tool' method with server_name
            logging.info(f"Worker executing tool '{self.tool_name}' on server '{self.server_name}'")
            result = self.connection_mgr.call_tool(self.server_name, self.tool_name, self.tool_args)
            self.result_ready.emit(result)
        except Exception as e:
            logging.error(f"Error in MCPToolCallWorker for tool {self.tool_name} on server {self.server_name}: {e}")
            # Include server name in error message
            self.error_occurred.emit(f"Error calling tool {self.tool_name} on {self.server_name}: {str(e)}")

class LLMChatWorker(QThread):
    """Worker thread for LLM chat interactions to avoid freezing the UI."""
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, connection_mgr, model_type, model_name, user_input, anthropic_client=None):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.model_type = model_type
        self.model_name = model_name
        self.user_input = user_input
        self.anthropic_client = anthropic_client # Passed in from ChatWidget

    def run(self):
        try:
            if self.model_type == "ollama":
                response = get_ollama_response(self.connection_mgr, self.model_name, self.user_input)
            elif self.model_type == "anthropic" and self.anthropic_client:
                # Ensure get_anthropic_response is defined before calling
                if 'get_anthropic_response' in globals():
                    response = get_anthropic_response(self.connection_mgr,
                                                     self.anthropic_client,
                                                     self.model_name,
                                                     self.user_input)
                else:
                    response = "Error: Anthropic response function not loaded."
            elif self.model_type == "anthropic" and not self.anthropic_client:
                 response = "Error: Anthropic client not available or API key missing."
            elif self.model_type == "gemini":
                 # Ensure get_gemini_response is defined before calling
                 if 'get_gemini_response' in globals():
                      # Gemini doesn't need a separate client instance passed like Anthropic
                      response = get_gemini_response(self.connection_mgr,
                                                     self.model_name,
                                                     self.user_input)
                 else:
                      response = "Error: Gemini response function not loaded."
            else:
                response = f"Error: Invalid model type '{self.model_type}'"

            self.response_ready.emit(response)
        except Exception as e:
            logging.error(f"Error in LLMChatWorker: {e}")
            self.error_occurred.emit(f"Error getting LLM response: {str(e)}")

# Import necessary functions from the updated connector
try:
    from src.mcp_connector_fixed import get_mcp_server_names, prepare_server_parameters
except ImportError:
    logging.error("Failed to import MCP connection helper functions.")
    # Define dummy functions if import fails
    def get_mcp_server_names(*args, **kwargs): return []
    def prepare_server_parameters(*args, **kwargs): return None


class MCPSequentialConnectionWorker(QThread):
    """Worker thread to connect to MCP servers sequentially."""
    # Signals for granular progress updates
    server_connection_attempt = pyqtSignal(str) # server_name
    server_connection_successful = pyqtSignal(str, list) # server_name, tools_list
    server_connection_failed = pyqtSignal(str, str) # server_name, error_message
    all_connections_finished = pyqtSignal(dict) # final_statuses {server_name: status}

    def __init__(self, connection_mgr, mcp_servers_config):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.mcp_servers_config = mcp_servers_config

    def run(self):
        server_names = get_mcp_server_names(self.mcp_servers_config)
        if not server_names:
            logging.warning("No servers found to connect to.")
            self.all_connections_finished.emit({}) # Emit empty dict if no servers
            return

        for server_name in server_names:
            try:
                self.server_connection_attempt.emit(server_name)
                logging.info(f"Attempting connection to {server_name}...")
                params = prepare_server_parameters(server_name, self.mcp_servers_config)

                if params:
                    # Use the connect method which now returns (success, error_message)
                    success, error_msg = self.connection_mgr.connect(server_name, params)
                    if success:
                        tools = self.connection_mgr.get_tools(server_name)
                        logging.info(f"Successfully connected to {server_name} with {len(tools or [])} tools.")
                        self.server_connection_successful.emit(server_name, tools if tools else [])
                    else:
                        err_str = error_msg or "Unknown connection error"
                        logging.error(f"Failed to connect to {server_name}: {err_str}")
                        self.server_connection_failed.emit(server_name, err_str)
                else:
                    err_str = f"Failed to prepare parameters for {server_name}"
                    logging.error(err_str)
                    self.server_connection_failed.emit(server_name, err_str)

            except Exception as e:
                # Catch unexpected errors during the loop for a specific server
                err_str = f"Unexpected error connecting to {server_name}: {str(e)}"
                logging.exception(f"Unexpected error in MCPSequentialConnectionWorker for {server_name}") # Log traceback
                self.server_connection_failed.emit(server_name, err_str)
                # Optionally decide whether to continue with the next server or stop

        # After attempting all connections
        final_statuses = self.connection_mgr.get_all_statuses()
        logging.info(f"Finished connection attempts. Final statuses: {final_statuses}")
        self.all_connections_finished.emit(final_statuses)


class MCPDisconnectAllWorker(QThread):
    """Worker thread for disconnecting all MCP servers."""
    # Define signal for disconnection result
    disconnection_complete = pyqtSignal(bool) # True if all disconnected successfully

    def __init__(self, connection_mgr):
        super().__init__()
        self.connection_mgr = connection_mgr

    def run(self):
        try:
            # Call the disconnect_all method
            logging.info("Disconnecting all servers via worker...")
            success = self.connection_mgr.disconnect_all()
            self.disconnection_complete.emit(success)
            logging.info(f"Disconnect all result: {success}")
        except Exception as e:
            logging.error(f"Error during disconnect all worker: {e}")
            self.disconnection_complete.emit(False) # Indicate failure
