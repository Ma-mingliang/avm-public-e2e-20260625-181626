"""AVM checkpoint 命令"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from ..core.locking import TaskLocker
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..models import TaskStatus

console = Console()


def run_checkpoint(
    project_path: Path,
    message: str,
    json_output: bool = False,
) -> bool:
    """阶段提交

    Args:
        project_path: 项目路径
        message: 提交消息
        json_output: 是否输出 JSON

    Returns:
        是否成功
    """
    try:
        result = _do_checkpoint(project_path, message)

        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_result(result)

        return result["success"]
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            console.print(f"[red]错误: {e}[/red]")
        return False


def _do_checkpoint(project_path: Path, message: str) -> dict[str, Any]:
    """执行阶段提交

    Args:
        project_path: 项目路径
        message: 提交消息

    Returns:
        提交结果
    """
    project_path = Path(project_path).resolve()
    result = {
        "success": True,
        "project_path": str(project_path),
        "steps": [],
    }

    # 1. 检查任务锁
    locker = TaskLocker(project_path)
    lock = locker.get_lock()

    if lock is None:
        result["steps"].append(
            {
                "step": "check_lock",
                "status": "error",
                "message": "没有活动任务",
            }
        )
        result["success"] = False
        return result

    result["steps"].append(
        {
            "step": "check_lock",
            "status": "ok",
            "message": f"当前任务: {lock.version} ({lock.agent})",
        }
    )

    # 2. 检查 Git 状态
    git = GitOps(project_path)
    if not git.detect_repo():
        result["steps"].append(
            {
                "step": "check_git",
                "status": "error",
                "message": "不是 Git 仓库",
            }
        )
        result["success"] = False
        return result

    # 3. 获取未提交修改
    changes = git.get_uncommitted_changes()
    status = changes.get("status", {})
    if not changes["has_changes"]:
        result["steps"].append(
            {
                "step": "check_changes",
                "status": "warn",
                "message": "没有未提交的修改",
            }
        )
    else:
        modified_count = len(status.get("modified", []))
        untracked_count = len(status.get("untracked", []))
        result["steps"].append(
            {
                "step": "check_changes",
                "status": "ok",
                "message": f"发现修改: {modified_count} 个修改, {untracked_count} 个新文件",
            }
        )

    # 4. 暂存并提交
    try:
        # 暂存所有修改（排除版本管理目录）
        all_files = status.get("modified", []) + status.get("untracked", [])
        # 排除版本管理目录下的文件（通过检查路径组件）
        version_dir_name = "版本管理"
        files_to_stage = []
        for f in all_files:
            # 解码 git 的引号格式
            decoded = f
            if f.startswith('"') and f.endswith('"'):
                try:
                    decoded = f[1:-1].encode().decode("unicode_escape")
                except Exception:
                    decoded = f[1:-1]
            # 检查是否在版本管理目录下
            parts = Path(decoded).parts
            if version_dir_name not in parts:
                files_to_stage.append(f)

        if files_to_stage:
            git.stage_files(files_to_stage)

            # 构建提交消息
            commit_message = f"[{lock.version}] {message}"
            sha = git.commit(commit_message)

            result["steps"].append(
                {
                    "step": "commit",
                    "status": "ok",
                    "message": f"提交成功: {sha[:8]}",
                    "sha": sha,
                }
            )
        else:
            result["steps"].append(
                {
                    "step": "commit",
                    "status": "skip",
                    "message": "没有需要提交的修改",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "commit",
                "status": "error",
                "message": f"提交失败: {e}",
            }
        )
        result["success"] = False
        return result

    # 5. 更新任务锁状态
    try:
        state_machine = StateMachine(project_path)
        state_machine.transition(TaskStatus.MODIFYING)
        result["steps"].append(
            {
                "step": "update_state",
                "status": "ok",
                "message": "任务状态已更新为 MODIFYING",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "update_state",
                "status": "warn",
                "message": f"状态更新失败: {e}",
            }
        )

    return result


def _print_result(result: dict[str, Any]) -> None:
    """打印结果"""
    if result["success"]:
        console.print("[bold green]阶段提交成功[/bold green]")
    else:
        console.print("[bold red]阶段提交失败[/bold red]")

    for step in result.get("steps", []):
        status = step["status"]
        message = step["message"]

        if status == "ok":
            icon = "[green]✓[/green]"
        elif status == "warn":
            icon = "[yellow]⚠[/yellow]"
        elif status == "error":
            icon = "[red]✗[/red]"
        elif status == "skip":
            icon = "[dim]-[/dim]"
        else:
            icon = "?"

        console.print(f"  {icon} {message}")
