#!/usr/bin/env python3
import os
import sys
import json
import logging
import asyncio
import threading
from typing import List, Dict, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import our modules
from src.client.config_loader import load_mcp_config
# Import connection manager and helper functions for single connection
from src.mcp_connector_fixed import MCPConnectionManager, get_mcp_server_names, prepare_server_parameters
from src.client.llm_interaction_fixed import get_ollama_response, get_anthropic_response

# Import PyQt6
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QTextEdit, QListWidget,
    QListWidgetItem, QTabWidget, QSplitter, QMessageBox,
    QGroupBox, QFormLayout, QScrollArea, QStatusBar, QLineEdit,
    QDialog, QDialogButtonBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings
from PyQt6.QtGui import QFont, QIcon, QTextCursor
# Ensure Anthropic is imported if used
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None
    logging.warning("Anthropic library not found. Anthropic models will not be available.")


# Config constants
CONFIG_ORGANIZATION = "MCP_PyQt_Client"
CONFIG_APPLICATION = "MCP_Client"

class ApiKeyDialog(QDialog):
    """Dialog for configuring API keys."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings(CONFIG_ORGANIZATION, CONFIG_APPLICATION)
        self.initUI()
        self.loadSettings()

    def initUI(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("API Key Configuration")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Anthropic API Key
        anthropic_group = QGroupBox("Anthropic")
        anthropic_layout = QFormLayout()

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key_input.setPlaceholderText("Enter Anthropic API key")
        anthropic_layout.addRow("API Key:", self.anthropic_key_input)

        self.save_anthropic_key = QCheckBox("Save API key")
        anthropic_layout.addRow("", self.save_anthropic_key)

        anthropic_group.setLayout(anthropic_layout)
        layout.addWidget(anthropic_group)

        # Add more API key sections as needed (OpenAI, etc.)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def loadSettings(self):
        """Load saved settings."""
        # Check if keys are saved
        if self.settings.value("save_anthropic_key", False, type=bool):
            self.anthropic_key_input.setText(self.settings.value("anthropic_api_key", ""))
            self.save_anthropic_key.setChecked(True)

    def saveSettings(self):
        """Save settings if requested."""
        if self.save_anthropic_key.isChecked():
            self.settings.setValue("anthropic_api_key", self.anthropic_key_input.text())
            self.settings.setValue("save_anthropic_key", True)
        else:
            self.settings.remove("anthropic_api_key")
            self.settings.setValue("save_anthropic_key", False)

    def getAnthropicKey(self):
        """Get the Anthropic API key."""
        return self.anthropic_key_input.text()

class MCPToolCallWorker(QThread):
    """Worker thread for calling MCP tools to avoid freezing the UI."""
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, connection_mgr, tool_name, tool_args):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.tool_name = tool_name
        self.tool_args = tool_args

    def run(self):
        try:
            result = self.connection_mgr.call_tool(self.tool_name, self.tool_args)
            self.result_ready.emit(result)
        except Exception as e:
            logging.error(f"Error in MCPToolCallWorker for tool {self.tool_name}: {e}")
            self.error_occurred.emit(f"Error calling tool {self.tool_name}: {str(e)}")

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
        self.anthropic_client = anthropic_client

    def run(self):
        try:
            if self.model_type == "ollama":
                response = get_ollama_response(self.connection_mgr, self.model_name, self.user_input)
            elif self.model_type == "anthropic" and self.anthropic_client:
                response = get_anthropic_response(self.connection_mgr,
                                                 self.anthropic_client,
                                                 self.model_name,
                                                 self.user_input)
            elif self.model_type == "anthropic" and not self.anthropic_client:
                 response = "Error: Anthropic client not available or API key missing."
            else:
                response = f"Error: Invalid model type '{self.model_type}'"

            self.response_ready.emit(response)
        except Exception as e:
            logging.error(f"Error in LLMChatWorker: {e}")
            self.error_occurred.emit(f"Error getting LLM response: {str(e)}")

class ToolInputWidget(QWidget):
    """Widget for displaying and gathering input for a tool's parameters."""

    # Remove server_name from init as it's implicit in single connection mode
    def __init__(self, tool):
        super().__init__()
        self.tool = tool
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Tool name and description
        name_label = QLabel(f"<b>{self.tool.name}</b>") # No server name needed
        name_label.setFont(QFont("Arial", 12))
        layout.addWidget(name_label)

        desc_label = QLabel(self.tool.description or "No description available")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Input schema section
        input_schema = getattr(self.tool, 'inputSchema', None) # Safely get schema
        if input_schema:
            schema_label = QLabel("Input Schema:")
            schema_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            layout.addWidget(schema_label)

            schema_text = QTextEdit()
            schema_text.setReadOnly(True)
            # Ensure schema is serializable
            try:
                schema_str = json.dumps(input_schema, indent=2)
            except TypeError:
                schema_str = str(input_schema) # Fallback
            schema_text.setText(schema_str)
            schema_text.setMaximumHeight(150)
            layout.addWidget(schema_text)

        # Arguments input
        args_label = QLabel("Tool Arguments (JSON):")
        args_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(args_label)

        self.args_input = QTextEdit()
        self.args_input.setPlaceholderText('{"param1": "value1", "param2": 123}')
        layout.addWidget(self.args_input)

        # Default empty JSON object
        self.args_input.setText("{}")

        # Execute button
        self.execute_button = QPushButton("Execute Tool")
        self.execute_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        layout.addWidget(self.execute_button)

        self.setLayout(layout)

    def get_arguments(self):
        """Get the arguments as a Python dictionary."""
        try:
            args_text = self.args_input.toPlainText()
            if not args_text.strip(): # Handle empty input
                return {}
            return json.loads(args_text)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"The arguments are not valid JSON: {str(e)}")
            return None

class MCPConnectionWorker(QThread):
    """Worker thread for MCP server connection (single server)."""
    # Define signals for connection results
    connection_successful = pyqtSignal(object)  # Pass tools list as object
    connection_failed = pyqtSignal(str) # Pass error message string

    # Takes server_name and server_params for single connection
    def __init__(self, connection_mgr, server_name, server_params):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.server_name = server_name
        self.server_params = server_params

    def run(self):
        try:
            # Call the single 'connect' method
            success = self.connection_mgr.connect(self.server_name, self.server_params)
            if success:
                # Pass the tools list for the connected server
                self.connection_successful.emit(self.connection_mgr.tools)
            else:
                # Pass connection error message
                error_msg = self.connection_mgr.connection_error or "Unknown connection error"
                self.connection_failed.emit(error_msg)
        except Exception as e:
            logging.error(f"Unexpected error during connect worker: {e}")
            self.connection_failed.emit(f"Unexpected error during connection: {str(e)}")


class MCPDisconnectionWorker(QThread):
    """Worker thread for MCP server disconnection (single server)."""
    # Define signal for disconnection result
    disconnection_complete = pyqtSignal(bool)

    def __init__(self, connection_mgr):
        super().__init__()
        self.connection_mgr = connection_mgr

    def run(self):
        try:
            # Call the single 'disconnect' method
            success = self.connection_mgr.disconnect()
            self.disconnection_complete.emit(success)
        except Exception as e:
            logging.error(f"Error during disconnect worker: {e}")
            self.disconnection_complete.emit(False) # Indicate potential issue


class ChatWidget(QWidget):
    """Widget for LLM chat interface."""

    def __init__(self, connection_mgr):
        super().__init__()
        self.connection_mgr = connection_mgr
        self.chat_history = []
        self.anthropic_client = None
        self.settings = QSettings(CONFIG_ORGANIZATION, CONFIG_APPLICATION)
        self.init_anthropic_client()
        self.initUI()

    def init_anthropic_client(self):
        """Initialize the Anthropic client with API key if available."""
        if Anthropic is None: return # Skip if library not found

        anthropic_api_key = self.settings.value("anthropic_api_key", "")
        if anthropic_api_key:
            try:
                self.anthropic_client = Anthropic(api_key=anthropic_api_key)
                logging.info("Anthropic client initialized with saved API key")
            except Exception as e:
                logging.error(f"Could not initialize Anthropic client with saved key: {e}")
                self.anthropic_client = None # Ensure it's None on failure

    def initUI(self):
        layout = QVBoxLayout()

        # LLM selection and API key configuration
        llm_group = QGroupBox("LLM Selection")
        llm_layout = QHBoxLayout()

        self.llm_type_combo = QComboBox()
        llm_items = ["ollama"]
        if Anthropic is not None: # Only add if library exists
             llm_items.append("anthropic")
        self.llm_type_combo.addItems(llm_items)

        llm_layout.addWidget(QLabel("LLM Type:"))
        llm_layout.addWidget(self.llm_type_combo)

        self.llm_model_combo = QComboBox()

        # Default Ollama models
        self.ollama_models = ["llama3.2:latest", "llama2", "mistral", "gemma"]
        # Default Anthropic models
        self.anthropic_models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]

        self.llm_model_combo.addItems(self.ollama_models) # Default to Ollama
        llm_layout.addWidget(QLabel("Model:"))
        llm_layout.addWidget(self.llm_model_combo)

        # API key configuration button
        self.api_key_button = QPushButton("Configure API Keys")
        self.api_key_button.clicked.connect(self.show_api_key_dialog)
        llm_layout.addWidget(self.api_key_button)

        # Connect change event
        self.llm_type_combo.currentTextChanged.connect(self.update_model_list)

        llm_group.setLayout(llm_layout)
        layout.addWidget(llm_group)

        # Chat display
        chat_group = QGroupBox("Chat")
        chat_layout = QVBoxLayout()

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(300)
        chat_layout.addWidget(self.chat_display)

        # Chat input area
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type your message here...")
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        input_layout.addWidget(self.send_button)

        chat_layout.addLayout(input_layout)

        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)

        self.setLayout(layout)

    def show_api_key_dialog(self):
        """Show the API key configuration dialog."""
        dialog = ApiKeyDialog(self)
        if dialog.exec():
            dialog.saveSettings()

            # Update the Anthropic client with the new API key
            if Anthropic is not None:
                anthropic_key = dialog.getAnthropicKey()
                if anthropic_key:
                    try:
                        self.anthropic_client = Anthropic(api_key=anthropic_key)
                        self.chat_display.append("<i>Anthropic API key updated.</i>")
                        self.chat_display.append("")
                    except Exception as e:
                        self.chat_display.append(f"<i>Error initializing Anthropic with new API key: {str(e)}</i>")
                        self.chat_display.append("")
                        self.anthropic_client = None # Reset on error
                else:
                     self.anthropic_client = None # Clear client if key removed
                     self.chat_display.append("<i>Anthropic API key removed.</i>")
                     self.chat_display.append("")


    def update_model_list(self, llm_type):
        """Update the model dropdown based on selected LLM type."""
        self.llm_model_combo.clear()
        if llm_type == "ollama":
            self.llm_model_combo.addItems(self.ollama_models)
        elif llm_type == "anthropic":
            self.llm_model_combo.addItems(self.anthropic_models)
            # Check if we have Anthropic client, if not, prompt to configure
            if not self.anthropic_client:
                self.chat_display.append("<i>Anthropic API key not configured. Please configure it to use Anthropic models.</i>")
                self.chat_display.append("")

    def send_message(self):
        """Send user message to the LLM."""
        user_input = self.chat_input.text().strip()
        if not user_input:
            return

        # Clear input field
        self.chat_input.clear()

        # Display user message
        self.chat_display.append(f"<b>You:</b> {user_input}")
        self.chat_display.append("")

        # Make sure we're connected to an MCP server (single connection check)
        if not self.connection_mgr or not self.connection_mgr.connection_complete:
            self.chat_display.append("<i>Error: Not connected to an MCP server. Please select and connect first.</i>")
            self.chat_display.append("")
            return

        # Show typing indicator
        self.chat_display.append("<i>AI is thinking...</i>")
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End) # Ensure cursor is at end

        # Get LLM type and model
        llm_type = self.llm_type_combo.currentText()
        llm_model = self.llm_model_combo.currentText()

        # Check if Anthropic is available and selected
        if llm_type == "anthropic" and not self.anthropic_client:
            # Remove typing indicator
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()

            self.chat_display.append("<i>Error: Anthropic API key not configured. Please configure it using the button above.</i>")
            self.chat_display.append("")
            return

        # Create and start worker thread
        self.chat_worker = LLMChatWorker(
            self.connection_mgr,
            llm_type,
            llm_model,
            user_input,
            self.anthropic_client if llm_type == "anthropic" else None
        )

        self.chat_worker.response_ready.connect(self.handle_llm_response)
        self.chat_worker.error_occurred.connect(self.handle_llm_error)
        self.chat_worker.start()

    def handle_llm_response(self, response):
        """Handle the response from the LLM."""
        # Remove typing indicator
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Check if the last line is the thinking indicator before removing
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        if cursor.selectedText().strip() == "AI is thinking...":
             cursor.removeSelectedText()
             # Remove potential extra newline
             cursor.movePosition(QTextCursor.MoveOperation.End)
             cursor.select(QTextCursor.SelectionType.LineUnderCursor)
             if not cursor.selectedText().strip():
                 cursor.removeSelectedText()

        # Display assistant message
        self.chat_display.append(f"<b>AI:</b> {response}")
        self.chat_display.append("")

        # Scroll to bottom
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    def handle_llm_error(self, error_msg):
        """Handle an error from the LLM."""
        # Remove typing indicator
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Check if the last line is the thinking indicator before removing
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        if cursor.selectedText().strip() == "AI is thinking...":
             cursor.removeSelectedText()
             # Remove potential extra newline
             cursor.movePosition(QTextCursor.MoveOperation.End)
             cursor.select(QTextCursor.SelectionType.LineUnderCursor)
             if not cursor.selectedText().strip():
                 cursor.removeSelectedText()

        # Display error message
        self.chat_display.append(f"<i>Error: {error_msg}</i>")
        self.chat_display.append("")

class MCPPyQtClient(QMainWindow):
    """A PyQt-based MCP client with a graphical interface (Single Server Connection)."""

    def __init__(self):
        super().__init__()
        # Load the configuration once (it returns enabled servers)
        self.mcp_config = load_mcp_config()
        self.connection_mgr = MCPConnectionManager.get_instance()
        # Get server names from the loaded (enabled) config
        self.server_names = get_mcp_server_names(self.mcp_config) # Use the loaded config
        self.selected_server_name: Optional[str] = None
        self.server_params = None # Store params for the selected server
        self.connected: bool = False # Use connection_mgr.connection_complete
        self.current_tool_widget = None
        self.connection_worker = None
        self.disconnection_worker = None
        self.tool_call_worker = None
        self.initUI()
        # No auto-connect on startup for single-server mode

    def initUI(self):
        """Initialize the user interface."""
        # Set window properties
        self.setWindowTitle("MCP PyQt Client (Single Server)")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # Server selection section (Restored)
        server_group = QGroupBox("MCP Server Connection")
        server_layout = QHBoxLayout()

        # Server dropdown
        self.server_combo = QComboBox()
        self.server_combo.addItems(self.server_names if self.server_names else ["No servers available"])
        server_layout.addWidget(QLabel("Select MCP Server:"))
        server_layout.addWidget(self.server_combo)

        # Connect/Disconnect buttons (Restored)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_server)
        self.connect_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect_from_server)
        self.disconnect_button.setEnabled(False) # Initially disabled
        self.disconnect_button.setStyleSheet("background-color: #f44336; color: white; padding: 8px;")

        server_layout.addWidget(self.connect_button)
        server_layout.addWidget(self.disconnect_button)

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

        # Tools list
        tools_group = QGroupBox("Available Tools")
        tools_layout = QVBoxLayout()

        self.tools_list = QListWidget()
        self.tools_list.itemClicked.connect(self.on_tool_selected)
        tools_layout.addWidget(self.tools_list)

        tools_group.setLayout(tools_layout)
        left_layout.addWidget(tools_group)

        # Right panel - Tool details and execution
        right_panel = QWidget()
        self.right_layout = QVBoxLayout(right_panel)

        # Tool input area (will be populated when a tool is selected)
        self.tool_container = QWidget()
        self.tool_layout = QVBoxLayout(self.tool_container)
        self.tool_layout.addWidget(QLabel("Select a server and connect, then select a tool."))

        # Tool result area
        result_group = QGroupBox("Tool Results")
        result_layout = QVBoxLayout()

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        result_layout.addWidget(self.result_text)

        result_group.setLayout(result_layout)

        # Add widgets to right panel
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.tool_container)

        self.right_layout.addWidget(scroll_area)
        self.right_layout.addWidget(result_group)

        # Add left and right panels to the splitter
        manual_splitter.addWidget(left_panel)
        manual_splitter.addWidget(right_panel)

        # Set initial sizes for the splitter
        manual_splitter.setSizes([300, 900])

        # Add splitter to manual tab
        manual_layout.addWidget(manual_splitter)

        # Tab 2: Chat with LLM
        chat_tab = QWidget()
        self.chat_widget = ChatWidget(self.connection_mgr)
        chat_layout = QVBoxLayout(chat_tab)
        chat_layout.addWidget(self.chat_widget)

        # Add tabs to tab widget
        tabs.addTab(manual_tab, "Manual Tool Selection")
        tabs.addTab(chat_tab, "Chat with LLM")

        # Add tab widget to main layout
        main_layout.addWidget(tabs)

        # Status bar for connection status
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Not connected.")

        self.setCentralWidget(central_widget)

        # Update the UI state initially
        self.update_ui_state()

    def update_ui_state(self):
        """Update the UI state based on single connection status."""
        self.connected = self.connection_mgr.connection_complete

        if self.connected:
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.server_combo.setEnabled(False) # Disable selection while connected
            self.status_bar.showMessage(f"Connected to {self.connection_mgr.connected_server_name}")
            self.populate_tools_list() # Populate with tools from the single connection
        else:
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.server_combo.setEnabled(True) # Enable selection
            self.tools_list.clear()
            self.status_bar.showMessage("Not connected.")

            # Clear tool details
            for i in reversed(range(self.tool_layout.count())):
                widget = self.tool_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)

            self.tool_layout.addWidget(QLabel("Select a server and connect, then select a tool."))

    def connect_to_server(self):
        """Connect to the selected MCP server."""
        if not self.server_names:
            QMessageBox.warning(self, "No Servers", "No MCP servers found in configuration.")
            return

        self.selected_server_name = self.server_combo.currentText()
        if self.selected_server_name == "No servers available":
            QMessageBox.warning(self, "No Servers", "No MCP servers found in configuration.")
            return

        # Use the loaded config to prepare params for the selected server
        self.server_params = prepare_server_parameters(self.selected_server_name, self.mcp_config)
        if not self.server_params:
            QMessageBox.critical(self, "Configuration Error",
                                 f"Failed to prepare parameters for server '{self.selected_server_name}'.")
            return

        self.status_bar.showMessage(f"Connecting to {self.selected_server_name}...")
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.server_combo.setEnabled(False)

        # Create worker thread for single connection
        self.connection_worker = MCPConnectionWorker(self.connection_mgr, self.selected_server_name, self.server_params)
        self.connection_worker.connection_successful.connect(self.on_connection_successful)
        self.connection_worker.connection_failed.connect(self.on_connection_failed)
        self.connection_worker.start()


    def on_connection_successful(self, tools):
        """Handle successful connection to the selected server."""
        # self.connected is updated by update_ui_state called below
        QMessageBox.information(self, "Connection Successful",
                               f"Connected to {self.connection_mgr.connected_server_name} with {len(tools)} tools available.")
        self.update_ui_state()

    def on_connection_failed(self, error_msg):
        """Handle failed connection to the selected server."""
        # self.connected is updated by update_ui_state called below
        QMessageBox.critical(self, "Connection Failed", f"Failed to connect to {self.selected_server_name}: {error_msg}")
        self.update_ui_state() # Re-enable connect button etc.

    def disconnect_from_server(self):
        """Disconnect from the current MCP server."""
        if not self.connection_mgr.connection_complete:
             return

        self.status_bar.showMessage(f"Disconnecting from {self.connection_mgr.connected_server_name}...")
        self.disconnect_button.setEnabled(False)
        self.connect_button.setEnabled(False) # Disable connect during disconnect

        # Create worker thread for disconnection
        self.disconnection_worker = MCPDisconnectionWorker(self.connection_mgr)
        self.disconnection_worker.disconnection_complete.connect(self.on_disconnection_complete)
        self.disconnection_worker.start()

    def on_disconnection_complete(self, success):
        """Handle disconnection completion."""
        # self.connected is updated by update_ui_state called below
        if success:
             QMessageBox.information(self, "Disconnection Complete", f"Disconnected from {self.selected_server_name}.") # Use stored name
        else:
             QMessageBox.warning(self, "Disconnection Issue", "There might have been issues during disconnection, but the client state has been reset.")
        self.selected_server_name = None # Clear selected server on disconnect
        self.update_ui_state()

    def populate_tools_list(self):
        """Populate the tools list with tools from the single connected server."""
        self.tools_list.clear()
        # Use tools directly from the manager instance
        tools = self.connection_mgr.tools

        if not tools:
            self.tools_list.addItem("No tools available for this server.")
            return

        # Sort tools alphabetically by name for consistency
        tools.sort(key=lambda tool: tool.name)

        for tool in tools:
            item = QListWidgetItem(tool.name) # No server name needed in item text
            item.setData(Qt.ItemDataRole.UserRole, tool.name) # Store actual tool name
            item.setToolTip(tool.description if hasattr(tool, 'description') else "No description")
            self.tools_list.addItem(item)

    def on_tool_selected(self, item):
        """Handle tool selection from the list."""
        if not self.connection_mgr.connection_complete or not self.connection_mgr.tools:
            return

        tool_name = item.data(Qt.ItemDataRole.UserRole) # Get stored tool name
        if not tool_name:
             return # Should not happen if populated correctly

        selected_tool = None
        # Find tool in the manager's list
        for tool in self.connection_mgr.tools:
            if tool.name == tool_name:
                selected_tool = tool
                break

        if not selected_tool:
            logging.error(f"Selected tool '{tool_name}' not found in connected server's list.")
            return

        # Clear current tool widget
        for i in reversed(range(self.tool_layout.count())):
            widget = self.tool_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Create and add the new tool widget (no server name needed)
        self.current_tool_widget = ToolInputWidget(selected_tool)
        self.current_tool_widget.execute_button.clicked.connect(
            lambda checked=False, tn=selected_tool.name: self.execute_tool(tn)) # Use lambda to capture tool name

        self.tool_layout.addWidget(self.current_tool_widget)

    def execute_tool(self, tool_name):
        """Execute the selected tool with the provided arguments."""
        if not self.current_tool_widget or self.current_tool_widget.tool.name != tool_name:
            logging.warning(f"Tool widget mismatch or not found for {tool_name}")
            return

        args = self.current_tool_widget.get_arguments()
        if args is None:  # Invalid JSON
            return

        self.result_text.clear()
        self.result_text.append(f"Executing tool: {tool_name}")
        self.result_text.append(f"Arguments: {json.dumps(args, indent=2)}")
        self.result_text.append("\nWaiting for results...")

        # Create and start the worker thread for tool call
        self.tool_call_worker = MCPToolCallWorker(self.connection_mgr, tool_name, args)
        self.tool_call_worker.result_ready.connect(self.handle_tool_result)
        self.tool_call_worker.error_occurred.connect(self.handle_tool_error)
        self.tool_call_worker.start()

    def handle_tool_result(self, result):
        """Handle the result from a tool execution."""
        self.result_text.clear()

        if result is None:
            self.result_text.append("No result returned from tool.")
            return

        try:
            # Attempt to pretty-print if it's likely JSON, otherwise just stringify
            if isinstance(result, (dict, list)):
                result_str = json.dumps(result, indent=2)
            elif hasattr(result, 'content') and isinstance(result.content, (dict, list)):
                 result_str = json.dumps(result.content, indent=2)
            elif hasattr(result, 'content'):
                 result_str = str(result.content)
            else:
                result_str = str(result)

            self.result_text.append("Tool execution successful:\n")
            self.result_text.append(result_str)
        except Exception as e:
            logging.error(f"Error formatting tool result: {e}")
            self.result_text.append(f"Tool execution successful, but result formatting failed:\n{str(result)}")

        # Scroll to top
        self.result_text.verticalScrollBar().setValue(0)

    def handle_tool_error(self, error_msg):
        """Handle an error during tool execution."""
        self.result_text.clear()
        self.result_text.append("Tool execution failed:\n")
        self.result_text.append(error_msg)

    def closeEvent(self, event):
        """Ensure disconnection when closing the window."""
        logging.info("Close event triggered. Disconnecting from server...")
        # Use a blocking call here as the app is closing anyway
        self.connection_mgr.disconnect(disconnect_timeout=5) # Call single disconnect
        event.accept()

# Note: The main execution block is now in improved_mcp_client.py
# This file should only contain the class definitions.

</final_file_content>

IMPORTANT: For any future changes to this file, use the final_file_content shown above as your reference. This content reflects the current state of the file, including any auto-formatting (e.g., if you used single quotes but the formatter converted them to double quotes). Always base your SEARCH/REPLACE operations on this final version to ensure accuracy.

<environment_details>
# VSCode Visible Files
mcp_pyqt_client.py

# VSCode Open Tabs
src/mcp_connector_fixed.py
mcp_pyqt_client.py

# Actively Running Terminals
## Original command: `python improved_mcp_client.py`
## Original command: `python improved_mcp_client.py`

# Current Time
4/2/2025, 12:21:11 AM (Europe/Bratislava, UTC+2:00)

# Current Mode
ACT MODE
</environment_details>
