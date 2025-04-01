#!/usr/bin/env python3
import os
import sys
import json
import logging
import traceback
from typing import Any, Dict, Optional
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
        logging.FileHandler("improved_mcp_client.log"),
        logging.StreamHandler()
    ]
)

def fix_path(path):
    """
    Convert between Unix and Windows paths intelligently.

    This function handles:
    1. Unix-style absolute paths (/home/user/...)
    2. Windows paths that might be missing drive letters
    3. Relative paths (preserving them)
    """
    if not path or not isinstance(path, str):
        return path

    logging.debug(f"Fixing path: {path}")

    # Handle specific path patterns first
    if path.startswith('/home/user'):
        # Common path pattern from models, convert to user's Documents
        windows_path = path.replace('/home/user', os.path.join(os.environ.get('USERPROFILE', 'C:/Users/AndrejGalad')))
        windows_path = windows_path.replace('/', '\\')
        logging.debug(f"Converted /home/user path to: {windows_path}")
        return windows_path

    if path.startswith('/projects/'):
        # Docker mounted directory
        windows_path = path.replace('/projects/', 'C:/___WORK/Ollama_MCP/')
        windows_path = windows_path.replace('/', '\\')
        logging.debug(f"Converted /projects path to: {windows_path}")
        return windows_path

    # If it's a relative path, keep it as is (but normalize slashes)
    if not (path.startswith('/') or (len(path) > 1 and path[1] == ':')):
        normalized_path = path.replace('/', '\\')
        logging.debug(f"Preserved relative path, normalized to: {normalized_path}")
        return normalized_path

    # Handle drive-less Windows path (missing C:)
    if path.startswith('/'):
        windows_path = 'C:' + path.replace('/', '\\')
        logging.debug(f"Added drive letter to path: {windows_path}")
        return windows_path

    # Already Windows path with drive letter, just normalize slashes
    windows_path = path.replace('/', '\\')
    logging.debug(f"Normalized existing Windows path: {windows_path}")
    return windows_path

def log_method(func):
    """Decorator to log method calls for debugging"""
    def wrapper(*args, **kwargs):
        logging.debug(f"CALLING: {func.__name__} with args: {args[1:]} kwargs: {kwargs}")
        result = func(*args, **kwargs)
        logging.debug(f"RESULT from {func.__name__}: {result}")
        return result
    return wrapper

# Add a custom write_file function to supplement the MCP tools
def write_file_direct(path, content):
    """
    Write content directly to a file - this is a backup method in case the MCP tool fails.

    Args:
        path: The file path to write to
        content: The content to write

    Returns:
        Dict with success or error information
    """
    try:
        # Ensure the path is Windows-friendly
        fixed_path = fix_path(path)

        # Make sure the directory exists
        directory = os.path.dirname(fixed_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        # Write the file
        with open(fixed_path, 'w', encoding='utf-8') as file:
            file.write(content)

        logging.info(f"Successfully wrote to file: {fixed_path}")
        return {
            "success": True,
            "path": fixed_path,
            "message": f"File successfully written to {fixed_path}"
        }
    except Exception as e:
        error_msg = f"Error writing to file {path}: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        return {
            "success": False,
            "error": True,
            "message": error_msg
        }

def patch_mcp_tools():
    """Apply all necessary patches to the MCP connector and tools"""
    logging.info("Patching MCP components for Windows compatibility")

    from src.mcp_connector_fixed import MCPConnectionManager

    # Save original methods before patching
    original_call_tool = MCPConnectionManager.call_tool

    @log_method
    def patched_call_tool(self, tool_name, tool_args):
        """Patched version of call_tool with Windows path fixes and better error handling"""
        # Make a copy of the arguments
        if tool_args is None:
            patched_args = {}
        else:
            patched_args = tool_args.copy()

        # Special handling for write_file to ensure it works
        if tool_name == 'write_file':
            try:
                logging.info(f"Write file requested: {patched_args}")
                # Make sure path is in Windows format
                if 'path' in patched_args:
                    patched_args['path'] = fix_path(patched_args['path'])

                # Try direct file writing first
                if 'path' in patched_args and 'content' in patched_args:
                    direct_result = write_file_direct(
                        patched_args['path'],
                        patched_args['content']
                    )
                    logging.info(f"Direct file write result: {direct_result}")

                    # If direct writing succeeded, we can return it
                    if direct_result.get('success', False):
                        return direct_result

                    # Otherwise, fall through to the MCP implementation
                    logging.info("Direct file write failed, trying MCP tool...")
            except Exception as e:
                logging.error(f"Error in write_file preprocessing: {str(e)}")
                logging.error(traceback.format_exc())
                # Continue to normal processing

        # Fix paths in common file operation tools
        if tool_name in ['read_file', 'edit_file', 'list_directory',
                        'directory_tree', 'get_file_info', 'create_directory']:
            if 'path' in patched_args:
                patched_args['path'] = fix_path(patched_args['path'])

        # Fix paths in tools with different parameter names
        elif tool_name == 'move_file':
            if 'source' in patched_args:
                patched_args['source'] = fix_path(patched_args['source'])
            if 'destination' in patched_args:
                patched_args['destination'] = fix_path(patched_args['destination'])

        elif tool_name == 'read_multiple_files' and 'paths' in patched_args:
            if isinstance(patched_args['paths'], list):
                patched_args['paths'] = [fix_path(p) for p in patched_args['paths']]

        elif tool_name == 'search_files' and 'path' in patched_args:
            patched_args['path'] = fix_path(patched_args['path'])

        # Fix GitHub tool missing parameters
        elif tool_name == 'search_repositories' and 'q' in patched_args and not patched_args['q']:
            # Add a default query if empty
            patched_args['q'] = 'topic:python'
            logging.info(f"Added default query for empty search_repositories: {patched_args}")

        elif tool_name == 'create_repository' and 'name' in patched_args:
            # Make sure repository has other needed fields
            if 'description' not in patched_args:
                patched_args['description'] = f"Repository created via MCP: {patched_args['name']}"
            if 'private' not in patched_args:
                patched_args['private'] = True
            logging.info(f"Enhanced create_repository parameters: {patched_args}")

        try:
            logging.info(f"Calling tool {tool_name} with patched args: {patched_args}")
            result = original_call_tool(self, tool_name, patched_args)
            logging.info(f"Tool result: {result}")
            return result
        except Exception as e:
            logging.error(f"Error in call_tool: {str(e)}")
            logging.error(traceback.format_exc())
            # Return a graceful error instead of crashing
            return {
                "error": True,
                "message": f"Error executing tool {tool_name}: {str(e)}"
            }

    # Apply the patches
    MCPConnectionManager.call_tool = patched_call_tool

    # Add simple property to track if patched
    MCPConnectionManager.is_patched = True

    logging.info("Successfully applied all patches to MCP components")

def main():
    try:
        logging.info("Starting Improved MCP PyQt Client")

        # Apply all patches
        patch_mcp_tools()

        # Import PyQt and create the application
        from PyQt6.QtWidgets import QApplication
        # Import the main window from the new ui module
        try:
            from ui.main_window import MCPPyQtClient
        except ImportError as import_err:
             logging.error(f"Failed to import MCPPyQtClient from ui.main_window: {import_err}")
             print("ERROR: Could not find the main GUI window class.")
             sys.exit(1)


        # Create and run the application
        app = QApplication(sys.argv)
        client = MCPPyQtClient() # This class needs the updated MCPConnectionManager logic
        client.show()

        sys.exit(app.exec())

    except Exception as e:
        logging.error(f"Error starting application: {str(e)}")
        logging.error(traceback.format_exc())
        print(f"ERROR: {str(e)}")
        print("See improved_mcp_client.log for details")

if __name__ == "__main__":
    main()
