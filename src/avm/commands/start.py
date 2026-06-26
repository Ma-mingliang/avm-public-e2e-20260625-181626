"""AVM start 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..adapters.factory import detect_agent, get_adapter
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..git.versioning import VersionCalculator
from ..models import AgentType, TaskStatus

console = Console()


def run_start(
    project_path: Path,
    version: str | None = None,
    agent: str | None = None,
    json_output: bool = False,
) -> bool:
    """开始任务

    Args:
        project_path: 项目路径
        version: 指定版本号（可选，自动计算）
        agent: 指定 Agent（可选，自动检测）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "version": None,
        "agent": None,
        "branch": None,
        "status": None,
        "steps": [],
    }

    # 1. 检查 Git 仓库
    git = GitOps(project_path)
    if not git.is_repo():
        result["steps"].append({"step": "check_git", "status": "error", "message": "当前目录不是 Git 仓库"})
        _output(result, json_output)
        return False

    # 2. 检查状态机
    sm = StateMachine(project_path)
    sm.load()

    if not sm.is_idle():
        current = sm.current_status.value
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current}，无法开始新任务。请先完成或废弃当前任务",
            }
        )
        _output(result, json_output)
        return False

    # 3. 检测 Agent
    if agent:
        try:
            agent_type = AgentType(agent)
            adapter = get_adapter(agent_type, project_path)
        except (ValueError, KeyError):
            result["steps"].append(
                {
                    "step": "detect_agent",
                    "status": "error",
                    "message": f"不支持的 Agent: {agent}",
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

    # 4. 计算版本号
    if version:
        ver_str = version
    else:
        calc = VersionCalculator(project_path)
        try:
            ver_num = calc.get_next_version()
            ver_str = f"v{ver_num}"
        except Exception as e:
            result["steps"].append(
                {
                    "step": "calculate_version",
                    "status": "error",
                    "message": f"版本号计算失败: {e}",
                }
            )
            _output(result, json_output)
            return False

    result["version"] = ver_str
    result["steps"].append(
        {
            "step": "calculate_version",
            "status": "ok",
            "message": f"版本号: {ver_str}",
        }
    )

    # 5. 获取基础提交
    try:
        base_commit = git.get_head_sha()
    except Exception as e:
        result["steps"].append(
            {
                "step": "get_base_commit",
                "status": "error",
                "message": f"获取基础提交失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 6. 创建分支名
    branch = f"agent/{ver_str}-{adapter.agent_type.value}"

    # 7. Agent 预检（先于状态转换，失败则保持 IDLE）
    preflight = adapter.preflight_check()
    if not preflight.get("passed", False):
        result["steps"].append(
            {
                "step": "preflight",
                "status": "error",
                "message": f"Agent 预检未通过: {preflight}",
            }
        )
        _output(result, json_output)
        return False
    result["steps"].append(
        {
            "step": "preflight",
            "status": "ok",
            "message": "Agent 预检通过",
        }
    )

    # 8. 状态转换: IDLE → PREFLIGHT → WAIT_START_APPROVAL（等待用户审批）
    try:
        sm.transition(
            TaskStatus.PREFLIGHT,
            {
                "version": ver_str,
                "agent": adapter.agent_type.value,
                "branch": branch,
                "base_commit": base_commit,
            },
        )
        sm.transition(TaskStatus.WAIT_START_APPROVAL)
    except Exception as e:
        result["steps"].append(
            {
                "step": "state_transition",
                "status": "error",
                "message": f"状态转换失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    result["status"] = "WAIT_START_APPROVAL"
    result["branch"] = branch
    result["steps"].append(
        {
            "step": "state_transition",
            "status": "ok",
            "message": "状态已转换为 WAIT_START_APPROVAL",
        }
    )

    result["success"] = True
    _output(result, json_output)
    return True


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]任务已开始[/bold green]")
            console.print(f"  版本: {result['version']}")
            console.print(f"  Agent: {result['agent']}")
            console.print(f"  分支: {result['branch']}")
            console.print(f"  状态: {result['status']}")
        else:
            console.print("[bold red]任务启动失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
                elif step["status"] == "warn":
                    console.print(f"  [yellow]⚠ {step['message']}[/yellow]")
