"""AVM launch 命令 - Agent 启动器"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from ..adapters.factory import detect_agent, get_adapter
from ..core.state_machine import StateMachine
from ..models import AgentType, TaskLock, TaskStatus

if TYPE_CHECKING:
    from ..adapters.base import AgentAdapter

console = Console()


def run_launch(
    project_path: Path,
    agent_name: str | None = None,
    task_description: str = "",
    json_output: bool = False,
) -> bool:
    """启动 Agent 执行任务

    流程:
    1. 检测或指定 Agent
    2. 验证 Agent 可用性
    3. 检查当前任务状态
    4. 启动 Agent 会话

    Args:
        project_path: 项目路径
        agent_name: Agent 名称（可选，自动检测）
        task_description: 任务描述
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "agent": None,
        "steps": [],
    }

    # 1. 检测 Agent
    if agent_name:
        try:
            agent_type = AgentType(agent_name)
            adapter = get_adapter(agent_type, project_path)
        except (ValueError, KeyError):
            result["steps"].append(
                {
                    "step": "detect_agent",
                    "status": "error",
                    "message": f"不支持的 Agent: {agent_name}",
                }
            )
            _output(result, json_output)
            return False
    else:
        adapter = detect_agent(project_path)
        if adapter is None:
            result["steps"].append(
                {
                    "step": "detect_agent",
                    "status": "error",
                    "message": "未检测到可用的 Agent",
                }
            )
            _output(result, json_output)
            return False

    result["agent"] = adapter.agent_type.value
    result["steps"].append(
        {
            "step": "detect_agent",
            "status": "ok",
            "message": f"检测到 Agent: {adapter.name}",
        }
    )

    # 2. 验证 Agent 可用性
    if not adapter.is_available():
        result["steps"].append(
            {
                "step": "check_available",
                "status": "error",
                "message": f"{adapter.name} 不可用，请检查安装",
            }
        )
        _output(result, json_output)
        return False

    version = adapter.get_version()
    result["steps"].append(
        {
            "step": "check_available",
            "status": "ok",
            "message": f"{adapter.name} 可用 (版本: {version})",
        }
    )

    # 3. 检查任务状态
    sm = StateMachine(project_path)
    sm.load()
    current = sm.current_status

    if current == TaskStatus.IDLE:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": "当前没有活动任务，请先使用 start 命令创建任务",
            }
        )
        _output(result, json_output)
        return False

    if current.is_error():
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态 {current.value} 是错误状态，请先恢复任务",
            }
        )
        _output(result, json_output)
        return False

    if current.is_terminal():
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态 {current.value} 是终态，请先创建新任务",
            }
        )
        _output(result, json_output)
        return False

    task_lock = sm.task_lock
    result["steps"].append(
        {
            "step": "check_state",
            "status": "ok",
            "message": f"当前状态: {current.value}, 版本: {task_lock.version if task_lock else 'unknown'}",
        }
    )

    # 4. 生成 Agent 配置文件
    try:
        _generate_agent_config(project_path, adapter, task_lock)
        result["steps"].append(
            {
                "step": "generate_config",
                "status": "ok",
                "message": "Agent 配置文件已生成",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "generate_config",
                "status": "warn",
                "message": f"配置文件生成失败: {e}",
            }
        )

    # 5. 启动 Agent
    try:
        launch_result = _launch_agent(project_path, adapter, task_lock, task_description)
        if launch_result:
            result["steps"].append(
                {
                    "step": "launch",
                    "status": "ok",
                    "message": f"{adapter.name} 已启动",
                }
            )
            result["success"] = True
        else:
            result["steps"].append(
                {
                    "step": "launch",
                    "status": "error",
                    "message": f"{adapter.name} 启动失败",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "launch",
                "status": "error",
                "message": f"启动失败: {e}",
            }
        )

    _output(result, json_output)
    return result["success"]


def _generate_agent_config(
    project_path: Path,
    adapter: AgentAdapter,
    task_lock: TaskLock | None,
) -> None:
    """生成 Agent 配置文件"""
    agent_type = adapter.agent_type

    if agent_type == AgentType.CLAUDE_CODE:
        _generate_claude_md(project_path, task_lock)
    elif agent_type == AgentType.HERMES:
        _generate_agents_md(project_path, task_lock)
    # Codex 不需要额外配置文件


def _generate_claude_md(project_path: Path, task_lock: TaskLock | None) -> None:
    """生成 CLAUDE.md 配置文件"""
    claude_md_path = project_path / "CLAUDE.md"

    content = """# AVM Agent 配置

## 任务信息

"""
    if task_lock:
        content += f"- 版本: {task_lock.version}\n"
        content += f"- 分支: {task_lock.branch}\n"
        content += f"- 状态: {task_lock.status.value}\n"
    else:
        content += "- 无活动任务\n"

    content += """
## 规则

1. 遵循 AVM 版本管理流程
2. 不得直接推送到 main 分支
3. 所有变更必须通过 PR 审批
4. 提交前运行安全扫描
5. 保持提交消息格式规范

## 验证命令

在提交前运行以下命令:
- `avm validate` - 运行配置的验证命令
- `avm hook pre-commit` - 检查敏感信息
"""

    claude_md_path.write_text(content, encoding="utf-8")


def _generate_agents_md(project_path: Path, task_lock: TaskLock | None) -> None:
    """生成 AGENTS.md 配置文件"""
    agents_md_path = project_path / "AGENTS.md"

    content = """# AVM Agent 配置

## 任务信息

"""
    if task_lock:
        content += f"- 版本: {task_lock.version}\n"
        content += f"- 分支: {task_lock.branch}\n"
        content += f"- 状态: {task_lock.status.value}\n"
    else:
        content += "- 无活动任务\n"

    content += """
## 规则

1. 遵循 AVM 版本管理流程
2. 不得直接推送到 main 分支
3. 所有变更必须通过 PR 审批
4. 提交前运行安全扫描
"""

    agents_md_path.write_text(content, encoding="utf-8")


def _launch_agent(
    project_path: Path,
    adapter: AgentAdapter,
    task_lock: TaskLock | None,
    task_description: str,
) -> bool:
    """启动 Agent 会话"""
    agent_type = adapter.agent_type

    if agent_type == AgentType.CLAUDE_CODE:
        return _launch_claude_code(project_path, task_lock, task_description)
    elif agent_type == AgentType.HERMES:
        return _launch_hermes(project_path, task_lock, task_description)
    elif agent_type == AgentType.CODEX:
        return _launch_codex(project_path, task_lock, task_description)
    else:
        return False


def _launch_claude_code(
    project_path: Path,
    task_lock: TaskLock | None,
    task_description: str,
) -> bool:
    """启动 Claude Code"""
    try:
        cmd = ["claude"]
        if task_description:
            cmd.extend(["--prompt", task_description])

        # 在后台启动 Claude Code
        subprocess.Popen(
            cmd,
            cwd=str(project_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def _launch_hermes(
    project_path: Path,
    task_lock: TaskLock | None,
    task_description: str,
) -> bool:
    """启动 Hermes"""
    try:
        cmd = ["hermes"]
        if task_description:
            cmd.extend(["--task", task_description])

        subprocess.Popen(
            cmd,
            cwd=str(project_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def _launch_codex(
    project_path: Path,
    task_lock: TaskLock | None,
    task_description: str,
) -> bool:
    """启动 Codex"""
    try:
        cmd = ["codex"]
        if task_description:
            cmd.extend(["--prompt", task_description])

        subprocess.Popen(
            cmd,
            cwd=str(project_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]Agent 启动成功[/bold green]")
            console.print(f"  Agent: {result['agent']}")
        else:
            console.print("[bold red]Agent 启动失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
