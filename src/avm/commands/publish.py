"""AVM publish 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..core.approval import ApprovalManager
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..github.client import GitHubClient
from ..models import TaskStatus

console = Console()


def run_publish(
    project_path: Path,
    json_output: bool = False,
) -> bool:
    """发布版本

    创建 Git Tag 和 GitHub Release。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "version": None,
        "tag": None,
        "release_url": None,
        "status": None,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    task_lock = sm.task_lock

    # 2. 检查状态
    if current not in (
        TaskStatus.PR_READY,
        TaskStatus.MERGING,
        TaskStatus.TAGGING,
        TaskStatus.RELEASING,
        TaskStatus.PUBLISH_INCOMPLETE,
    ):
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，无法发布",
            }
        )
        _output(result, json_output)
        return False

    # 3. 获取版本信息
    version = task_lock.version if task_lock else None
    if not version:
        result["steps"].append(
            {
                "step": "check_version",
                "status": "error",
                "message": "未找到版本信息",
            }
        )
        _output(result, json_output)
        return False

    result["version"] = version

    # 4. 验证审批有效性
    if task_lock:
        try:
            from .approve import _compute_content_hash

            actual_content_hash = _compute_content_hash(project_path, task_lock)
            approval_mgr = ApprovalManager(project_path)
            approval_mgr.validate_approval(
                task_lock=task_lock,
                actual_content_hash=actual_content_hash,
            )
            result["steps"].append(
                {
                    "step": "validate_approval",
                    "status": "ok",
                    "message": "审批验证通过",
                }
            )
        except Exception as e:
            result["steps"].append(
                {
                    "step": "validate_approval",
                    "status": "error",
                    "message": f"审批验证失败: {e}",
                }
            )
            _output(result, json_output)
            return False

    # 5. 初始化 Git 和 GitHub
    git = GitOps(project_path)
    if not git.is_repo():
        result["steps"].append(
            {
                "step": "check_git",
                "status": "error",
                "message": "当前目录不是 Git 仓库",
            }
        )
        _output(result, json_output)
        return False

    # 6. 状态转换: PR_READY → MERGING → TAGGING
    try:
        if current == TaskStatus.PR_READY:
            sm.transition(TaskStatus.MERGING)
            current = TaskStatus.MERGING
        if current == TaskStatus.MERGING:
            sm.transition(TaskStatus.TAGGING)
            current = TaskStatus.TAGGING
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

    # 7. 创建 Git Tag 并推送
    try:
        tag_name = version
        if not git.create_annotated_tag(tag_name, f"Release {version}"):
            raise RuntimeError("创建本地标签失败")
        if not git.push_tag(tag_name):
            raise RuntimeError(f"推送标签 {tag_name} 到远程失败")
        result["tag"] = tag_name
        result["steps"].append(
            {
                "step": "create_tag",
                "status": "ok",
                "message": f"Git 标签已创建并推送: {tag_name}",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "create_tag",
                "status": "error",
                "message": f"创建/推送 Git 标签失败: {e}",
            }
        )
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        _output(result, json_output)
        return False

    # 8. 状态转换: TAGGING → RELEASING
    try:
        sm.transition(TaskStatus.RELEASING)
    except Exception as e:
        result["steps"].append(
            {
                "step": "state_transition",
                "status": "warn",
                "message": f"状态转换失败: {e}",
            }
        )

    # 9. 创建 GitHub Release
    try:
        client = GitHubClient()
        release = client.create_release(
            tag_name=tag_name,
            title=f"Release {version}",
            body=f"## {version}\n\n版本 {version} 发布。",
            draft=False,
            prerelease=False,
        )
        result["release_url"] = release.get("url", release.get("html_url", ""))
        result["steps"].append(
            {
                "step": "create_release",
                "status": "ok",
                "message": f"GitHub Release 已创建: {result['release_url']}",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "create_release",
                "status": "error",
                "message": f"创建 GitHub Release 失败: {e}",
            }
        )
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        result["status"] = "PUBLISH_INCOMPLETE"
        _output(result, json_output)
        return False

    # 10. 状态转换: RELEASING → HANDOFF_UPDATING → CLEANING → COMPLETE
    try:
        sm.transition(TaskStatus.HANDOFF_UPDATING)
        sm.transition(TaskStatus.CLEANING)
        sm.transition(TaskStatus.COMPLETE)
        result["status"] = "COMPLETE"
        result["steps"].append(
            {
                "step": "complete",
                "status": "ok",
                "message": "版本发布完成",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "complete",
                "status": "error",
                "message": f"最终状态转换失败: {e}",
            }
        )
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        result["status"] = "PUBLISH_INCOMPLETE"
        _output(result, json_output)
        return False

    result["success"] = True
    _output(result, json_output)
    return True


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]版本发布成功[/bold green]")
            console.print(f"  版本: {result['version']}")
            console.print(f"  标签: {result['tag']}")
            if result.get("release_url"):
                console.print(f"  Release: {result['release_url']}")
            console.print(f"  状态: {result['status']}")
        else:
            console.print("[bold red]版本发布失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
                elif step["status"] == "warn":
                    console.print(f"  [yellow]⚠ {step['message']}[/yellow]")
