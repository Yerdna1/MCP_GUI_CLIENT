#!/usr/bin/env python3
import os
import sys
import json
import logging

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mcp_client_windows.log"),
        logging.StreamHandler()
    ]
)

def convert_path_for_windows(path):
    """Convert Unix-style paths to Windows format for file operations."""
    if not path or not isinstance(path, str):
        return path
        
    if path.startswith('/'):
        # This is a Unix-style absolute path, convert to Windows format
        # For Docker-mounted directories, we need to map to the appropriate Windows paths
        if path.startswith('/projects/'):
            # This is a Docker mount, map to actual Windows path based on the mounting in mcp_config.json
            # By default /projects maps to the project root in Docker
            path = path.replace('/projects/', 'C:/___WORK/Ollama_MCP/')
        elif path.startswith('/home/user/'):
            # This is a common test path, map to the user's Documents folder
            path = path.replace('/home/user/', 'C:/Users/AndrejGalad/')
        else:
            # General Unix path, just convert slashes and add C: drive
            path = 'C:' + path.replace('/', '\\')
    
    # Replace any remaining forward slashes with backslashes
    path = path.replace('/', '\\')
    
    return path

def patch_tool_args(tool_name, args):
    """
    Patch tool arguments to fix paths for Windows.
    """
    if not args:
        return args
    
    patched_args = args.copy()
    
    # Handle common tool arguments that contain paths
    if tool_name in ['read_file', 'write_file', 'edit_file', 'list_directory', 
                    'directory_tree', 'get_file_info', 'create_directory']:
        if 'path' in patched_args:
            patched_args['path'] = convert_path_for_windows(patched_args['path'])
    
    # Handle specific tools with different parameter names
    if tool_name == 'move_file':
        if 'source' in patched_args:
            patched_args['source'] = convert_path_for_windows(patched_args['source'])
        if 'destination' in patched_args:
            patched_args['destination'] = convert_path_for_windows(patched_args['destination'])
    
    if tool_name == 'read_multiple_files' and 'paths' in patched_args:
        patched_args['paths'] = [convert_path_for_windows(p) for p in patched_args['paths']]
    
    if tool_name == 'search_files':
        if 'path' in patched_args:
            patched_args['path'] = convert_path_for_windows(patched_args['path'])
    
    logging.info(f"Original args: {args}")
    logging.info(f"Patched args: {patched_args}")
    
    return patched_args

def main():
    try:
        logging.info("Starting MCP PyQt Client with Windows path fixes")
        
        # Import our modules - we'll use the actual MCPPyQtClient class but fix the path handling
        from src.client.config_loader import load_mcp_config
        from src.mcp_connector_fixed import get_mcp_server_names, prepare_server_parameters, MCPConnectionManager
        
        # Apply monkey patch to fix path handling in MCPConnectionManager
        original_call_tool = MCPConnectionManager.call_tool
        
        def patched_call_tool(self, tool_name, tool_args):
            """Patched version of call_tool that fixes paths for Windows"""
            patched_args = patch_tool_args(tool_name, tool_args)
            logging.info(f"Calling tool {tool_name} with patched args: {patched_args}")
            return original_call_tool(self, tool_name, patched_args)
        
        # Apply the patch
        MCPConnectionManager.call_tool = patched_call_tool
        logging.info("Applied path fixing patch to MCPConnectionManager.call_tool")
        
        # Now import the PyQt client and run it
        from PyQt6.QtWidgets import QApplication
        from mcp_pyqt_client import MCPPyQtClient
        
        # Create and run the application
        app = QApplication(sys.argv)
        client = MCPPyQtClient()
        client.show()
        
        sys.exit(app.exec())
        
    except Exception as e:
        logging.error(f"Error starting application: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        print(f"ERROR: {str(e)}")
        print("See mcp_client_windows.log for details")

if __name__ == "__main__":
    main()
