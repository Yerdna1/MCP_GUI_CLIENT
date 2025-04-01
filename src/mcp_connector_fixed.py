import os
import asyncio
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
import logging
import threading
import traceback
from typing import Dict, Any, Optional, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_mcp_server_names(mcp_servers_config):
    """Returns a list of available MCP server names from the config."""
    if not mcp_servers_config:
        logging.warning("No enabled MCP servers found in configuration.")
        return []

    server_names = [name for name, cfg in mcp_servers_config.items() if not cfg.get("disabled", False)]
    logging.info(f"Found enabled servers: {server_names}")
    return server_names

def prepare_server_parameters(selected_server_name, mcp_servers_config):
    """Prepares StdioServerParameters for the selected server name."""
    if not selected_server_name or not mcp_servers_config:
        logging.error("Missing server name or config for parameter preparation.")
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

class MCPConnectionManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        # Dictionary to store connection details per server_name
        # Structure: { server_name: { "session": ClientSession, "read": ..., "write": ..., "tools": [],
        #                             "status": "disconnected" | "connecting" | "connected" | "error" | "disconnecting",
        #                             "error_message": str | None, "stdio_context": ... } }
        self.connections: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock() # To protect access to self.connections

    def _run_async(self, async_func, timeout=30):
        """Runs async code in a new thread with a dedicated event loop and timeout."""
        result = None
        exception = None
        thread_done = threading.Event()

        def thread_func():
            nonlocal result, exception
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def run_with_timeout():
                    return await asyncio.wait_for(async_func(), timeout)
                result = loop.run_until_complete(run_with_timeout())
            except asyncio.TimeoutError:
                exception = TimeoutError(f"Operation timed out after {timeout} seconds")
                logging.error(f"MCP operation timed out after {timeout} seconds")
            except Exception as e:
                exception = e
                logging.error(f"Error in async operation: {str(e)}")
                logging.debug(traceback.format_exc())
            finally:
                # Refined cleanup: Cancel pending tasks and wait briefly
                try:
                    current_task = asyncio.current_task(loop)
                    tasks = [task for task in asyncio.all_tasks(loop) if task is not current_task]
                    if tasks:
                        logging.debug(f"Attempting to cancel {len(tasks)} pending tasks...")
                        for task in tasks:
                            task.cancel()
                        # Wait briefly for cancellations to finish
                        loop.run_until_complete(asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0))
                        logging.debug("Finished gathering cancelled tasks.")
                except asyncio.TimeoutError:
                     logging.warning("Timed out waiting for cancelled tasks to finish during cleanup.")
                except Exception as e:
                    logging.error(f"Error cancelling/gathering pending tasks during cleanup: {str(e)}")
                finally:
                    # Proceed with closing the loop
                    try:
                        # Ensure loop is stopped before closing
                        if loop.is_running():
                            loop.stop()
                            # Give a moment for stop to register if needed, though close should handle it
                            # loop.run_until_complete(asyncio.sleep(0.01)) # Usually not needed
                        if not loop.is_closed():
                            loop.close()
                            logging.debug("Event loop closed.")
                        else:
                            logging.debug("Event loop already closed.")
                    except Exception as e:
                         logging.error(f"Error closing event loop: {str(e)}")
                    finally:
                         # Signal completion regardless of cleanup success/failure
                         logging.debug("Signalling thread completion.")
                         thread_done.set()

        thread = threading.Thread(target=thread_func)
        thread.daemon = True
        thread.start()

        thread_timeout = timeout + 30
        if not thread_done.wait(thread_timeout):
            logging.error(f"Thread execution exceeded timeout ({thread_timeout}s)")
            exception = TimeoutError(f"Thread execution exceeded timeout ({thread_timeout}s)")

        if exception:
            logging.error(f"Async operation failed with: {exception}")
            raise exception

        return result

    def connect(self, server_name: str, server_params: StdioServerParameters, connect_timeout=30) -> Tuple[bool, Optional[str]]:
        """Connect to a specific MCP server synchronously with timeout. Returns (success, error_message)."""
        with self._lock:
            if server_name in self.connections and self.connections[server_name]["status"] in ["connecting", "connected"]:
                logging.warning(f"Already connecting or connected to {server_name}.")
                return (self.connections[server_name]["status"] == "connected", self.connections[server_name].get("error_message"))

            # Initialize or reset connection state
            self.connections[server_name] = {
                "session": None, "read": None, "write": None, "tools": [],
                "status": "connecting", "error_message": None, "stdio_context": None
            }

        success = False
        error_message = None
        session = None
        read = None
        write = None
        tools = []
        stdio_context = None

        try:
            logging.info(f"Starting connection to MCP server: {server_name}")

            async def do_connect():
                nonlocal session, read, write, tools, stdio_context # Allow modification
                # Create stdio context
                logging.info(f"[{server_name}] Creating stdio context")
                current_stdio_context = stdio_client(server_params)
                logging.info(f"[{server_name}] Attempting to connect with command: {server_params.command} {' '.join(server_params.args)}")
                current_read, current_write = await current_stdio_context.__aenter__()
                logging.info(f"[{server_name}] Stdio context created successfully")

                # Create client session
                logging.info(f"[{server_name}] Creating client session")
                current_session = ClientSession(current_read, current_write)
                await current_session.__aenter__()
                logging.info(f"[{server_name}] Initializing session")
                await current_session.initialize()
                logging.info(f"[{server_name}] Session initialized successfully")

                # Retrieve tools
                logging.info(f"[{server_name}] Retrieving available tools")
                tools_response = await current_session.list_tools()
                current_tools = tools_response.tools
                logging.info(f"[{server_name}] Retrieved {len(current_tools)} tools")

                # Assign to outer scope variables on success
                session = current_session
                read = current_read
                write = current_write
                tools = current_tools
                stdio_context = current_stdio_context
                return True # Indicate success

            # Run the async connection logic
            logging.info(f"[{server_name}] Running connection with {connect_timeout}s timeout")
            connection_successful = self._run_async(do_connect, timeout=connect_timeout)

            success = bool(connection_successful)
            logging.info(f"Connection result for {server_name}: {success} with {len(tools)} tools")

        except Exception as e:
            error_message = str(e)
            logging.error(f"MCP connection setup error for {server_name}: {e}")
            logging.debug(traceback.format_exc())
            success = False
            # Ensure potential partial resources are cleaned up if an error occurred *during* connection
            # Use asyncio.run for cleanup in the main thread context if needed
            if session: asyncio.run(session.__aexit__(None, None, None))
            if stdio_context: asyncio.run(stdio_context.__aexit__(None, None, None))
            # Reset variables that might have been partially assigned
            session, read, write, tools, stdio_context = None, None, None, [], None

        finally:
            # Update the final status in the shared dictionary
            with self._lock:
                if server_name in self.connections: # Check if entry still exists (disconnect might have removed it)
                    self.connections[server_name].update({
                        "session": session,
                        "read": read,
                        "write": write,
                        "tools": tools,
                        "status": "connected" if success else "error",
                        "error_message": error_message,
                        "stdio_context": stdio_context
                    })
                else:
                     logging.warning(f"Connection entry for {server_name} was removed during connection attempt, possibly by disconnect.")


        return success, error_message

    def disconnect(self, server_name: str, disconnect_timeout=5) -> bool:
        """Disconnect from a specific MCP server synchronously with timeout."""
        with self._lock:
            if server_name not in self.connections or self.connections[server_name]["status"] in ["disconnected", "disconnecting"]:
                logging.warning(f"Server {server_name} not connected or already disconnecting.")
                return True # Consider already disconnected as success

            if self.connections[server_name]["status"] == "connecting":
                 logging.warning(f"Server {server_name} is still connecting, cannot disconnect yet.")
                 # Optionally, you could try to cancel the connection attempt here, but it's complex.
                 # For simplicity, just report failure.
                 return False

            # Mark as disconnecting
            self.connections[server_name]["status"] = "disconnecting"
            # Retrieve resources needed for disconnection
            session_to_close = self.connections[server_name].get("session")
            stdio_context_to_close = self.connections[server_name].get("stdio_context")

        success = False
        try:
            logging.info(f"Starting disconnection from MCP server: {server_name}")

            async def do_disconnect():
                logging.info(f"[{server_name}] Closing session")
                if session_to_close:
                    await session_to_close.__aexit__(None, None, None)
                logging.info(f"[{server_name}] Closing stdio context")
                if stdio_context_to_close:
                    await stdio_context_to_close.__aexit__(None, None, None)
                logging.info(f"[{server_name}] Disconnection complete")
                return True

            logging.info(f"[{server_name}] Running disconnection with {disconnect_timeout}s timeout")
            success = self._run_async(do_disconnect, timeout=disconnect_timeout)
            logging.info(f"[{server_name}] Disconnection result: {success}")

        except Exception as e:
            logging.error(f"MCP disconnection error for {server_name}: {e}")
            logging.debug(traceback.format_exc())
            success = False
        finally:
            # Clean up the entry in the connections dictionary
            with self._lock:
                if server_name in self.connections:
                     # Keep the entry but mark as disconnected, retain error if disconnect failed
                     self.connections[server_name] = {
                         "session": None, "read": None, "write": None, "tools": [],
                         "status": "disconnected",
                         "error_message": self.connections[server_name].get("error_message") if not success else None, # Keep previous error if disconnect fails
                         "stdio_context": None
                     }
                     # Alternatively, remove the entry entirely: del self.connections[server_name]
                logging.info(f"Connection manager state updated for {server_name} after disconnection attempt.")

        return success

    def disconnect_all(self, disconnect_timeout=5):
        """Disconnects from all currently connected servers."""
        logging.info("Disconnecting from all MCP servers...")
        server_names_to_disconnect = []
        with self._lock:
            server_names_to_disconnect = list(self.connections.keys()) # Get a copy of keys

        results = {}
        for server_name in server_names_to_disconnect:
             # Check status again before disconnecting, might have changed
             with self._lock:
                 current_status = self.connections.get(server_name, {}).get("status")
             if current_status in ["connected", "error", "disconnecting"]: # Attempt disconnect even on error state
                 logging.info(f"Initiating disconnect for {server_name}")
                 results[server_name] = self.disconnect(server_name, disconnect_timeout)
             else:
                 logging.info(f"Skipping disconnect for {server_name} (status: {current_status})")
                 results[server_name] = True # Already disconnected or not connected

        logging.info(f"Finished disconnecting all servers. Results: {results}")
        return all(results.values()) # Return True if all disconnections were successful

    def call_tool(self, server_name: str, tool_name: str, tool_args: Dict[str, Any], call_timeout=60):
        """Call a tool on a specific connected server synchronously."""
        with self._lock:
            connection_info = self.connections.get(server_name)
            if not connection_info or connection_info["status"] != "connected":
                error_msg = f"Server '{server_name}' is not connected or does not exist."
                logging.error(error_msg)
                raise ValueError(error_msg)
            session = connection_info["session"]
            if not session:
                 error_msg = f"Session object missing for connected server '{server_name}'."
                 logging.error(error_msg)
                 raise ValueError(error_msg) # Should not happen if status is 'connected'

        logging.info(f"Calling tool '{tool_name}' on server '{server_name}'")

        async def do_call_tool():
            # Ensure the session is still valid before calling
            # (Could add a check here if sessions can become invalid without status change)
            return await session.call_tool(tool_name, arguments=tool_args)

        try:
            return self._run_async(do_call_tool, timeout=call_timeout)
        except Exception as e:
            logging.error(f"Error calling MCP tool '{tool_name}' on server '{server_name}': {e}")
            # Potentially update server status to 'error' here
            # with self._lock:
            #    if server_name in self.connections:
            #        self.connections[server_name]["status"] = "error"
            #        self.connections[server_name]["error_message"] = f"Tool call failed: {e}"
            raise # Re-raise the exception for the caller to handle

    def get_connection_status(self, server_name: str) -> Optional[str]:
        """Returns the connection status of a specific server."""
        with self._lock:
            return self.connections.get(server_name, {}).get("status")

    def get_all_statuses(self) -> Dict[str, str]:
        """Returns a dictionary of all server statuses."""
        with self._lock:
            return {name: info.get("status", "unknown") for name, info in self.connections.items()}

    def get_tools(self, server_name: str) -> Optional[List[Dict[str, Any]]]:
        """Returns the list of tools for a specific connected server."""
        with self._lock:
            connection_info = self.connections.get(server_name)
            if connection_info and connection_info["status"] == "connected":
                return connection_info.get("tools", [])
            return None # Return None if not connected or server doesn't exist

    def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
         """Returns a dictionary mapping server names to their list of tools."""
         all_tools = {}
         with self._lock:
             for name, info in self.connections.items():
                 if info.get("status") == "connected":
                     all_tools[name] = info.get("tools", [])
         return all_tools

    def is_connected(self, server_name: str) -> bool:
        """Checks if a specific server is currently connected."""
        return self.get_connection_status(server_name) == "connected"

    def get_error_message(self, server_name: str) -> Optional[str]:
        """Gets the last error message for a specific server, if any."""
        with self._lock:
            return self.connections.get(server_name, {}).get("error_message")
