"""AVM approve 命令"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from ..core.approval import ApprovalManager
from ..core.hashing import compute_approval_hash, compute_file_sha256, compute_string_sha256
from ..core.locking import TaskLocker
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..git.versioning import VersionCalculator
from ..models import ApprovalType, TaskLock, TaskStatus

console = Console()


def run_approve(
    project_path: Path,
    approver: str | None = None,
    notes: str = "",
    json_output: bool = False,
) -> bool:
    """用户审批

    Args:
        project_path: 项目路径
        approver: 审批人（默认从环境获取）
        notes: 审批备注
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "approval_id": None,
        "status": None,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    task_lock = sm.task_lock

    # 2. 检查是否需要审批
    if current not in (TaskStatus.WAIT_START_APPROVAL, TaskStatus.WAIT_FINAL_APPROVAL):
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，不需要审批",
            }
        )
        _output(result, json_output)
        return False

    if task_lock is None:
        result["steps"].append(
            {
                "step": "check_lock",
                "status": "error",
                "message": "未找到任务锁",
            }
        )
        _output(result, json_output)
        return False

    # 3. 确定审批类型
    if current == TaskStatus.WAIT_START_APPROVAL:
        approval_type = ApprovalType.START
        next_status = TaskStatus.RESERVED
    else:
        approval_type = ApprovalType.FINAL_RELEASE
        next_status = TaskStatus.PR_READY

    # 4. 获取审批人
    if not approver:
        import os

        approver = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    # 5. 计算内容哈希（绑定 base_commit、文件 SHA-256、配置）
    content_hash = ""
    try:
        content_hash = _compute_content_hash(project_path, task_lock)
        result["steps"].append(
            {
                "step": "compute_content_hash",
                "status": "ok",
                "message": f"内容哈希已计算: {content_hash[:16]}...",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "compute_content_hash",
                "status": "error",
                "message": f"计算内容哈希失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 6. 创建审批记录
    approval_mgr = ApprovalManager(project_path)
    try:
        record = approval_mgr.create_approval(
            task_lock=task_lock,
            approval_type=approval_type,
            approver=approver,
            notes=notes,
            content_hash=content_hash,
        )
        result["approval_id"] = record.approval_id
        result["steps"].append(
            {
                "step": "create_approval",
                "status": "ok",
                "message": f"审批记录已创建: {record.approval_id}",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "create_approval",
                "status": "error",
                "message": f"创建审批记录失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 7. 状态转换 + 后续事务
    if approval_type == ApprovalType.START:
        # START 审批：执行完整的预留→锁→分支事务
        success = _execute_start_transaction(project_path, sm, task_lock, record.approval_id, result, json_output)
        if not success:
            _output(result, json_output)
            return False
    else:
        # FINAL_RELEASE 审批：直接转换到 PR_READY
        try:
            sm.transition(next_status, {"approval_id": record.approval_id})
            result["status"] = next_status.value
            result["steps"].append(
                {
                    "step": "state_transition",
                    "status": "ok",
                    "message": f"状态已转换为 {next_status.value}",
                }
            )
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

    result["success"] = True
    _output(result, json_output)
    return True


def _compute_content_hash(project_path: Path, task_lock: Any) -> str:
    """计算内容哈希，绑定 base_commit、文件 SHA-256、配置

    Args:
        project_path: 项目路径
        task_lock: 当前任务锁

    Returns:
        内容哈希值

    Raises:
        RuntimeError: 当无法获取文件列表或计算哈希时
    """
    git = GitOps(project_path)

    # 获取暂存区和已修改文件
    try:
        status = git.get_status()
        tracked_files = sorted(set(status.get("modified", []) + status.get("added", [])))
    except Exception:
        tracked_files = []

    # 计算文件清单哈希
    file_manifest = []
    for f in tracked_files:
        file_path = project_path / f
        if file_path.exists() and file_path.is_file():
            sha = compute_file_sha256(file_path)
            file_manifest.append({"path": f, "sha256": sha})

    # 计算配置哈希
    config_hash = ""
    config_paths = [
        project_path / "版本管理" / "配置.yaml",
        project_path / ".claude" / "avm.json",
    ]
    for cp in config_paths:
        if cp.exists():
            config_hash = compute_file_sha256(cp)
            break

    # 使用 compute_approval_hash 计算最终哈希
    return compute_approval_hash(
        base_commit=task_lock.base_commit or "",
        file_manifest=file_manifest,
        commit_message_hash=compute_string_sha256(task_lock.version or ""),
        pr_body_hash="",
        release_body_hash="",
        config_hash=config_hash,
    )


def _execute_start_transaction(
    project_path: Path,
    sm: StateMachine,
    task_lock: TaskLock | None,
    approval_id: str,
    result: dict,
    json_output: bool,
) -> bool:
    """执行 START 审批后的完整事务

    流程：预留版本 → 获取本地锁 → 远程原子锁 → 建分支并切换 → BRANCH_READY

    任何步骤失败都会回滚已执行的步骤。
    """
    git = GitOps(project_path)

    # 从状态机获取任务信息
    lock = sm.task_lock
    if lock is None:
        result["steps"].append({"step": "start_transaction", "status": "error", "message": "任务锁不存在"})
        return False

    version_str = lock.version
    branch = lock.branch
    base_commit = lock.base_commit

    # 解析版本号
    ver_match = re.match(r"^v(\d+)$", version_str)
    if not ver_match:
        result["steps"].append(
            {"step": "start_transaction", "status": "error", "message": f"无法解析版本号: {version_str}"}
        )
        return False
    ver_num = int(ver_match.group(1))

    # 步骤 A: 预留版本号
    try:
        calc = VersionCalculator(project_path)
        calc.reserve_version(ver_num)
        result["steps"].append({"step": "reserve_version", "status": "ok", "message": f"版本 {version_str} 已预留"})
    except Exception as e:
        result["steps"].append({"step": "reserve_version", "status": "error", "message": f"版本预留失败: {e}"})
        return False

    # 步骤 B: 更新本地任务锁状态为 RESERVED
    try:
        locker = TaskLocker(project_path)
        existing_lock = locker.get_lock()
        if existing_lock is not None:
            # 锁已存在（start 命令创建），更新状态
            locker.update_lock(status=TaskStatus.RESERVED)
            result["steps"].append({"step": "acquire_lock", "status": "ok", "message": "本地任务锁已更新为 RESERVED"})
        else:
            # 锁不存在，获取新锁
            lock.status = TaskStatus.RESERVED
            locker.acquire_lock(lock)
            result["steps"].append({"step": "acquire_lock", "status": "ok", "message": "本地任务锁已获取"})
    except Exception as e:
        result["steps"].append({"step": "acquire_lock", "status": "error", "message": f"获取本地锁失败: {e}"})
        return False

    # 步骤 C: 远程原子锁（best effort，失败不阻断）
    remote_lock_created = False
    try:
        from ..github.client import GitHubClient

        gh = GitHubClient()
        if gh.repo_owner and gh.repo_name:
            lock_ref = "refs/heads/avm/system-lock"
            remote_lock_created = gh.create_reference(lock_ref, base_commit)
            if remote_lock_created:
                result["steps"].append({"step": "remote_lock", "status": "ok", "message": "远程原子锁已创建"})
            else:
                result["steps"].append(
                    {"step": "remote_lock", "status": "warn", "message": "远程锁已存在（可能有其他任务进行中）"}
                )
        else:
            result["steps"].append(
                {"step": "remote_lock", "status": "warn", "message": "未配置 GitHub 仓库，跳过远程锁"}
            )
    except Exception as e:
        result["steps"].append({"step": "remote_lock", "status": "warn", "message": f"远程锁创建失败（非阻断）: {e}"})

    # 步骤 D: 创建分支并切换
    try:
        if not git.create_branch(branch, base_commit):
            raise RuntimeError(f"创建分支失败: {branch}")
        if not git.checkout(branch):
            # 回滚：删除分支
            git.delete_branch(branch)
            raise RuntimeError(f"切换分支失败: {branch}")
        result["steps"].append({"step": "create_branch", "status": "ok", "message": f"分支 {branch} 已创建并切换"})
    except Exception as e:
        result["steps"].append({"step": "create_branch", "status": "error", "message": f"分支操作失败: {e}"})
        # 回滚：释放锁、删除远程锁
        _rollback_transaction(project_path, locker, remote_lock_created, branch)
        return False

    # 步骤 E: 状态转换链 RESERVED → LOCKED → BRANCH_READY
    try:
        sm.transition(TaskStatus.RESERVED, {"approval_id": approval_id})
        sm.transition(TaskStatus.LOCKED)
        sm.transition(TaskStatus.BRANCH_READY)
        result["status"] = TaskStatus.BRANCH_READY.value
        result["steps"].append(
            {
                "step": "state_transition",
                "status": "ok",
                "message": f"状态已转换为 {TaskStatus.BRANCH_READY.value}",
            }
        )
    except Exception as e:
        result["steps"].append({"step": "state_transition", "status": "error", "message": f"状态转换失败: {e}"})
        _rollback_transaction(project_path, locker, remote_lock_created, branch)
        return False

    return True


def _rollback_transaction(
    project_path: Path,
    locker: TaskLocker,
    remote_lock_created: bool,
    branch: str,
) -> None:
    """回滚已执行的事务步骤"""
    try:
        locker.release_lock()
    except Exception:
        pass

    try:
        if remote_lock_created:
            from ..github.client import GitHubClient

            gh = GitHubClient()
            gh.delete_reference("heads/avm/system-lock")
    except Exception:
        pass

    try:
        git = GitOps(project_path)
        git.delete_branch(branch)
    except Exception:
        pass


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]审批通过[/bold green]")
            console.print(f"  审批ID: {result['approval_id']}")
            console.print(f"  新状态: {result['status']}")
        else:
            console.print("[bold red]审批失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
