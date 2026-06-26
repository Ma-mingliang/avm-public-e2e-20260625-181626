"""AVM status 命令"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ..core.locking import TaskLocker
from ..git.ops import GitOps
from ..git.versioning import VersionCalculator

console = Console()


def run_status(project_path: Path, json_output: bool = False) -> bool:
    """显示项目状态

    Args:
        project_path: 项目路径
        json_output: 是否输出 JSON

    Returns:
        命令是否成功执行（与是否有活动任务无关）
    """
    try:
        result = _get_status(project_path)

        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_status(result)

        return True
    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        else:
            console.print(f"[red]错误: {e}[/red]")
        return False


def _get_status(project_path: Path) -> dict[str, Any]:
    """获取项目状态

    Args:
        project_path: 项目路径

    Returns:
        状态信息
    """
    project_path = Path(project_path).resolve()
    result: dict[str, Any] = {
        "project_path": str(project_path),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # 1. Git 状态
    git = GitOps(project_path)
    if git.detect_repo():
        git_info: dict[str, Any] = {
            "is_repo": True,
            "branch": git.get_current_branch(),
            "head_sha": git.get_head_sha()[:8],
        }

        # 未提交修改
        changes = git.get_uncommitted_changes()
        git_info["has_changes"] = changes["has_changes"]
        git_info["modified_count"] = len(changes.get("modified", []))
        git_info["untracked_count"] = len(changes.get("untracked", []))
        result["git"] = git_info
    else:
        result["git"] = {"is_repo": False}

    # 2. 任务锁状态
    locker = TaskLocker(project_path)
    lock = locker.get_lock()

    if lock:
        result["task"] = {
            "has_active_task": lock.status.is_active(),
            "task_id": lock.task_id,
            "version": lock.version,
            "agent": lock.agent.value if hasattr(lock.agent, "value") else str(lock.agent),
            "branch": lock.branch,
            "status": lock.status.value,
            "started_at": lock.started_at,
        }
        result["has_active_task"] = lock.status.is_active()
    else:
        result["task"] = {"has_active_task": False}
        result["has_active_task"] = False

    # 3. 版本信息
    try:
        calc = VersionCalculator(project_path)
        result["version"] = {
            "next_version": calc.get_next_version(),
            "next_formatted": calc.format_version(calc.get_next_version()),
        }
    except Exception as e:
        result["version"] = {"error": str(e)}

    # 4. Hooks 状态
    hooks: dict[str, Any] = git.check_hooks() if git.detect_repo() else {}
    result["hooks"] = hooks

    return result


def _print_status(result: dict[str, Any]) -> None:
    """打印状态信息"""
    console.print("[bold]项目状态[/bold]")
    console.print(f"项目路径: {result['project_path']}")
    console.print("")

    # Git 状态
    git_info = result.get("git", {})
    if git_info.get("is_repo"):
        console.print("[bold]Git 状态[/bold]")
        console.print(f"  分支: {git_info.get('branch', 'unknown')}")
        console.print(f"  HEAD: {git_info.get('head_sha', 'unknown')}")

        if git_info.get("has_changes"):
            modified = git_info.get("modified_count", 0)
            untracked = git_info.get("untracked_count", 0)
            console.print(f"  [yellow]有未提交修改: {modified} 个修改, {untracked} 个新文件[/yellow]")
        else:
            console.print("  [green]工作区干净[/green]")
    else:
        console.print("[red]不是 Git 仓库[/red]")
    console.print("")

    # 任务状态
    task_info = result.get("task", {})
    if task_info.get("has_active_task"):
        console.print("[bold]活动任务[/bold]")
        console.print(f"  版本: {task_info.get('version', 'unknown')}")
        console.print(f"  代理: {task_info.get('agent', 'unknown')}")
        console.print(f"  分支: {task_info.get('branch', 'unknown')}")
        console.print(f"  状态: {task_info.get('status', 'unknown')}")
        console.print(f"  开始: {task_info.get('started_at', 'unknown')}")
    else:
        console.print("[dim]没有活动任务[/dim]")
    console.print("")

    # 版本信息
    version_info = result.get("version", {})
    if "next_version" in version_info:
        console.print("[bold]版本信息[/bold]")
        console.print(f"  下一个版本: {version_info.get('next_formatted', 'unknown')}")
    elif "error" in version_info:
        console.print(f"[yellow]版本信息: {version_info['error']}[/yellow]")
    console.print("")

    # Hooks 状态
    hooks = result.get("hooks", {})
    if hooks:
        console.print("[bold]Git Hooks[/bold]")
        for hook, installed in hooks.items():
            status = "[green]✓[/green]" if installed else "[red]✗[/red]"
            console.print(f"  {status} {hook}")
