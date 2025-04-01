import os
import sys
import json
import logging
from typing import Optional

# Add src directory to Python path relative to this file's location
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir) # Assumes ui is one level down
src_dir = os.path.join(project_root, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if project_root not in sys.path: # Add project root as well
     sys.path.insert(0, project_root)

# Import PyQt6 components
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QTextEdit, QListWidget,
    QListWidgetItem, QTabWidget, QSplitter, QMessageBox,
    QGroupBox, QScrollArea, QStatusBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# Import local UI components
from .dialogs import ApiKeyDialog
from .widgets import ToolInputWidget
from .chat_widget import ChatWidget
from .tool_controller import ToolController # Import the new controller
# Import updated workers for sequential/all operations
from .workers import MCPSequentialConnectionWorker, MCPDisconnectAllWorker, MCPToolCallWorker, LLMChatWorker

# Import core components
# Assuming config_loader is still in src/client
try:
    from src.client.config_loader import load_mcp_config
except ImportError:
     logging.error("Failed to import load_mcp_config from src.client.config_loader")
     # Define dummy function
     def load_mcp_config(*args, **kwargs): return {}

# Assuming connector and helpers are in src
try:
    from src.mcp_connector_fixed import MCPConnectionManager, get_mcp_server_names, prepare_server_parameters
except ImportError:
     logging.error("Failed to import from src.mcp_connector_fixed")
     # Define dummy classes/functions if needed to prevent crashes
     class MCPConnectionManager:
         connection_complete = False
         connected_server_name = "Error"
         tools = []
         def get_instance(cls): return cls()
         def connect(self, *args, **kwargs): return False
         def disconnect(self, *args, **kwargs): return True
         def call_tool(self, *args, **kwargs): raise ValueError("MCPConnectionManager not loaded")
     def get_mcp_server_names(*args, **kwargs): return ["Error loading servers"]
     def prepare_server_parameters(*args, **kwargs): return None


class MCPPyQtClient(QMainWindow):
    """A PyQt-based MCP client with sequential connection and multi-server support."""

    def __init__(self):
        super().__init__()
        # Load the configuration once
        self.mcp_config = load_mcp_config()
        # Instantiate the manager directly (no longer singleton)
        self.connection_mgr = MCPConnectionManager()
        # Get server names from the loaded (enabled) config
        self.server_names = get_mcp_server_names(self.mcp_config)
        self.current_tool_widget = None
        # Worker references
        self.connection_worker = None
        self.disconnection_worker = None
        # self.tool_call_worker = None # Worker is now managed by ToolController
        self.tool_controller = None # Add reference for the controller
        self.initUI()
        # Optionally, trigger auto-connect on startup
        # self.connect_all_servers()

    def initUI(self):
        """Initialize the user interface."""
        # Set window properties
        self.setWindowTitle("MCP PyQt Client (Sequential Connect)")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # Server connection control section
        server_group = QGroupBox("MCP Server Connections")
        server_layout = QHBoxLayout()

        # Connect/Disconnect buttons (Changed)
        self.connect_button = QPushButton("Connect All")
        self.connect_button.clicked.connect(self.connect_all_servers)
        self.connect_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")

        self.disconnect_button = QPushButton("Disconnect All")
        self.disconnect_button.clicked.connect(self.disconnect_all_servers)
        self.disconnect_button.setEnabled(False) # Initially disabled
        self.disconnect_button.setStyleSheet("background-color: #f44336; color: white; padding: 8px;")

        server_layout.addWidget(self.connect_button)
        server_layout.addWidget(self.disconnect_button)
        server_layout.addStretch(1) # Push buttons to the left

        server_group.setLayout(server_layout)
        main_layout.addWidget(server_group)

        # Create tabbed interface for different functions
        tabs = QTabWidget()

        # Tab 1: Manual Tool Selection
        manual_tab = QWidget()
        manual_layout = QVBoxLayout(manual_tab)

        # Create splitter for resizable sections
        manual_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Tools list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Tools list (Widget creation)
        tools_group = QGroupBox("Available Tools")
        tools_layout = QVBoxLayout()
        tools_list_widget = QListWidget() # Create instance
        tools_layout.addWidget(tools_list_widget)
        tools_group.setLayout(tools_layout)
        left_layout.addWidget(tools_group)

        # Right panel - Tool details and execution
        right_panel = QWidget()
        self.right_layout = QVBoxLayout(right_panel)

        # Tool input area (Widget creation)
        tool_container_widget = QWidget()
        tool_layout = QVBoxLayout(tool_container_widget)
        tool_layout.addWidget(QLabel("Select a server and connect, then select a tool."))

        # Tool result area (Widget creation)
        result_group = QGroupBox("Tool Results")
        result_layout = QVBoxLayout()
        result_text_widget = QTextEdit()
        result_text_widget.setReadOnly(True)
        result_layout.addWidget(result_text_widget)
        result_group.setLayout(result_layout)

        # Add widgets to right panel
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(tool_container_widget) # Use created widget instance

        self.right_layout.addWidget(scroll_area)
        self.right_layout.addWidget(result_group)

        # Add left and right panels to the splitter
        manual_splitter.addWidget(left_panel)
        manual_splitter.addWidget(right_panel)

        # Set initial sizes for the splitter
        manual_splitter.setSizes([300, 900]) # Adjust as needed

        # Add splitter to manual tab
        manual_layout.addWidget(manual_splitter)

        # Tab 2: Chat with LLM
        chat_tab = QWidget()
        # Pass the connection manager instance to ChatWidget
        self.chat_widget = ChatWidget(self.connection_mgr)
        chat_layout = QVBoxLayout(chat_tab)
        chat_layout.addWidget(self.chat_widget)

        # Add tabs to tab widget
        tabs.addTab(manual_tab, "Manual Tool Selection")
        tabs.addTab(chat_tab, "Chat with LLM") # ChatWidget needs access to the manager

        # Add tab widget to main layout
        main_layout.addWidget(tabs)

        # Status bar for connection status
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Not connected.")

        self.setCentralWidget(central_widget)

        # --- Instantiate ToolController ---
        self.tool_controller = ToolController(
            connection_mgr=self.connection_mgr,
            tools_list_widget=tools_list_widget,
            tool_container_widget=tool_container_widget,
            tool_layout=tool_layout,
            result_text_widget=result_text_widget
        )
        # Connect the list widget signal to the controller's slot
        tools_list_widget.itemClicked.connect(self.tool_controller.on_tool_selected)
        # --- End ToolController Instantiation ---


        # Update the UI state initially
        self.update_ui_state()

    def update_ui_state(self):
        """Update the UI state based on the status of all connections."""
        statuses = self.connection_mgr.get_all_statuses()
        connected_count = sum(1 for status in statuses.values() if status == "connected")
        connecting_count = sum(1 for status in statuses.values() if status == "connecting")
        disconnecting_count = sum(1 for status in statuses.values() if status == "disconnecting")
        error_count = sum(1 for status in statuses.values() if status == "error")
        total_servers = len(self.server_names) # Total configured enabled servers

        is_busy = connecting_count > 0 or disconnecting_count > 0
        is_any_connected = connected_count > 0

        self.connect_button.setEnabled(not is_busy and connected_count < total_servers)
        self.disconnect_button.setEnabled(not is_busy and is_any_connected)

        # Update status bar
        if is_busy:
            if connecting_count > 0:
                self.status_bar.showMessage(f"Connecting... ({connecting_count} active)")
            else:
                self.status_bar.showMessage(f"Disconnecting... ({disconnecting_count} active)")
        elif connected_count == total_servers and total_servers > 0:
            self.status_bar.showMessage(f"Connected to all {total_servers} servers.")
        elif is_any_connected:
            status_msg = f"Connected to {connected_count}/{total_servers} servers."
            if error_count > 0:
                status_msg += f" ({error_count} errors)"
            self.status_bar.showMessage(status_msg)
        else:
            status_msg = "Not connected."
            if error_count > 0:
                 status_msg += f" ({error_count} errors on last attempt)"
            self.status_bar.showMessage(status_msg)

        # Delegate tool list population and panel clearing to controller
        self.tool_controller.populate_tools_list()

        if not is_any_connected:
            self.tool_controller.clear_tool_details_panel()
            # Add placeholder label back via controller if needed, or handle in controller
            self.tool_controller.tool_layout.addWidget(QLabel("Connect to servers to see available tools."))

    # clear_tool_details_panel method removed (now in ToolController)

    def connect_all_servers(self):
        """Initiate sequential connection to all configured MCP servers."""
        if not self.server_names:
            QMessageBox.warning(self, "No Servers", "No enabled MCP servers found in configuration.")
            return

        self.status_bar.showMessage("Initiating connections...")
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.clear_tool_details_panel() # Clear old tool details
        self.tools_list.clear() # Clear old tools list

        # Create and start the sequential connection worker
        self.connection_worker = MCPSequentialConnectionWorker(self.connection_mgr, self.mcp_config)
        # Connect signals to handlers
        self.connection_worker.server_connection_attempt.connect(self.on_server_connection_attempt)
        self.connection_worker.server_connection_successful.connect(self.on_server_connection_successful)
        self.connection_worker.server_connection_failed.connect(self.on_server_connection_failed)
        self.connection_worker.all_connections_finished.connect(self.on_all_connections_finished)
        self.connection_worker.start()

    def on_server_connection_attempt(self, server_name):
        """Handle signal when connection attempt starts for a server."""
        self.status_bar.showMessage(f"Connecting to {server_name}...")
        # Optionally add visual indication in a server status list (future enhancement)

    def on_server_connection_successful(self, server_name, tools):
        """Handle signal when a server connects successfully."""
        logging.info(f"Successfully connected to {server_name} with {len(tools)} tools.")
        # Status bar will be updated fully at the end, but could show incremental success
        self.status_bar.showMessage(f"Connected to {server_name}... Waiting for others.")
        # Could potentially update the tools list incrementally here, but might be visually noisy.
        # Waiting for all_connections_finished is simpler.

    def on_server_connection_failed(self, server_name, error_msg):
        """Handle signal when a server fails to connect."""
        logging.error(f"Failed to connect to {server_name}: {error_msg}")
        # Show a non-blocking message or log, status bar updates at the end
        self.status_bar.showMessage(f"Failed to connect to {server_name}. Continuing...")
        # Optionally show a persistent error indicator for this server (future enhancement)

    def on_all_connections_finished(self, final_statuses):
        """Handle signal when all connection attempts are finished."""
        logging.info(f"All connection attempts finished. Final statuses: {final_statuses}")
        QMessageBox.information(self, "Connection Complete", "Finished attempting connections to all servers.")
        self.update_ui_state() # Update UI based on final states

    def disconnect_all_servers(self):
        """Disconnect from all currently connected MCP servers."""
        statuses = self.connection_mgr.get_all_statuses()
        if not any(s in ["connected", "error", "connecting"] for s in statuses.values()): # Only disconnect if needed
             logging.info("No servers seem to be connected or in an error state. Skipping disconnect all.")
             return

        self.status_bar.showMessage("Disconnecting from all servers...")
        self.disconnect_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.tool_controller.clear_tool_details_panel() # Delegate panel clearing

        # Create worker thread for disconnection
        self.disconnection_worker = MCPDisconnectAllWorker(self.connection_mgr)
        self.disconnection_worker.disconnection_complete.connect(self.on_disconnection_complete)
        self.disconnection_worker.start()

    def on_disconnection_complete(self, success):
        """Handle disconnection completion."""
        if success:
             QMessageBox.information(self, "Disconnection Complete", "Disconnected from all servers.")
        else:
             QMessageBox.warning(self, "Disconnection Issue", "There might have been issues during disconnection, but the client state has been reset.")
        self.update_ui_state() # Update UI to reflect disconnected state

    # Methods moved to ToolController:
    # - populate_tools_list
    # - on_tool_selected
    # - execute_tool
    # - handle_tool_result
    # - handle_tool_error

    # Need to keep reference to the widgets passed to controller if needed elsewhere,
    # but the methods operating on them are now in the controller.
    # We delegate calls in update_ui_state and connect_all_servers/disconnect_all_servers.

    def closeEvent(self, event):
        """Ensure disconnection from all servers when closing the window."""
        logging.info("Close event triggered. Disconnecting from all servers...")
        # Use a blocking call here as the app is closing anyway
        success = self.connection_mgr.disconnect_all(disconnect_timeout=5) # Call disconnect_all
        if not success:
             logging.warning("Disconnection during close event might not have been fully successful.")
        event.accept()
