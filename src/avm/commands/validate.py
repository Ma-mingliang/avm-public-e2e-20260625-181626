"""AVM validate 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..adapters.factory import detect_agent, get_adapter
from ..core.state_machine import StateMachine
from ..models import AgentType, TaskStatus

console = Console()


def run_validate(
    project_path: Path,
    agent: str | None = None,
    json_output: bool = False,
) -> bool:
    """运行验证

    Args:
        project_path: 项目路径
        agent: 指定 Agent（可选，自动检测）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "validation": None,
        "status": None,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status

    # 2. 检查状态
    if current not in (TaskStatus.MODIFYING, TaskStatus.VALIDATING, TaskStatus.FIXING, TaskStatus.DRAFT_PR):
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，无法运行验证",
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
        # 从任务锁获取 Agent
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

    result["steps"].append(
        {
            "step": "detect_agent",
            "status": "ok",
            "message": f"使用 Agent: {adapter.name}",
        }
    )

    # 4. 运行验证
    try:
        validation = adapter.validate()
        result["validation"] = validation
        passed = validation.get("passed", False)

        if passed:
            result["steps"].append(
                {
                    "step": "validate",
                    "status": "ok",
                    "message": "验证通过",
                }
            )

            # 状态转换: MODIFYING/VALIDATING/FIXING → VALIDATING
            if current in (TaskStatus.MODIFYING, TaskStatus.FIXING):
                sm.transition(TaskStatus.VALIDATING)
                result["status"] = "VALIDATING"
        else:
            errors = validation.get("errors", [])
            result["steps"].append(
                {
                    "step": "validate",
                    "status": "error",
                    "message": f"验证失败: {errors}",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "validate",
                "status": "error",
                "message": f"验证执行失败: {e}",
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
            console.print("[bold green]验证通过[/bold green]")
            if result.get("status"):
                console.print(f"  新状态: {result['status']}")
        else:
            console.print("[bold red]验证失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
