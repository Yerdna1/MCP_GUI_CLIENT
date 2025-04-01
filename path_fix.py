#!/usr/bin/env python3
import os
import sys
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def convert_path_for_windows(path):
    """Convert Unix-style paths to Windows format for file operations."""
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

def test_path_conversion():
    """Test the path conversion functions."""
    test_paths = [
        '/home/user/Documents/example.txt',
        '/projects/src/main.py',
        '/var/log/app.log',
        'C:/Users/AndrejGalad/Desktop/file.txt'  # Already Windows format
    ]
    
    print("Testing path conversion:")
    for path in test_paths:
        windows_path = convert_path_for_windows(path)
        print(f"Unix: {path} -> Windows: {windows_path}")
    
    # Test tool argument patching
    test_args = {
        'read_file': {'path': '/home/user/Documents/example.txt'},
        'move_file': {'source': '/projects/src/old.py', 'destination': '/projects/src/new.py'},
        'read_multiple_files': {'paths': ['/home/user/file1.txt', '/home/user/file2.txt']},
        'search_files': {'path': '/projects', 'pattern': '*.py'}
    }
    
    print("\nTesting tool argument patching:")
    for tool_name, args in test_args.items():
        patched = patch_tool_args(tool_name, args)
        print(f"{tool_name}: {args} -> {patched}")

if __name__ == "__main__":
    test_path_conversion()
