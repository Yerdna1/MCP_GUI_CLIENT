import json
import logging
import os
from typing import Optional

# Import QGridLayout and other necessary Qt components
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox, QGroupBox, QComboBox, QLineEdit, QGridLayout
)
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtCore import QSettings

# Import necessary local components
from .dialogs import ApiKeyDialog, CONFIG_ORGANIZATION, CONFIG_APPLICATION
from .workers import LLMChatWorker # Assuming LLMChatWorker is in workers.py

# Placeholder for Anthropic client
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


class ChatWidget(QWidget):
    """Widget for LLM chat interface."""

    def __init__(self, connection_mgr):
        super().__init__()
        self.connection_mgr = connection_mgr # Needed to check connection status
        # Use conversation_history from the shared state module
        try:
            from src.client.conversation_state import conversation_history
            self.chat_history = conversation_history
        except ImportError:
            self.chat_history = [] # Fallback
            logging.error("Could not import shared conversation_history for ChatWidget")

        self.anthropic_client = None
        self.settings = QSettings(CONFIG_ORGANIZATION, CONFIG_APPLICATION)
        # Import worker here, assuming it's defined in workers.py
        try:
            # from .workers import LLMChatWorker # Already imported above
            self.LLMChatWorker = LLMChatWorker
        except NameError: # If LLMChatWorker wasn't imported successfully
            self.LLMChatWorker = None
            logging.error("LLMChatWorker not available")

        self.init_anthropic_client()
        # Initialize Gemini client configuration check (doesn't create client yet)
        self.check_gemini_config()
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

    def check_gemini_config(self):
        """Checks if Gemini API key is configured."""
        self.gemini_configured = False
        if GEMINI_AVAILABLE:
            google_api_key = self.settings.value("google_api_key", os.getenv('GOOGLE_API_KEY', ""))
            if google_api_key:
                self.gemini_configured = True
                # Configuration now happens within the handler before the call
                logging.info("Gemini API key found in settings or environment.")
            else:
                logging.info("Gemini API key not found.")
        else:
            logging.info("Gemini library not available.")


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

            # Update Gemini client configuration status check
            self.check_gemini_config()
            if self.gemini_configured:
                 self.chat_display.append("<i>Google API key updated. Client will configure on next use.</i>")
                 self.chat_display.append("")
            else:
                 google_key_removed = not dialog.settings.value("save_google_key", False, type=bool)
                 if google_key_removed:
                      self.chat_display.append("<i>Google API key removed.</i>")
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
                self.chat_display.append("<i>Anthropic API key not configured. Please configure it using the button above.</i>")
                self.chat_display.append("")
        elif llm_type == "gemini":
             self.llm_model_combo.addItems(self.gemini_models)
             # Check if Gemini client is configured
             if not self.gemini_configured:
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

        # Check API key configurations before starting worker
        if llm_type == "anthropic" and not self.anthropic_client:
            self.handle_llm_error("Anthropic API key not configured.") # Use error handler
            return
        if llm_type == "gemini" and not self.gemini_configured:
             self.handle_llm_error("Google API key not configured.") # Use error handler
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
