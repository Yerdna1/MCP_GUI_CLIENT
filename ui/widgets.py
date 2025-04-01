import json
import logging
import os
from typing import Optional

# Import QGridLayout
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox, QGroupBox, QComboBox, QLineEdit, QGridLayout
)
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtCore import QSettings

# Assuming ApiKeyDialog is needed by ChatWidget
from .dialogs import ApiKeyDialog, CONFIG_ORGANIZATION, CONFIG_APPLICATION

# Assuming worker and LLM functions are needed by ChatWidget
# These will eventually be imported from ui.workers and src.client.llm_interaction_fixed
# For now, define placeholders or assume they are globally available if running sequentially
# from .workers import LLMChatWorker # Placeholder
# from src.client.llm_interaction_fixed import get_ollama_response, get_anthropic_response # Placeholder

# Placeholder for Anthropic client if needed by ChatWidget
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

# Check for Gemini library at the module level
try:
    import google.generativeai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
# Add logging to check the result
logging.info(f"Gemini library available check: {GEMINI_AVAILABLE}")

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

class ChatWidget(QWidget):
    """Widget for LLM chat interface."""

    def __init__(self, connection_mgr):
        super().__init__()
        self.connection_mgr = connection_mgr # Needed to check connection status
        self.chat_history = []
        self.anthropic_client = None
        self.settings = QSettings(CONFIG_ORGANIZATION, CONFIG_APPLICATION)
        # Import worker here, assuming it's defined in workers.py
        try:
            from .workers import LLMChatWorker
            self.LLMChatWorker = LLMChatWorker
        except ImportError:
            self.LLMChatWorker = None
            logging.error("Could not import LLMChatWorker from ui.workers")

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
        if Anthropic is not None:
             llm_items.append("anthropic")
        # Use the module-level check result
        if GEMINI_AVAILABLE:
             llm_items.append("gemini")
        self.llm_type_combo.addItems(llm_items)

        llm_layout.addWidget(QLabel("LLM Type:"))
        llm_layout.addWidget(self.llm_type_combo)

        self.llm_model_combo = QComboBox()

        # Default Ollama models
        self.ollama_models = ["llama3.2:latest", "llama2", "mistral", "gemma"]
        # Default Anthropic models
        self.anthropic_models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
        # Default Gemini models (Using requested experimental model)
        self.gemini_models = ["gemini-2.5-pro-exp-03-25"] # User requested experimental model

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

        # --- Add Example Prompts Section ---
        prompts_group = QGroupBox("Example Prompts")
        # Use QGridLayout for 2 rows of 5
        prompts_layout = QGridLayout()

        # Define example prompts (10 total, focused on tools including read/write)
        example_prompts = [
            # Filesystem Tool Examples
            "List files in /projects using filesystem server.",
            "Read content of /projects/README.md using filesystem server.",
            "Write 'Hello World' to /projects/test_write.txt using filesystem server.",
            "Get file info for /projects/test_write.txt using filesystem server.",
            "Search for 'import' in /projects using filesystem server.",
            # GitHub Tool Examples
            "List tools on 'github' server.",
            "Search GitHub repos for 'MCP GUI'.",
            "Get README.md from 'modelcontextprotocol/mcp-python' repo via github server.",
            # Puppeteer Tool Examples
            "List tools on 'puppeteer' server.",
            "Fetch content of https://example.com using puppeteer server.",
        ]

        # Add buttons to the grid layout (2 rows, 5 columns)
        row, col = 0, 0
        for prompt_text in example_prompts:
            button = QPushButton(prompt_text)
            # Use lambda to capture the prompt text for the slot
            button.clicked.connect(lambda checked=False, text=prompt_text: self.set_chat_input(text))
            prompts_layout.addWidget(button, row, col)
            col += 1
            if col >= 5: # Move to next row after 5 buttons
                row += 1
                col = 0

        prompts_group.setLayout(prompts_layout)
        chat_layout.addWidget(prompts_group) # Add prompts group to chat layout
        # --- End Example Prompts Section ---


        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)

        self.setLayout(layout)

    def set_chat_input(self, text):
        """Sets the text of the chat input field."""
        self.chat_input.setText(text)
        self.chat_input.setFocus() # Set focus to input field after clicking button

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

            # Update Gemini client configuration
            try:
                import google.generativeai as genai
                google_key = dialog.getGoogleKey()
                if google_key:
                    genai.configure(api_key=google_key)
                    self.chat_display.append("<i>Google API key updated and client configured.</i>")
                    self.chat_display.append("")
                    # Optionally, set an instance variable if needed elsewhere
                    # self.gemini_configured = True
                else:
                    # Clear configuration if key is removed? Depends on desired behavior.
                    # For now, just notify. The handler checks env/settings on use.
                    self.chat_display.append("<i>Google API key removed. Client may use environment variable if set.</i>")
                    self.chat_display.append("")
                    # self.gemini_configured = False
            except ImportError:
                 pass # Gemini library not installed
            except Exception as e:
                 self.chat_display.append(f"<i>Error configuring Gemini with new API key: {str(e)}</i>")
                 self.chat_display.append("")
                 # self.gemini_configured = False


    def update_model_list(self, llm_type):
        """Update the model dropdown based on selected LLM type."""
        self.llm_model_combo.clear()
        if llm_type == "ollama":
            self.llm_model_combo.addItems(self.ollama_models)
        elif llm_type == "anthropic":
            self.llm_model_combo.addItems(self.anthropic_models)
            # Check if we have Anthropic client, if not, prompt to configure
            if not self.anthropic_client:
                self.chat_display.append("<i>Anthropic API key not configured. Please configure it using the button above.</i>")
                self.chat_display.append("")
        elif llm_type == "gemini":
             self.llm_model_combo.addItems(self.gemini_models)
             # Check if Gemini client is configured (via environment or settings)
             # A more robust check would involve trying to initialize the client here or checking a flag
             google_api_key = self.settings.value("google_api_key", os.getenv('GOOGLE_API_KEY', ""))
             if not google_api_key:
                  self.chat_display.append("<i>Google API key not configured. Please configure it using the button above.</i>")
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

        # Check if at least one server is connected using the new manager methods
        if not self.connection_mgr:
             self.chat_display.append("<i>Error: Connection manager not available.</i>")
             self.chat_display.append("")
             return

        statuses = self.connection_mgr.get_all_statuses()
        is_any_connected = any(status == "connected" for status in statuses.values())

        if not is_any_connected:
            self.chat_display.append("<i>Error: Not connected to any MCP server. Please use 'Connect All'.</i>")
            self.chat_display.append("")
            return

        # Check if worker class was imported
        if not self.LLMChatWorker:
             self.chat_display.append("<i>Error: LLMChatWorker could not be imported. Cannot send message.</i>")
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
        self.chat_worker = self.LLMChatWorker(
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
