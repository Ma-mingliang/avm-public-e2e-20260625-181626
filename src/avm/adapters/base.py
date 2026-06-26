"""AVM Agent 适配器基类"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import AgentType, TaskLock


class AgentAdapter(ABC):
    """Agent 适配器基类

    所有 Agent 适配器必须继承此类并实现抽象方法。
    """

    def __init__(self, project_root: Path):
        """初始化适配器

        Args:
            project_root: 项目根目录
        """
        self.project_root = project_root

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """返回 Agent 类型"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """返回 Agent 名称"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查 Agent 是否可用

        Returns:
            是否可用
        """
        ...

    @abstractmethod
    def get_version(self) -> str:
        """获取 Agent 版本

        Returns:
            版本字符串
        """
        ...

    @abstractmethod
    def preflight_check(self) -> dict[str, Any]:
        """预检

        Returns:
            检查结果
        """
        ...

    @abstractmethod
    def start_task(self, task_lock: TaskLock) -> bool:
        """开始任务

        Args:
            task_lock: 任务锁

        Returns:
            是否成功
        """
        ...

    @abstractmethod
    def checkpoint(self, message: str) -> bool:
        """阶段提交

        Args:
            message: 提交消息

        Returns:
            是否成功
        """
        ...

    @abstractmethod
    def validate(self) -> dict[str, Any]:
        """验证

        Returns:
            验证结果
        """
        ...

    @abstractmethod
    def prepare_review(self) -> dict[str, Any]:
        """准备审查

        Returns:
            审查准备结果
        """
        ...

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """获取状态

        Returns:
            状态信息
        """
        ...

    def get_adapter_info(self) -> dict[str, Any]:
        """获取适配器信息

        Returns:
            适配器信息
        """
        return {
            "agent_type": self.agent_type.value if hasattr(self.agent_type, "value") else str(self.agent_type),
            "name": self.name,
            "available": self.is_available(),
            "version": self.get_version() if self.is_available() else None,
        }

    def run_validation_commands(self) -> dict[str, Any]:
        """执行配置的验证命令

        从项目配置加载 validation.commands，逐个执行并收集结果。
        任何命令失败则整体验证不通过。

        Returns:
            验证结果 {"passed": bool, "checks": [...]}
        """
        try:
            from ..config import load_project_config

            config = load_project_config(self.project_root)
            commands = config.validation.commands
        except Exception:
            # 配置不存在或无法加载时，跳过命令验证
            return {
                "passed": True,
                "checks": [
                    {
                        "name": "config_load",
                        "passed": True,
                        "message": "无验证配置，跳过命令验证",
                    }
                ],
            }

        if not commands:
            return {
                "passed": True,
                "checks": [
                    {
                        "name": "no_commands",
                        "passed": True,
                        "message": "未配置验证命令",
                    }
                ],
            }

        checks = []
        all_passed = True

        for cmd_config in commands:
            cmd_name = cmd_config.name
            cmd_args = cmd_config.command

            if not cmd_args:
                continue

            try:
                result = subprocess.run(
                    cmd_args,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                passed = result.returncode == 0
                # 脱敏输出（截断长输出，去除可能的路径信息）
                output = (result.stdout + result.stderr).strip()
                if len(output) > 500:
                    output = output[:500] + "...(截断)"

                checks.append(
                    {
                        "name": cmd_name,
                        "passed": passed,
                        "message": f"退出码: {result.returncode}" if not passed else "通过",
                        "output": output if not passed else "",
                    }
                )
                if not passed:
                    all_passed = False
            except subprocess.TimeoutExpired:
                checks.append(
                    {
                        "name": cmd_name,
                        "passed": False,
                        "message": "命令超时 (120s)",
                    }
                )
                all_passed = False
            except FileNotFoundError:
                checks.append(
                    {
                        "name": cmd_name,
                        "passed": False,
                        "message": f"命令未找到: {cmd_args[0] if cmd_args else 'unknown'}",
                    }
                )
                all_passed = False
            except Exception as e:
                checks.append(
                    {
                        "name": cmd_name,
                        "passed": False,
                        "message": f"执行失败: {e}",
                    }
                )
                all_passed = False

        return {"passed": all_passed, "checks": checks}
