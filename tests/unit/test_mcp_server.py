from __future__ import annotations

from pathlib import Path

import pytest

from avm.mcp_server import AVMMCPServer
from avm.models import AgentType


def test_workbuddy_agent_type_is_supported() -> None:
    assert AgentType("workbuddy") is AgentType.WORKBUDDY


def test_tools_list_is_restricted() -> None:
    server = AVMMCPServer(Path.cwd(), agent="codex", client_id="codex-desktop")
    names = {tool["name"] for tool in server.list_tools()}
    assert names == {
        "avm_status",
        "avm_preflight",
        "avm_start",
        "avm_approve",
        "avm_checkpoint",
        "avm_validate",
        "avm_prepare_review",
        "avm_create_pr",
        "avm_merge",
        "avm_publish",
    }


def test_project_binding_rejects_path_escape(tmp_path: Path) -> None:
    server = AVMMCPServer(tmp_path, agent="codex", client_id="codex-desktop")
    with pytest.raises(ValueError, match="project root"):
        server.call_tool("avm_status", {"project_root": str(tmp_path / "..")})


def test_status_returns_structured_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = AVMMCPServer(tmp_path, agent="codex", client_id="codex-desktop")
    monkeypatch.setattr("avm.mcp_server._run_json_command", lambda *args, **kwargs: {"success": True})
    result = server.call_tool("avm_status", {})
    assert result["success"] is True
    assert result["audit"]["approval_source"] == "machine"
    assert result["audit"]["agent"] == "codex"


def test_json_rpc_initialize_and_tools() -> None:
    server = AVMMCPServer(Path.cwd(), agent="codex", client_id="codex-desktop")
    init = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["protocolVersion"]
    listed = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed["result"]["tools"]


def test_all_workflow_handlers_are_structured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = AVMMCPServer(tmp_path, agent="workbuddy", client_id="workbuddy")
    monkeypatch.setattr("avm.mcp_server._run_json_command", lambda *args, **kwargs: {"success": True})
    for index, name in enumerate(
        ["avm_preflight", "avm_start", "avm_approve", "avm_checkpoint", "avm_validate",
         "avm_prepare_review", "avm_create_pr", "avm_merge", "avm_publish"],
        1,
    ):
        result = server.call_tool(name, {"call_id": f"handler-{index}"})
        assert result["success"] is True
        assert result["audit"]["approval_source"] == "machine"


def test_json_rpc_errors_are_structured(tmp_path: Path) -> None:
    server = AVMMCPServer(tmp_path, agent="codex", client_id="codex-desktop")
    unknown = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {}})
    assert unknown and unknown["error"]["code"] == -32601
    bad = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nope"}})
    assert bad and bad["error"]["code"] == -32602
    assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
