"""AVM Claude Code 适配器"""

from __future__ import annotations

import subprocess
from typing import Any

from ..models import AgentType, TaskLock
from .base import AgentAdapter


class ClaudeCodeAdapter(AgentAdapter):
    """Claude Code 适配器"""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CLAUDE_CODE

    @property
    def name(self) -> str:
        return "Claude Code"

    def is_available(self) -> bool:
        """检查 Claude Code 是否可用"""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_version(self) -> str:
        """获取 Claude Code 版本"""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return "unknown"
        except Exception:
            return "unknown"

    def preflight_check(self) -> dict[str, Any]:
        """预检"""
        checks = []

        # 检查 Claude Code 是否可用
        available = self.is_available()
        checks.append(
            {
                "name": "claude_available",
                "passed": available,
                "message": "Claude Code 可用" if available else "Claude Code 不可用",
            }
        )

        # 检查版本
        if available:
            version = self.get_version()
            checks.append(
                {
                    "name": "claude_version",
                    "passed": True,
                    "message": f"Claude Code 版本: {version}",
                }
            )

        return {
            "passed": all(c["passed"] for c in checks),
            "checks": checks,
        }

    def start_task(self, task_lock: TaskLock) -> bool:
        """开始任务"""
        # Claude Code 不需要特殊启动逻辑
        return True

    def checkpoint(self, message: str) -> bool:
        """阶段提交"""
        # 委托给 Git 操作
        from ..git.ops import GitOps

        git = GitOps(self.project_root)
        try:
            git.stage_files(["."])
            git.commit(f"[{message}] Claude Code checkpoint")
            return True
        except Exception:
            return False

    def validate(self) -> dict[str, Any]:
        """验证 - 执行配置的验证命令"""
        return self.run_validation_commands()

    def prepare_review(self) -> dict[str, Any]:
        """准备审查"""
        return {
            "passed": True,
            "message": "Claude Code 审查准备完成",
        }

    def get_status(self) -> dict[str, Any]:
        """获取状态"""
        return {
            "agent": self.name,
            "available": self.is_available(),
            "version": self.get_version() if self.is_available() else None,
        }
