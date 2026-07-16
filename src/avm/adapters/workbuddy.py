"""Tencent WorkBuddy MCP client adapter."""

from __future__ import annotations

from typing import Any

from ..models import AgentType, TaskLock
from .base import AgentAdapter


class WorkBuddyAdapter(AgentAdapter):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.WORKBUDDY

    @property
    def name(self) -> str:
        return "WorkBuddy"

    def is_available(self) -> bool:
        # Availability is established by the MCP client handshake, not a local CLI.
        return True

    def get_version(self) -> str:
        return "mcp-client"

    def preflight_check(self) -> dict[str, Any]:
        return {"passed": True, "checks": [{"name": "mcp_client", "passed": True, "message": "WorkBuddy MCP client"}]}

    def start_task(self, task_lock: TaskLock) -> bool:
        return True

    def checkpoint(self, message: str) -> bool:
        from ..git.ops import GitOps

        try:
            git = GitOps(self.project_root)
            git.stage_files(["."])
            git.commit(f"[{message}] WorkBuddy checkpoint")
            return True
        except Exception:
            return False

    def validate(self) -> dict[str, Any]:
        return self.run_validation_commands()

    def prepare_review(self) -> dict[str, Any]:
        return {"passed": True, "message": "WorkBuddy 审查准备完成"}

    def get_status(self) -> dict[str, Any]:
        return {"agent": self.name, "available": True, "version": self.get_version()}
