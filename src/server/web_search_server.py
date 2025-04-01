#!/usr/bin/env python3
import json
import sys
import logging
import argparse
import urllib.parse
import urllib.request
import ssl
import os
import requests
from typing import Dict, Any, List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Models a simple MCP server that provides web search functionality
class WebSearchServer:
    def __init__(self):
        self.tools = [
            {
                "name": "web_search",
                "description": "Search the web for information on a specified query",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to send to the search engine"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "fetch_webpage",
                "description": "Fetch the content of a specific webpage by URL",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL of the webpage to fetch"
                        },
                        "extract_text": {
                            "type": "boolean",
                            "description": "Whether to extract just the text content (default: true)",
                            "default": True
                        }
                    },
                    "required": ["url"]
                }
            }
        ]
        
        # Fallback search using a free API if the main one isn't available
        self.search_engine_url = "https://ddg-api.herokuapp.com/search"
        
        # Try to load API key from environment for better search results
        self.serpapi_key = os.environ.get("SERPAPI_KEY", "")
        if self.serpapi_key:
            logging.info("Using SerpAPI for web searches")
        else:
            logging.info("Using fallback search engine (limited results)")

    def handle_request(self, request_json: str) -> str:
        """Handle incoming MCP requests."""
        try:
            request = json.loads(request_json)
            logging.debug(f"Received request: {request}")
            
            # Handle different request types
            if request.get("method") == "mcp.list_tools":
                return self._handle_list_tools()
            elif request.get("method") == "mcp.call_tool":
                return self._handle_call_tool(request)
            else:
                return self._create_error_response(
                    request.get("id", "unknown"), 
                    -32601, 
                    "Method not found"
                )
        except json.JSONDecodeError:
            return self._create_error_response("unknown", -32700, "Parse error")
        except Exception as e:
            logging.error(f"Error handling request: {str(e)}")
            return self._create_error_response("unknown", -32603, f"Internal error: {str(e)}")

    def _handle_list_tools(self) -> str:
        """Handle a request to list available tools."""
        response = {
            "jsonrpc": "2.0",
            "result": {
                "tools": self.tools
            },
            "id": "list_tools"
        }
        return json.dumps(response)

    def _handle_call_tool(self, request: Dict[str, Any]) -> str:
        """Handle a request to call a tool."""
        request_id = request.get("id", "unknown")
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        # Validate the tool exists
        tool = next((t for t in self.tools if t["name"] == tool_name), None)
        if not tool:
            return self._create_error_response(request_id, -32602, f"Unknown tool: {tool_name}")
        
        # Call the appropriate tool handler
        try:
            if tool_name == "web_search":
                result = self._web_search(arguments)
            elif tool_name == "fetch_webpage":
                result = self._fetch_webpage(arguments)
            else:
                return self._create_error_response(request_id, -32602, f"Tool implementation not found: {tool_name}")
            
            # Create successful response
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False)
                        }
                    ]
                },
                "id": request_id
            }
            return json.dumps(response)
        except Exception as e:
            logging.error(f"Error executing tool {tool_name}: {str(e)}")
            return self._create_error_response(request_id, -32603, f"Error executing tool: {str(e)}")

    def _web_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a web search."""
        query = arguments.get("query", "")
        num_results = int(arguments.get("num_results", 5))
        
        if not query:
            return {"error": "Empty search query"}
        
        # Use SerpAPI if available
        if self.serpapi_key:
            return self._search_with_serpapi(query, num_results)
        
        # Use fallback search
        return self._search_with_fallback(query, num_results)

    def _search_with_serpapi(self, query: str, num_results: int) -> Dict[str, Any]:
        """Search using SerpAPI."""
        try:
            params = {
                "q": query,
                "api_key": self.serpapi_key,
                "num": num_results
            }
            
            response = requests.get(
                "https://serpapi.com/search", 
                params=params
            )
            
            if response.status_code != 200:
                logging.error(f"SerpAPI error: {response.status_code} {response.text}")
                return self._search_with_fallback(query, num_results)
            
            data = response.json()
            
            # Extract the organic results
            results = []
            if "organic_results" in data:
                for result in data["organic_results"][:num_results]:
                    results.append({
                        "title": result.get("title", ""),
                        "link": result.get("link", ""),
                        "snippet": result.get("snippet", "")
                    })
            
            return {
                "query": query,
                "results": results,
                "total_results": len(results)
            }
        except Exception as e:
            logging.error(f"SerpAPI search error: {str(e)}")
            # Fall back to alternate search
            return self._search_with_fallback(query, num_results)

    def _search_with_fallback(self, query: str, num_results: int) -> Dict[str, Any]:
        """Search using the fallback API."""
        try:
            # Prepare parameters
            params = {
                "q": query,
                "limit": min(num_results, 10)  # API limit
            }
            
            # Make the request
            response = requests.get(
                self.search_engine_url,
                params=params
            )
            
            if response.status_code != 200:
                return {
                    "error": f"Search API error: {response.status_code}",
                    "query": query,
                    "results": []
                }
            
            # Parse results
            data = response.json()
            results = []
            
            for item in data:
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", "")
                })
            
            return {
                "query": query,
                "results": results,
                "total_results": len(results)
            }
        except Exception as e:
            logging.error(f"Fallback search error: {str(e)}")
            return {
                "error": f"Search error: {str(e)}",
                "query": query,
                "results": []
            }

    def _fetch_webpage(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch the content of a webpage."""
        url = arguments.get("url", "")
        extract_text = arguments.get("extract_text", True)
        
        if not url:
            return {"error": "Empty URL"}
        
        try:
            # Add scheme if missing
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return {
                    "error": f"HTTP error: {response.status_code}",
                    "url": url
                }
            
            content_type = response.headers.get('content-type', '')
            
            # Only process text/html content
            if 'text/html' not in content_type.lower():
                return {
                    "url": url,
                    "content_type": content_type,
                    "content": "Non-HTML content cannot be processed",
                    "extract_text": extract_text
                }
            
            if extract_text:
                # Simple HTML text extraction
                try:
                    # Try to use BeautifulSoup if available
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.extract()
                    
                    # Get text
                    text = soup.get_text()
                    
                    # Break into lines and remove leading and trailing space
                    lines = (line.strip() for line in text.splitlines())
                    # Break multi-headlines into a line each
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    # Remove blank lines
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    return {
                        "url": url,
                        "content_type": content_type,
                        "text_content": text[:8000] + ("..." if len(text) > 8000 else ""),
                        "extract_text": extract_text
                    }
                except ImportError:
                    # Fallback to simple extraction
                    import re
                    text = re.sub(r'<.*?>', ' ', response.text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return {
                        "url": url,
                        "content_type": content_type,
                        "text_content": text[:8000] + ("..." if len(text) > 8000 else ""),
                        "extract_text": extract_text,
                        "note": "Used fallback extraction (BeautifulSoup not available)"
                    }
            else:
                # Return raw HTML
                return {
                    "url": url,
                    "content_type": content_type,
                    "html_content": response.text[:8000] + ("..." if len(response.text) > 8000 else ""),
                    "extract_text": extract_text
                }
        except Exception as e:
            logging.error(f"Error fetching webpage: {str(e)}")
            return {
                "error": f"Error fetching webpage: {str(e)}",
                "url": url
            }

    def _create_error_response(self, request_id: str, code: int, message: str) -> str:
        """Create a JSON-RPC error response."""
        response = {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": request_id
        }
        return json.dumps(response)

def main():
    """Main entry point for the MCP server."""
    # Set up an SSL context that doesn't verify (for development)
    ssl._create_default_https_context = ssl._create_unverified_context
    
    server = WebSearchServer()
    
    # Process stdin/stdout communications
    while True:
        try:
            # Each request is a single line of JSON
            request_line = sys.stdin.readline()
            if not request_line:
                break
            
            # Process request and send response
            response = server.handle_request(request_line.strip())
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Error in main loop: {str(e)}")
            # Try to send an error response
            error_response = server._create_error_response("unknown", -32603, f"Internal error: {str(e)}")
            sys.stdout.write(error_response + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        sys.exit(1)
