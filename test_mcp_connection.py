import sys
import os
import logging
from src.client.config_loader import load_mcp_config
from src.mcp_connector_fixed import get_mcp_server_names, prepare_server_parameters, MCPConnectionManager

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MCP-Test")

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def test_mcp_connection():
    """Test the MCP connection manager with a sample server."""
    import time
    print("Step 1: Loading MCP server configuration...")
    logger.info("Loading MCP server configuration...")
    mcp_servers_config = load_mcp_config()
    
    if not mcp_servers_config:
        logger.error("No MCP server configuration found.")
        return False
    
    print("Step 2: Getting server names...")
    server_names = get_mcp_server_names(mcp_servers_config)
    if not server_names:
        logger.error("No MCP servers found in configuration.")
        return False
    
    logger.info(f"Available MCP servers: {', '.join(server_names)}")
    
    # Select the first server for testing
    selected_server = server_names[0]
    logger.info(f"Testing connection to: {selected_server}")
    
    # Prepare server parameters
    print("Step 3: Preparing server parameters...")
    server_params = prepare_server_parameters(selected_server, mcp_servers_config)
    if not server_params:
        logger.error(f"Failed to prepare parameters for {selected_server}")
        return False
    
    # Initialize connection manager
    print("Step 4: Initializing connection manager...")
    connection_mgr = MCPConnectionManager.get_instance()
    
    # Test connection
    print("Step 5: Attempting to connect...")
    logger.info("Attempting to connect...")
    try:
        print("Step 5.1: Calling connect()...")
        connect_result = connection_mgr.connect(server_params)
        print(f"Step 5.2: Connect result: {connect_result}")
        
        if connect_result:
            logger.info("Connection successful!")
            print(f"Step 6: Connection successful! Tools: {[tool.name for tool in connection_mgr.tools]}")
            logger.info(f"Available tools: {[tool.name for tool in connection_mgr.tools]}")
            
            # Test disconnection
            print("Step 7: Disconnecting...")
            logger.info("Disconnecting...")
            
            print("Step 7.1: Calling disconnect()...")
            disconnect_result = connection_mgr.disconnect()
            print(f"Step 7.2: Disconnect result: {disconnect_result}")
            
            if disconnect_result:
                logger.info("Disconnection successful")
                return True
            else:
                logger.error("Disconnection failed")
                return False
        else:
            print(f"Step 6 (alt): Connection failed: {connection_mgr.connection_error}")
            logger.error(f"Connection failed: {connection_mgr.connection_error}")
            return False
    except Exception as e:
        print(f"Error during MCP connection test: {e}")
        logger.exception(f"Error during MCP connection test: {e}")
        return False

def run_with_timeout(func, timeout=30):
    """Run a function with a timeout."""
    import threading
    import time
    
    result = [None]
    exception = [None]
    completed = [False]
    
    def worker():
        # Initialize StreamlitScript context if running within streamlit
        try:
            import streamlit.runtime.scriptrunner.script_run_context as script_run_context
            # Check if we're in a Streamlit context - if yes, get current one to pass to thread
            streamlit_ctx = script_run_context.get_script_run_ctx()
            if streamlit_ctx:
                # Set the context for this thread
                script_run_context.add_script_run_ctx(streamlit_ctx)
                logging.info("ScriptRunContext initialized for thread")
        except (ImportError, AttributeError) as e:
            # This is fine in non-streamlit environments
            logging.debug(f"Not running in Streamlit or couldn't set context: {e}")
            
        try:
            result[0] = func()
            completed[0] = True
        except Exception as e:
            exception[0] = e
            completed[0] = True
    
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    
    # Wait for completion or timeout
    start_time = time.time()
    while not completed[0] and (time.time() - start_time) < timeout:
        time.sleep(0.1)
    
    if not completed[0]:
        print(f"Operation timed out after {timeout} seconds")
        # Force disconnect to clean up resources
        try:
            connection_mgr = MCPConnectionManager.get_instance()
            if connection_mgr.connection_complete:
                print("Forcing disconnection due to timeout...")
                connection_mgr.disconnect()
        except Exception as e:
            print(f"Error during forced disconnection: {e}")
        return False
    
    if exception[0]:
        print(f"Operation failed with exception: {exception[0]}")
        return False
    
    return result[0]

if __name__ == "__main__":
    print("Starting MCP connection test...")
    result = run_with_timeout(test_mcp_connection, timeout=20)
    print(f"Test completed. Success: {result}")
