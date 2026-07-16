"""AVM publish"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ..core.approval import ApprovalManager
from ..core.manifest import format_release_body, generate_release_manifest
from ..core.publish_saga import PublishSaga
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..github.client import GitHubClient
from ..models import ApprovalType, TaskLock, TaskStatus

console = Console()


def run_publish(project_path: Path, json_output: bool = False) -> bool:
    """发布版本"""
    result: dict[str, Any] = {
        "success": False,
        "version": None,
        "tag": None,
        "release_url": None,
        "status": None,
        "steps": [],
    }

    sm = StateMachine(project_path)
    sm.load()
    current = sm.current_status
    task_lock = sm.task_lock
    if current not in (
        TaskStatus.PR_READY,
        TaskStatus.MERGING,
        TaskStatus.TAGGING,
        TaskStatus.RELEASING,
        TaskStatus.PUBLISH_INCOMPLETE,
    ):
        result["steps"].append(
            {"step": "check_state", "status": "error", "message": f"当前状态为 {current.value}，无法发布"}
        )
        _output(result, json_output)
        return False

    version = task_lock.version if task_lock else None
    if not version:
        result["steps"].append({"step": "check_version", "status": "error", "message": "未找到版本信息"})
        _output(result, json_output)
        return False
    result["version"] = version

    if not task_lock or not task_lock.merge_sha:
        result["steps"].append({"step": "check_merge_sha", "status": "error", "message": "merge_sha 不存在，无法发布"})
        _output(result, json_output)
        return False
    merge_sha = task_lock.merge_sha

    git = GitOps(project_path)
    if not git.is_repo():
        result["steps"].append({"step": "check_git", "status": "error", "message": "当前目录不是 Git 仓库"})
        _output(result, json_output)
        return False

    try:
        from .approve import _compute_content_hash

        actual_content_hash = _compute_content_hash(project_path, task_lock, git=git)
        ApprovalManager(project_path).validate_approval(
            task_lock,
            actual_content_hash=actual_content_hash,
            expected_type=ApprovalType.FINAL_RELEASE,
        )
        result["steps"].append({"step": "validate_approval", "status": "ok", "message": "最终发布审批验证通过"})
    except Exception as e:
        result["steps"].append(
            {"step": "validate_approval", "status": "error", "message": f"最终发布审批验证失败: {e}"}
        )
        _output(result, json_output)
        return False

    client = GitHubClient(project_root=project_path)

    try:
        remote_sha = client.get_commit_sha(merge_sha)
        if not remote_sha:
            result["steps"].append(
                {"step": "verify_merge_sha", "status": "error", "message": f"merge SHA {merge_sha[:8]} 在远程不存在"}
            )
            _output(result, json_output)
            return False
        if not client.is_commit_on_branch(merge_sha, git.get_default_branch()):
            result["steps"].append(
                {
                    "step": "verify_merge_sha",
                    "status": "error",
                    "message": "merge SHA 不在默认分支",
                }
            )
            _output(result, json_output)
            return False
        result["steps"].append(
            {"step": "verify_merge_sha", "status": "ok", "message": f"merge SHA 验证通过: {merge_sha[:8]}"}
        )
    except Exception as e:
        result["steps"].append({"step": "verify_merge_sha", "status": "error", "message": f"验证 merge SHA 失败: {e}"})
        _output(result, json_output)
        return False
    try:
        if current == TaskStatus.PR_READY:
            sm.transition(TaskStatus.MERGING)
            current = TaskStatus.MERGING
        if current == TaskStatus.MERGING:
            sm.transition(TaskStatus.TAGGING)
            current = TaskStatus.TAGGING
    except Exception as e:
        result["steps"].append(
            {"step": "state_to_tagging", "status": "error", "message": f"状态转换到 TAGGING 失败: {e}"}
        )
        _output(result, json_output)
        return False

    tag_name = version
    try:
        saga = PublishSaga(client, git)
        saga.ensure_tag(tag_name, merge_sha)
        result["tag"] = tag_name
        result["steps"].append(
            {"step": "create_tag", "status": "ok", "message": f"Git 标签已创建并推送: {tag_name} -> {merge_sha[:8]}"}
        )
    except Exception as e:
        result["steps"].append({"step": "create_tag", "status": "error", "message": f"创建/推送 Git 标签失败: {e}"})
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        _output(result, json_output)
        return False
    try:
        sm.transition(TaskStatus.RELEASING)
    except Exception as e:
        result["steps"].append(
            {"step": "state_to_releasing", "status": "warn", "message": f"状态转换到 RELEASING 失败: {e}"}
        )

    try:
        manifest = generate_release_manifest(task_lock, merge_sha=merge_sha, release_url="")
        release_body = format_release_body(manifest)
        release_url = saga.ensure_release(
            tag_name,
            f"Release {version}",
            release_body,
            manifest["manifest_hash"],
        )
        result["release_url"] = release_url
        active_lock = sm.task_lock
        if active_lock is None:
            raise RuntimeError("发布状态丢失")
        active_lock.manifest_hash = manifest["manifest_hash"]
        active_lock.release_url = release_url
        active_lock.published_at = datetime.now(UTC).isoformat()
        sm.save()
        result["steps"].append(
            {"step": "create_release", "status": "ok", "message": f"GitHub Release 已创建: {release_url}"}
        )
    except Exception as e:
        result["steps"].append(
            {"step": "create_release", "status": "error", "message": f"创建 GitHub Release 失败: {e}"}
        )
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        result["status"] = "PUBLISH_INCOMPLETE"
        _output(result, json_output)
        return False

    try:
        cleanup_steps = _perform_cleanup(client, git, task_lock)
        result["steps"].extend(cleanup_steps)
        if any(step["status"] != "ok" for step in cleanup_steps):
            sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
            result["status"] = "PUBLISH_INCOMPLETE"
            _output(result, json_output)
            return False
    except Exception as e:
        result["steps"].append({"step": "cleanup", "status": "error", "message": f"Cleanup 失败: {e}"})
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        result["status"] = "PUBLISH_INCOMPLETE"
        _output(result, json_output)
        return False
    try:
        sm.transition(TaskStatus.HANDOFF_UPDATING)
        sm.transition(TaskStatus.CLEANING)
        sm.transition(TaskStatus.COMPLETE)
        sm.transition(TaskStatus.IDLE)
        result["status"] = "IDLE"
        result["steps"].append({"step": "complete", "status": "ok", "message": "版本发布完成，状态已回到 IDLE"})
    except Exception as e:
        result["steps"].append({"step": "complete", "status": "error", "message": f"最终状态转换失败: {e}"})
        sm.transition(TaskStatus.PUBLISH_INCOMPLETE)
        result["status"] = "PUBLISH_INCOMPLETE"
        _output(result, json_output)
        return False

    result["success"] = True
    _output(result, json_output)
    return True


def _perform_cleanup(client: GitHubClient, git: GitOps, task_lock: TaskLock) -> list[dict[str, Any]]:
    """执行发布后清理"""
    steps: list[dict[str, Any]] = []
    if task_lock.remote_lock_ref:
        try:
            ref_path = task_lock.remote_lock_ref.replace("refs/", "")
            if not client.delete_reference(ref_path):
                raise RuntimeError("远程 lock ref 仍存在")
            steps.append(
                {
                    "step": "cleanup_lock_ref",
                    "status": "ok",
                    "message": f"远程 lock ref 已删除: {task_lock.remote_lock_ref}",
                }
            )
        except Exception as e:
            steps.append({"step": "cleanup_lock_ref", "status": "error", "message": f"删除远程 lock ref 失败: {e}"})
    if task_lock.branch:
        try:
            if not client.delete_branch(task_lock.branch):
                raise RuntimeError("远程分支仍存在")
            steps.append(
                {"step": "cleanup_remote_branch", "status": "ok", "message": f"远程分支已删除: {task_lock.branch}"}
            )
        except Exception as e:
            steps.append({"step": "cleanup_remote_branch", "status": "error", "message": f"删除远程分支失败: {e}"})
        try:
            if not git.delete_branch(task_lock.branch, remote=False):
                raise RuntimeError("本地分支仍存在")
            steps.append(
                {"step": "cleanup_local_branch", "status": "ok", "message": f"本地分支已删除: {task_lock.branch}"}
            )
        except Exception as e:
            steps.append({"step": "cleanup_local_branch", "status": "error", "message": f"删除本地分支失败: {e}"})
    return steps


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
                    console.print(f"  [red]X {step['message']}[/red]")
                elif step["status"] == "warn":
                    console.print(f"  [yellow]! {step['message']}[/yellow]")
