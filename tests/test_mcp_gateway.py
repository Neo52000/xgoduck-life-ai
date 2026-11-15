"""Tests for the read-only MCP gateway; no MCP dependency or network needed."""
from pathlib import Path
import importlib.util
from unittest.mock import patch, MagicMock
import urllib.error

mod_path = Path(__file__).parents[1] / "integrations/tunnel/gateway.py"
spec = importlib.util.spec_from_file_location("lifeai_mcp_gateway", mod_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_scope_read_only():
    scope = module.get_gateway_scope()
    assert scope["access"] == "read-only"
    assert scope["motor_control"] is False
    assert scope["shell_access"] is False
    assert scope["code_deployment"] is False

def test_external_urls_refused():
    try:
        module.get_lifeai_health("http://169.254.169.254/latest/meta-data")
    except ValueError:
        pass
    else:
        raise AssertionError("An external URL was accepted")

def test_unavailable_health_does_not_leak_errors():
    with patch.object(module.urllib.request, "urlopen", side_effect=urllib.error.URLError("private secret")):
        result = module.get_lifeai_health()
    assert result == {"reachable": False, "state": "unavailable", "error_type": "URLError"}

def test_response_filters_private_keys():
    response = MagicMock()
    response.status = 200
    response.read.return_value = b'{"status":"ok","admin_key":"must-not-leak"}'
    response.__enter__.return_value = response
    with patch.object(module.urllib.request, "urlopen", return_value=response):
        result = module.get_lifeai_health()
    assert result == {"reachable": True, "state": "healthy", "http_status": 200}
    assert "admin_key" not in str(result)
