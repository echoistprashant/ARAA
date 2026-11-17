import json
import sys
from typing import Any


class MCPResearchServer:
    """Zero-cost Model Context Protocol (MCP) JSON-RPC 2.0 server.
    
    Exposes modular research utilities over standardized stdio / stream interfaces.
    """

    SERVER_INFO = {
        "name": "araa-research-tools",
        "version": "1.0.0",
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
        },
    }

    TOOLS = [
        {
            "name": "extract_keywords",
            "description": "Extracts high-frequency topical keywords and named phrases from text.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Source text to analyze"},
                    "max_keywords": {"type": "integer", "default": 5, "description": "Maximum keywords to return"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "text_statistics",
            "description": "Computes word count, character count, sentence count, and reading time.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Document text to measure"},
                },
                "required": ["text"],
            },
        },
    ]

    def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Dispatches incoming JSON-RPC 2.0 requests to the appropriate handler."""
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "serverInfo": self.SERVER_INFO,
                    "capabilities": self.SERVER_INFO["capabilities"],
                    "protocolVersion": self.SERVER_INFO["protocolVersion"],
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.TOOLS,
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result_text = self._execute_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}],
                        "isError": True,
                    },
                }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Internal execution dispatch for MCP server tools."""
        if name == "extract_keywords":
            text = args.get("text", "")
            limit = args.get("max_keywords", 5)
            words = [w.strip(".,;:\"'()[]{}").lower() for w in text.split() if len(w) > 3]
            stopwords = {"this", "that", "with", "from", "have", "were", "they", "their", "about", "which"}
            filtered = [w for w in words if w not in stopwords]
            from collections import Counter
            counts = Counter(filtered).most_common(limit)
            keywords = [word for word, _ in counts]
            return json.dumps({"keywords": keywords, "count": len(keywords)})

        elif name == "text_statistics":
            text = args.get("text", "")
            words = text.split()
            word_count = len(words)
            char_count = len(text)
            sentence_count = max(1, text.count(".") + text.count("!") + text.count("?"))
            # Estimated reading speed: 200 words per minute
            reading_time_mins = round(word_count / 200.0, 2)
            return json.dumps({
                "word_count": word_count,
                "character_count": char_count,
                "sentence_count": sentence_count,
                "reading_time_minutes": reading_time_mins,
            })

        else:
            raise ValueError(f"Unknown MCP tool: {name}")

    def run_stdio(self) -> None:
        """Runs the stdio event loop processing JSON-RPC lines from stdin."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                res = self.handle_request(req)
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_res = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                sys.stdout.write(json.dumps(err_res) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = MCPResearchServer()
    server.run_stdio()
