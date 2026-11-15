"""Read-only MCP diagnostics gateway for XGO-Duck Life AI.
Does not provide SSH, shell, filesystem, private memories or motor actions.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from typing import Any

HEALTH_URL = "http://127.0.0.1:8000/health"

def get_lifeai_health(url: str = HEALTH_URL) -> dict[str, Any]:
    """Query the fixed localhost endpoint with a short timeout and small response."""
    if url != HEALTH_URL:
        raise ValueError("Only the fixed local Life AI health endpoint is allowed")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            status = response.status
            content = response.read(2048)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"reachable": False, "state": "unavailable", "error_type": type(exc).__name__}
    if status != 200:
        return {"reachable": False, "state": "unhealthy", "http_status": status}
    try:
        body = json.loads(content)
    except (json.JSONDecodeError, UnicodeError):
        return {"reachable": True, "state": "responding", "http_status": status}
    healthy = body.get("status") in {"ok", "healthy"} if isinstance(body, dict) else False
    return {"reachable": True, "state": "healthy" if healthy else "responding", "http_status": status}

def get_gateway_scope() -> dict[str, Any]:
    return {
        "project": "XGO-Duck Life AI",
        "gateway_version": "0.1.0",
        "access": "read-only",
        "allowed_operations": ["lifeai_health", "lifeai_gateway_scope"],
        "motor_control": False,
        "shell_access": False,
        "code_deployment": False,
    }

def main() -> None:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP(
        "xgoduck-lifeai-diagnostics", host="127.0.0.1",
        port=18765, stateless_http=True, json_response=True
    )
    @mcp.tool()
    def lifeai_health() -> dict[str, Any]:
        """Check the local Life AI health endpoint without returning private data."""
        return get_lifeai_health()
    @mcp.tool()
    def lifeai_gateway_scope() -> dict[str, Any]:
        """Describe the strictly read-only scope of this MCP gateway."""
        return get_gateway_scope()
    mcp.run(transport="streamable-http")

if __name__ == "__main__":
    main()
