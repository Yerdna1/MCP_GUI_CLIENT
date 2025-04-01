import json
import logging
from typing import Optional

# Import necessary Qt components
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QListWidget,
    QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# Import local components
from .widgets import ToolInputWidget
from .workers import MCPToolCallWorker
# Assuming MCPConnectionManager is accessible via src path
try:
    from src.mcp_connector_fixed import MCPConnectionManager
except ImportError:
     logging.error("Failed to import MCPConnectionManager for ToolController")
     # Define dummy class if needed
     class MCPConnectionManager: pass


class ToolController:
    """Handles logic for the Manual Tool Selection tab."""

    def __init__(self, connection_mgr: MCPConnectionManager, tools_list_widget: QListWidget,
                 tool_container_widget: QWidget, tool_layout: QVBoxLayout, result_text_widget: QTextEdit):
        self.connection_mgr = connection_mgr
        self.tools_list = tools_list_widget
        self.tool_container = tool_container_widget # The widget whose layout we manage
        self.tool_layout = tool_layout # The layout within tool_container
        self.result_text = result_text_widget

        self.current_tool_widget: Optional[ToolInputWidget] = None
        self.tool_call_worker: Optional[MCPToolCallWorker] = None

        # Connect signals if needed (e.g., if tools_list is managed here)
        # self.tools_list.itemClicked.connect(self.on_tool_selected) # Connect in main_window instead

    def populate_tools_list(self):
        """Populate the tools list, grouping by server."""
        self.tools_list.clear()
        all_tools_by_server = self.connection_mgr.get_all_tools() # Gets {server: [tools]}

        if not all_tools_by_server:
            self.tools_list.addItem("No tools available. Connect to servers.")
            return

        # Sort server names for consistent order
        sorted_server_names = sorted(all_tools_by_server.keys())

        for server_name in sorted_server_names:
            tools = all_tools_by_server[server_name]
            if not tools:
                continue # Skip servers with no tools reported

            # Add a non-selectable header item for the server
            server_item = QListWidgetItem(f"--- {server_name} ---")
            server_item.setFlags(server_item.flags() & ~Qt.ItemFlag.ItemIsSelectable) # Make it non-selectable
            font = server_item.font()
            font.setBold(True)
            server_item.setFont(font)
            self.tools_list.addItem(server_item)

            # Sort tools alphabetically within the server group
            tools.sort(key=lambda tool: getattr(tool, 'name', '')) # Use getattr for safety

            for tool in tools:
                item = QListWidgetItem(f"  {getattr(tool, 'name', 'Unknown')}") # Indent tool names
                # Store both server and tool name
                item.setData(Qt.ItemDataRole.UserRole, {"server": server_name, "tool": getattr(tool, 'name', None)})
                description = getattr(tool, 'description', "No description")
                item.setToolTip(description if description else "No description")
                self.tools_list.addItem(item)

    def on_tool_selected(self, item: QListWidgetItem):
        """Handle tool selection from the list."""
        tool_data = item.data(Qt.ItemDataRole.UserRole)

        # Ignore clicks on headers or invalid items
        if not isinstance(tool_data, dict) or "server" not in tool_data or "tool" not in tool_data:
            logging.debug("Clicked on a non-tool item or item with invalid data.")
            if not isinstance(tool_data, dict):
                 self.clear_tool_details_panel()
                 self.tool_layout.addWidget(QLabel("Select a specific tool from a server."))
            return

        server_name = tool_data["server"]
        tool_name = tool_data["tool"]

        if not tool_name: # Check if tool name is None
             logging.error(f"Invalid tool data for item: {item.text()}")
             self.clear_tool_details_panel()
             self.tool_layout.addWidget(QLabel(f"Error: Invalid tool data selected."))
             return

        # Get the specific tool definition from the manager
        server_tools = self.connection_mgr.get_tools(server_name)
        selected_tool = None
        if server_tools:
            for tool in server_tools:
                if getattr(tool, 'name', None) == tool_name:
                    selected_tool = tool
                    break

        if not selected_tool:
            logging.error(f"Selected tool '{tool_name}' from server '{server_name}' not found in manager's list.")
            self.clear_tool_details_panel()
            self.tool_layout.addWidget(QLabel(f"Error: Tool '{tool_name}' not found for server '{server_name}'."))
            return

        # Clear current tool widget and add the new one
        self.clear_tool_details_panel()

        # Pass server_name to ToolInputWidget constructor
        self.current_tool_widget = ToolInputWidget(selected_tool, server_name)
        # Connect execute button, passing both server and tool name
        self.current_tool_widget.execute_button.clicked.connect(
            lambda checked=False, sn=server_name, tn=tool_name: self.execute_tool(sn, tn)
        )
        self.tool_layout.addWidget(self.current_tool_widget)
        self.result_text.clear() # Clear previous results

    def execute_tool(self, server_name: str, tool_name: str):
        """Execute the selected tool on the specified server."""
        if not self.current_tool_widget or \
           getattr(self.current_tool_widget.tool, 'name', None) != tool_name or \
           self.current_tool_widget.server_name != server_name:
            logging.warning(f"Tool widget mismatch or not found for {tool_name} on {server_name}")
            QMessageBox.warning(self.tool_container.parentWidget(), # Try to get parent for QMessageBox
                                "Execution Error", "Tool selection mismatch. Please re-select the tool.")
            return

        # Check if the specific server is actually connected
        if not self.connection_mgr.is_connected(server_name):
             QMessageBox.critical(self.tool_container.parentWidget(),
                                  "Execution Error", f"Server '{server_name}' is not currently connected.")
             return

        args = self.current_tool_widget.get_arguments()
        if args is None:  # Invalid JSON input by user
            return

        self.result_text.clear()
        self.result_text.append(f"Executing tool: {tool_name} on server: {server_name}")
        self.result_text.append(f"Arguments: {json.dumps(args, indent=2)}")
        self.result_text.append("\nWaiting for results...")

        # Disable execute button while running? (Optional)
        # self.current_tool_widget.execute_button.setEnabled(False)

        # Create and start the worker thread for the specific tool call
        # MCPToolCallWorker needs server_name now
        self.tool_call_worker = MCPToolCallWorker(self.connection_mgr, server_name, tool_name, args)
        self.tool_call_worker.result_ready.connect(self.handle_tool_result)
        self.tool_call_worker.error_occurred.connect(self.handle_tool_error)
        self.tool_call_worker.start()

    def handle_tool_result(self, result):
        """Handle the result from a tool execution."""
        # Re-enable execute button if it was disabled
        # if self.current_tool_widget: self.current_tool_widget.execute_button.setEnabled(True)
        self.result_text.clear()

        if result is None:
            self.result_text.append("No result returned from tool.")
            return

        try:
            # Attempt to pretty-print if it's likely JSON, otherwise just stringify
            result_content = getattr(result, 'content', result) # Get content if available
            if isinstance(result_content, (dict, list)):
                result_str = json.dumps(result_content, indent=2)
            # Handle cases where content might be a list of simple types or complex objects
            elif isinstance(result_content, list) and result_content and not isinstance(result_content[0], (dict, list)):
                 result_str = "\n".join(map(str, result_content))
            else:
                result_str = str(result_content)

            self.result_text.append("Tool execution successful:\n")
            self.result_text.append(result_str)
        except Exception as e:
            logging.error(f"Error formatting tool result: {e}")
            self.result_text.append(f"Tool execution successful, but result formatting failed:\n{str(result)}")

        # Scroll to top
        self.result_text.verticalScrollBar().setValue(0) # Scroll to top

    def handle_tool_error(self, error_msg):
        """Handle an error during tool execution."""
        # Re-enable execute button if it was disabled
        # if self.current_tool_widget: self.current_tool_widget.execute_button.setEnabled(True)
        self.result_text.clear()
        self.result_text.append("Tool execution failed:\n")
        self.result_text.append(error_msg)
        # Optionally update server status to error?

    def clear_tool_details_panel(self):
        """Clears the right panel where tool details are shown."""
        # Clear current tool widget if exists
        if self.current_tool_widget:
            self.current_tool_widget.setParent(None)
            self.current_tool_widget = None
        # Clear any placeholder labels
        for i in reversed(range(self.tool_layout.count())):
            item = self.tool_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
        # Clear results text
        self.result_text.clear()
