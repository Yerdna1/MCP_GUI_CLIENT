#!/usr/bin/env python3
import os
import sys
import traceback
import logging

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)

def main():
    try:
        logging.info("Starting MCP PyQt Client with debug info")
        
        # Add src directory to Python path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.join(current_dir, 'src')
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        logging.info(f"Current dir: {current_dir}")
        logging.info(f"Src dir: {src_dir}")
        logging.info(f"Python path: {sys.path}")
        
        # Try importing PyQt6
        logging.info("Importing PyQt6...")
        from PyQt6.QtWidgets import QApplication
        logging.info("PyQt6 imported successfully")
        
        # Import our main application
        logging.info("Importing main application components...")
        from mcp_pyqt_client import MCPPyQtClient
        
        # Create and run the application
        logging.info("Creating application...")
        app = QApplication(sys.argv)
        client = MCPPyQtClient()
        logging.info("Showing main window...")
        client.show()
        
        logging.info("Entering application main loop...")
        sys.exit(app.exec())
        
    except Exception as e:
        logging.error(f"Error starting application: {str(e)}")
        logging.error(traceback.format_exc())
        print(f"ERROR: {str(e)}")
        print("See debug.log for details")

if __name__ == "__main__":
    main()
