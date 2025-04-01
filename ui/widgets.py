import json
import logging
from typing import Optional

# Import QGridLayout and other necessary Qt components
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QMessageBox, QGroupBox, QComboBox, QLineEdit, QGridLayout
)
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtCore import QSettings

# Assuming ApiKeyDialog is needed by ChatWidget - Removed as ChatWidget is moved
# from .dialogs import ApiKeyDialog, CONFIG_ORGANIZATION, CONFIG_APPLICATION

# Placeholder for Anthropic client - Removed as ChatWidget is moved
# try:
#     from anthropic import Anthropic
# except ImportError:
#     Anthropic = None

# Check for Gemini library - Removed as ChatWidget is moved
# try:
#     import google.generativeai
#     GEMINI_AVAILABLE = True
# except ImportError:
#     GEMINI_AVAILABLE = False
# logging.info(f"Gemini library available check: {GEMINI_AVAILABLE}") # Removed

class ToolInputWidget(QWidget):
    """Widget for displaying and gathering input for a tool's parameters."""

    # Added server_name back to init as it's needed for context
    def __init__(self, tool, server_name=None): # Added server_name parameter
        super().__init__()
        self.tool = tool
        self.server_name = server_name # Store server name
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Tool name and description (Include server name if provided)
        tool_display_name = f"{self.tool.name}"
        if self.server_name:
             tool_display_name += f" (Server: {self.server_name})"
        name_label = QLabel(f"<b>{tool_display_name}</b>")
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

# ChatWidget class has been moved to ui/chat_widget.py
