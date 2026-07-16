"""Minimal, dependency-free MCP stdio server for AVM.

The server intentionally exposes only AVM workflow operations.  It is not a
general shell, filesystem, or git server.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from datetime import UTC, datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from .commands.approve import run_approve
from .commands.checkpoint import run_checkpoint
from .commands.preflight import run_preflight
from .commands.pr import run_create_pr, run_merge
from .commands.publish import run_publish
from .commands.review import run_prepare_review
from .commands.start import run_start
from .commands.validate import run_validate
from .commands.status import _get_status
from .git.ops import GitOps
from .models import AgentType

POLICY_VERSION = "avm-mcp-v1"


def _run_json_command(func: Callable[..., bool], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run an existing AVM command and parse its JSON output."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        ok = func(*args, json_output=True, **kwargs)
    raw = output.getvalue().strip()
    try:
        result = json.loads(raw) if raw else {"success": ok}
    except json.JSONDecodeError:
        result = {"success": ok, "output": raw[-4000:]}
    if isinstance(result, dict):
        result.setdefault("success", ok)
        return result
    return {"success": ok, "result": result}


class AVMMCPServer:
    """MCP server bound to one project and one client agent identity."""

    def __init__(self, project_root: Path, *, agent: str, client_id: str):
        self.project_root = Path(project_root).resolve()
        self.agent = AgentType(agent).value
        self.client_id = client_id.strip() or "unknown-client"
        if self.client_id == "codex-desktop" and self.agent == "codex":
            os.environ["AVM_MCP_AGENT_CONTEXT"] = "codex-desktop"
        self.call_ids: set[str] = set()
        self.audit_path = self.project_root / "版本管理" / "mcp-audit.jsonl"
        self._git_remote = self._read_remote()
        self._default_branch = self._read_default_branch()

    def _read_remote(self) -> str:
        try:
            return GitOps(self.project_root).get_remote_url("origin") or ""
        except Exception:
            return ""

    def _read_default_branch(self) -> str:
        try:
            return GitOps(self.project_root).get_default_branch()
        except Exception:
            return "main"

    def _bind(self, args: dict[str, Any]) -> None:
        supplied = args.get("project_root")
        if supplied and Path(supplied).resolve() != self.project_root:
            raise ValueError("project root is not bound to this MCP server")
        current_remote = self._read_remote()
        if self._git_remote and current_remote != self._git_remote:
            raise ValueError("git remote changed after MCP binding")
        if args.get("agent") and args["agent"] != self.agent:
            raise ValueError("agent identity cannot be overridden")

    def _audit(self, call_id: str, tool: str, success: bool, error: str = "") -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "call_id": call_id,
            "tool": tool,
            "client_id": self.client_id,
            "agent": self.agent,
            "approval_source": "machine",
            "policy_version": POLICY_VERSION,
            "project_root": str(self.project_root),
            "git_remote": self._git_remote,
            "default_branch": self._default_branch,
            "success": success,
        }
        if error:
            record["error"] = error
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Auditing failure must never silently authorize a write.
            if tool not in {"avm_status", "avm_preflight"}:
                raise
        return record

    def list_tools(self) -> list[dict[str, Any]]:
        names = [
            "avm_status", "avm_preflight", "avm_start", "avm_approve",
            "avm_checkpoint", "avm_validate", "avm_prepare_review", "avm_create_pr", "avm_merge", "avm_publish",
        ]
        return [{"name": name, "description": f"Bound AVM workflow operation: {name}",
                 "inputSchema": {"type": "object", "additionalProperties": True}} for name in names]

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        self._bind(args)
        call_id = str(args.pop("call_id", "") or uuid4())
        if call_id in self.call_ids:
            raise ValueError("call_id replay rejected")
        self.call_ids.add(call_id)
        handlers: dict[str, Callable[..., Any]] = {
            "avm_status": lambda: _get_status(self.project_root),
            "avm_preflight": lambda: _run_json_command(run_preflight, self.project_root, agent=self.agent,
                                                        task=args.get("task", ""),
                                                        changed_files=args.get("changed_files")),
            "avm_start": lambda: _run_json_command(run_start, self.project_root, version=args.get("version"),
                                                    agent=self.agent),
            "avm_approve": lambda: _run_json_command(run_approve, self.project_root,
                                                      approver=f"machine:{self.client_id}",
                                                      notes=args.get("notes", "machine-approved via MCP"),
                                                      approval_source="machine", policy_version=POLICY_VERSION,
                                                      call_id=call_id),
            "avm_checkpoint": lambda: _run_json_command(run_checkpoint, self.project_root,
                                                         message=args.get("message", "MCP checkpoint")),
            "avm_validate": lambda: _run_json_command(run_validate, self.project_root, agent=self.agent),
            "avm_prepare_review": lambda: _run_json_command(run_prepare_review, self.project_root),
            "avm_create_pr": lambda: _run_json_command(run_create_pr, self.project_root,
                                                        draft=bool(args.get("draft", False))),
            "avm_merge": lambda: _run_json_command(run_merge, self.project_root),
            "avm_publish": lambda: _run_json_command(run_publish, self.project_root),
        }
        if name not in handlers:
            raise ValueError(f"unknown AVM tool: {name}")
        try:
            result = handlers[name]()
            if not isinstance(result, dict):
                result = {"result": result}
            result.setdefault("success", True)
            result["binding"] = {"project_root": str(self.project_root), "git_remote": self._git_remote,
                                  "default_branch": self._default_branch, "agent": self.agent}
            result["audit"] = self._audit(call_id, name, bool(result.get("success", True)))
            return result
        except Exception as exc:
            self._audit(call_id, name, False, str(exc))
            raise

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "avm-mcp", "version": "1.0.0"},
            }}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.list_tools()}}
        if method == "tools/call":
            try:
                params = message.get("params", {})
                result = self.call_tool(params["name"], params.get("arguments", {}))
                content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                return {"jsonrpc": "2.0", "id": request_id, "result": {"content": content, "isError": False}}
            except Exception as exc:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--agent", required=True, choices=[a.value for a in AgentType])
    parser.add_argument("--client-id", default="mcp-client")
    options = parser.parse_args()
    server = AVMMCPServer(Path(options.project_root), agent=options.agent, client_id=options.client_id)
    for line in sys.stdin:
        if not line.strip():
            continue
        response = server.handle_message(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
