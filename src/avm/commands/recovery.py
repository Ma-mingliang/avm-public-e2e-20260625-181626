"""AVM recovery 命令 - 任务恢复与废弃"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..core.state_machine import StateMachine
from ..exceptions import AVMError
from ..models import TaskStatus

console = Console()


def run_resume(project_path: Path, json_output: bool = False) -> bool:
    """恢复中断的任务

    从 INTERRUPTED、AUTH_BLOCKED、NETWORK_BLOCKED 等错误状态恢复到之前的工作状态。
    恢复目标由进入错误状态时记录的 previous_status 决定。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "from_status": None,
        "to_status": None,
        "steps": [],
    }

    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    task_lock = sm.task_lock
    result["from_status"] = current.value

    # 只有错误状态才能恢复
    if not current.is_error():
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态 {current.value} 不是错误状态，无需恢复",
            }
        )
        _output(result, json_output)
        return False

    # 使用 previous_status 作为恢复目标
    recovery_target = _get_recovery_target(current, task_lock.previous_status if task_lock else None)
    if recovery_target is None:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"状态 {current.value} 不支持自动恢复（无 previous_status 记录）",
            }
        )
        _output(result, json_output)
        return False

    try:
        sm.transition(recovery_target)
        result["to_status"] = recovery_target.value
        result["success"] = True
        result["steps"].append(
            {
                "step": "resume",
                "status": "ok",
                "message": f"已从 {current.value} 恢复到 {recovery_target.value}",
            }
        )
    except AVMError as e:
        result["steps"].append(
            {
                "step": "resume",
                "status": "error",
                "message": f"状态恢复失败: {e}",
            }
        )

    _output(result, json_output)
    return result["success"]


def run_abandon(project_path: Path, json_output: bool = False) -> bool:
    """废弃当前任务

    将任务状态转为 ABANDONED，然后重置为 IDLE。
    只允许从 INTERRUPTED 或其他错误状态废弃。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "from_status": None,
        "steps": [],
    }

    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    result["from_status"] = current.value

    # 已经是 IDLE 或终态
    if current == TaskStatus.IDLE:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": "当前没有活动任务",
            }
        )
        _output(result, json_output)
        return False

    if current == TaskStatus.COMPLETE:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": "任务已完成，无需废弃",
            }
        )
        _output(result, json_output)
        return False

    # 只允许从错误状态或 INTERRUPTED 废弃
    abandonable = current.is_error() or current == TaskStatus.INTERRUPTED
    if not abandonable:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态 {current.value} 不允许废弃，请先中断任务",
            }
        )
        _output(result, json_output)
        return False

    try:
        # 转为 ABANDONED（只有 INTERRUPTED 可以直接转，其他错误状态需要先转 INTERRUPTED）
        if current != TaskStatus.INTERRUPTED:
            sm.transition(TaskStatus.INTERRUPTED)
        sm.transition(TaskStatus.ABANDONED)
        # 重置为 IDLE
        sm.transition(TaskStatus.IDLE)
        result["success"] = True
        result["steps"].append(
            {
                "step": "abandon",
                "status": "ok",
                "message": f"任务已从 {current.value} 废弃并重置为 IDLE",
            }
        )
    except AVMError as e:
        result["steps"].append(
            {
                "step": "abandon",
                "status": "error",
                "message": f"废弃失败: {e}",
            }
        )

    _output(result, json_output)
    return result["success"]


def run_recover(project_path: Path, json_output: bool = False) -> bool:
    """恢复任务（从 PUBLISH_INCOMPLETE 重试发布）

    从 PUBLISH_INCOMPLETE 状态恢复，允许重新尝试发布步骤。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "from_status": None,
        "steps": [],
    }

    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    result["from_status"] = current.value

    if current == TaskStatus.PUBLISH_INCOMPLETE:
        # 恢复到 TAGGING，允许重新尝试
        try:
            sm.transition(TaskStatus.TAGGING)
            result["success"] = True
            result["steps"].append(
                {
                    "step": "recover",
                    "status": "ok",
                    "message": "已恢复到 TAGGING 状态，可重新尝试发布",
                }
            )
        except AVMError as e:
            result["steps"].append(
                {
                    "step": "recover",
                    "status": "error",
                    "message": f"恢复失败: {e}",
                }
            )
    elif current == TaskStatus.APPROVAL_INVALIDATED:
        # 恢复到 WAIT_FINAL_APPROVAL
        try:
            sm.transition(TaskStatus.WAIT_FINAL_APPROVAL)
            result["success"] = True
            result["steps"].append(
                {
                    "step": "recover",
                    "status": "ok",
                    "message": "已恢复到 WAIT_FINAL_APPROVAL 状态，等待重新审批",
                }
            )
        except AVMError as e:
            result["steps"].append(
                {
                    "step": "recover",
                    "status": "error",
                    "message": f"恢复失败: {e}",
                }
            )
    elif current.is_error():
        # 其他错误状态使用 resume 逻辑
        return run_resume(project_path, json_output)
    else:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态 {current.value} 不支持恢复操作",
            }
        )

    _output(result, json_output)
    return result["success"]


def _get_recovery_target(status: TaskStatus, previous_status: TaskStatus | None) -> TaskStatus | None:
    """根据错误状态和 previous_status 确定恢复目标状态

    优先使用 previous_status（进入错误状态前的状态）。
    如果没有记录，则使用默认恢复映射。
    """
    if previous_status and previous_status not in (
        TaskStatus.IDLE,
        TaskStatus.COMPLETE,
        TaskStatus.ABANDONED,
    ):
        return previous_status

    # 默认恢复映射（当无 previous_status 时使用）
    recovery_map = {
        TaskStatus.INTERRUPTED: TaskStatus.RESERVED,
        TaskStatus.AUTH_BLOCKED: TaskStatus.PREFLIGHT,
        TaskStatus.NETWORK_BLOCKED: TaskStatus.PREFLIGHT,
        TaskStatus.SECURITY_BLOCKED: None,  # 需要人工干预
        TaskStatus.APPROVAL_INVALIDATED: TaskStatus.WAIT_FINAL_APPROVAL,
    }
    return recovery_map.get(status)


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]恢复操作成功[/bold green]")
            if result.get("from_status") and result.get("to_status"):
                console.print(f"  {result['from_status']} → {result['to_status']}")
        else:
            console.print("[bold red]恢复操作失败[/bold red]")
            for step in result.get("steps", []):
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
