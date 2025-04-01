import json
import logging

# This module contains utilities specific to the Gemini API, like tool formatting.

def format_tools_for_gemini(connection_mgr):
    """Formats MCP tools for the Gemini API's function calling format."""
    gemini_tools = []
    all_mcp_tools = connection_mgr.get_all_tools() # {server: [tools]}

    if not all_mcp_tools:
        return None

    for server_name, tool_list in all_mcp_tools.items():
        if tool_list:
            for tool in tool_list:
                tool_name = getattr(tool, 'name', None)
                description = getattr(tool, 'description', 'No description available.')
                input_schema = getattr(tool, 'inputSchema', None)

                if not tool_name or not input_schema:
                    logging.warning(f"Skipping tool from server '{server_name}' due to missing name or schema: {tool}")
                    continue

                # Gemini requires specific schema format (OpenAPI subset)
                # Basic conversion attempt:
                gemini_schema = {
                    "type": input_schema.get("type", "OBJECT").upper(), # Default to OBJECT
                    "properties": {},
                    "required": input_schema.get("required", [])
                }

                # Handle properties, including arrays and empty objects
                input_properties = input_schema.get("properties")
                if input_properties: # Check if properties exist and are not empty
                    for prop_name, prop_details in input_properties.items():
                        prop_type = prop_details.get("type", "string").upper()
                        gemini_prop = {
                            "type": prop_type,
                            "description": prop_details.get("description", "")
                        }

                        # Handle array types: add 'items' schema
                        if prop_type == "ARRAY":
                            # Try to get item type from MCP schema, default to STRING
                            items_schema = prop_details.get("items", {})
                            items_type = items_schema.get("type", "string").upper()
                            # Define the items schema structure
                            gemini_items_schema = {"type": items_type}
                            # Copy item description if available
                            if "description" in items_schema:
                                 gemini_items_schema["description"] = items_schema["description"]
                            # If items are objects, explicitly add empty properties schema as required by API
                            if items_type == "OBJECT":
                                 gemini_items_schema["properties"] = {} # Explicitly add empty properties
                            # Assign the constructed items schema
                            gemini_prop["items"] = gemini_items_schema

                        # Handle enums if present
                        if "enum" in prop_details:
                            gemini_prop["enum"] = prop_details["enum"]

                        gemini_schema["properties"][prop_name] = gemini_prop
                
                # FIXED: Ensure all OBJECT types have at least one property
                if gemini_schema["type"] == "OBJECT" and (not gemini_schema["properties"] or len(gemini_schema["properties"]) == 0):
                    # If type is OBJECT but no properties are defined, add a placeholder property
                    gemini_schema["properties"] = {
                        "_placeholder": {
                            "type": "STRING",
                            "description": "Placeholder property to satisfy API requirements"
                        }
                    }


                # Gemini uses FunctionDeclaration
                gemini_tools.append({
                    "name": f"{server_name}__{tool_name}", # Use double underscore to separate server/tool
                    "description": f"(Server: {server_name}) {description}",
                    "parameters": gemini_schema
                })

    return gemini_tools if gemini_tools else None
