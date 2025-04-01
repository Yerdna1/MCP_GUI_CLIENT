import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QDialogButtonBox, QCheckBox, QGroupBox
)
from PyQt6.QtCore import QSettings

# Config constants should be defined or imported if needed elsewhere
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

        # --- Add Google Gemini API Key Section ---
        google_group = QGroupBox("Google Gemini")
        google_layout = QFormLayout()

        self.google_key_input = QLineEdit()
        self.google_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_key_input.setPlaceholderText("Enter Google AI Studio API key")
        google_layout.addRow("API Key:", self.google_key_input)

        self.save_google_key = QCheckBox("Save API key")
        google_layout.addRow("", self.save_google_key)

        google_group.setLayout(google_layout)
        layout.addWidget(google_group)
        # --- End Google Gemini Section ---

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
        # Load Google key
        if self.settings.value("save_google_key", False, type=bool):
            self.google_key_input.setText(self.settings.value("google_api_key", ""))
            self.save_google_key.setChecked(True)

    def saveSettings(self):
        """Save settings if requested."""
        # Save Anthropic key
        if self.save_anthropic_key.isChecked():
            self.settings.setValue("anthropic_api_key", self.anthropic_key_input.text())
            self.settings.setValue("save_anthropic_key", True)
        else:
            if self.settings.contains("anthropic_api_key"):
                 self.settings.remove("anthropic_api_key")
            self.settings.setValue("save_anthropic_key", False)

        # Save Google key
        if self.save_google_key.isChecked():
            self.settings.setValue("google_api_key", self.google_key_input.text())
            self.settings.setValue("save_google_key", True)
        else:
            if self.settings.contains("google_api_key"):
                 self.settings.remove("google_api_key")
            self.settings.setValue("save_google_key", False)

    def getAnthropicKey(self):
        """Get the Anthropic API key."""
        return self.anthropic_key_input.text()

    def getGoogleKey(self):
        """Get the Google API key."""
        return self.google_key_input.text()
