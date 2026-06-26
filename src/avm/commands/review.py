"""AVM prepare-review 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..adapters.factory import detect_agent, get_adapter
from ..core.state_machine import StateMachine
from ..models import AgentType, TaskStatus

console = Console()


def run_prepare_review(
    project_path: Path,
    json_output: bool = False,
) -> bool:
    """准备审阅材料

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "agent": None,
        "review": None,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status

    # 2. 检查状态
    if current not in (TaskStatus.VALIDATING, TaskStatus.MODIFYING, TaskStatus.FIXING):
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，无法准备审阅材料",
            }
        )
        _output(result, json_output)
        return False

    # 3. 检测 Agent
    task_lock = sm.task_lock
    if task_lock and task_lock.agent:
        try:
            agent_type = AgentType(task_lock.agent)
            adapter = get_adapter(agent_type, project_path)
        except (ValueError, KeyError):
            adapter = detect_agent(project_path)
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

    # 4. 准备审阅材料
    try:
        review = adapter.prepare_review()
        result["review"] = review
        passed = review.get("passed", False)

        if passed:
            result["steps"].append(
                {
                    "step": "prepare_review",
                    "status": "ok",
                    "message": "审阅材料准备完成",
                }
            )

            # 状态转换
            try:
                sm.transition(TaskStatus.REVIEW_MATERIAL_READY)
                result["steps"].append(
                    {
                        "step": "state_transition",
                        "status": "ok",
                        "message": "状态已转换为 REVIEW_MATERIAL_READY",
                    }
                )
            except Exception as e:
                result["steps"].append(
                    {
                        "step": "state_transition",
                        "status": "warn",
                        "message": f"状态转换失败: {e}",
                    }
                )
        else:
            result["steps"].append(
                {
                    "step": "prepare_review",
                    "status": "error",
                    "message": "审阅材料准备失败",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "prepare_review",
                "status": "error",
                "message": f"审阅材料准备失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    result["success"] = passed
    _output(result, json_output)
    return passed


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]审阅材料准备完成[/bold green]")
            console.print(f"  Agent: {result['agent']}")
        else:
            console.print("[bold red]审阅材料准备失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
