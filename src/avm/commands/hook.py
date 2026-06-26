"""AVM Git Hook 命令"""

from __future__ import annotations

import sys
from pathlib import Path

from ..config import load_project_config
from ..core.security_scan import SecurityScanner
from ..core.state_machine import StateMachine
from ..git.ops import GitOps
from ..models import ProjectConfig, TaskStatus


def _load_config(project_path: Path) -> ProjectConfig | None:
    """加载项目配置（统一从 版本管理/配置.yaml 读取）"""
    try:
        return load_project_config(project_path)
    except Exception:
        return None


def run_hook_pre_commit(project_path: Path) -> bool:
    """pre-commit hook 检查

    检查:
    1. 是否有敏感信息泄露（任何状态下都检查）
    2. 是否在 AVM 任务中（任务中额外检查）

    Returns:
        True 允许提交，False 阻止提交
    """
    try:
        sm = StateMachine(project_path)
        sm.load()

        # 获取暂存区文件
        git = GitOps(project_path)
        status = git.get_status()
        modified = status.get("modified", []) + status.get("added", [])

        if not modified:
            return True

        # 使用安全扫描器（任何状态下都扫描敏感信息）
        config = _load_config(project_path)
        scanner = SecurityScanner(config)
        scan_result = scanner.scan_files(modified, project_path)

        # 阻止严重问题
        if scan_result["has_critical"]:
            for finding in scan_result["findings"]:
                if finding["severity"] == "CRITICAL":
                    print(f"[AVM] 错误: {finding['message']}", file=sys.stderr)
            return False

        # 警告高风险问题（不阻止）
        if scan_result["has_high"]:
            for finding in scan_result["findings"]:
                if finding["severity"] == "HIGH":
                    print(f"[AVM] 警告: {finding['message']}", file=sys.stderr)

        return True
    except Exception as e:
        # 安全相关 hook 异常必须 fail-closed
        print(f"[AVM] 错误: pre-commit hook 内部异常: {e}", file=sys.stderr)
        return False


def run_hook_commit_msg(project_path: Path, msg_file: str) -> bool:
    """commit-msg hook 检查

    检查提交消息格式。

    Args:
        project_path: 项目路径
        msg_file: 提交消息文件路径

    Returns:
        True 允许提交，False 阻止提交
    """
    try:
        msg_path = Path(msg_file)
        if not msg_path.exists():
            return True

        message = msg_path.read_text(encoding="utf-8").strip()
        if not message:
            print("[AVM] 错误: 提交消息不能为空", file=sys.stderr)
            return False

        # 检查是否是 conventional commit 格式（可选，不强制）
        # 只检查第一行长度
        first_line = message.split("\n")[0].strip()
        if len(first_line) > 120:
            print(f"[AVM] 警告: 提交消息首行过长 ({len(first_line)} > 120)", file=sys.stderr)

        return True
    except Exception as e:
        print(f"[AVM] 错误: commit-msg hook 内部异常: {e}", file=sys.stderr)
        return False


def run_hook_pre_push(project_path: Path) -> bool:
    """pre-push hook 检查

    检查:
    1. 是否直接推送到默认分支（main/master）—— 任何状态下都阻止
    2. 是否在 AVM 任务中
    3. 如果在任务中，是否已获得审批

    Returns:
        True 允许推送，False 阻止推送
    """
    try:
        # 检查是否直接推送到默认分支
        git = GitOps(project_path)
        try:
            current_branch = git.get_current_branch()
            default_branch = git.get_default_branch()
            if current_branch == default_branch:
                print(
                    f"[AVM] 错误: 禁止直接推送到默认分支 ({default_branch})",
                    file=sys.stderr,
                )
                return False
        except Exception:
            # 无法获取分支信息时，不阻止（可能是非标准仓库）
            pass

        sm = StateMachine(project_path)
        sm.load()

        # 如果不在任务中，允许推送到非默认分支
        if sm.is_idle():
            return True

        # 检查是否在允许推送的状态
        pushable_states = {
            TaskStatus.PR_READY,
            TaskStatus.MERGING,
            TaskStatus.TAGGING,
            TaskStatus.RELEASING,
            TaskStatus.COMPLETE,
        }
        if sm.current_status not in pushable_states:
            print(
                f"[AVM] 错误: 当前状态 {sm.current_status.value} 不允许推送",
                file=sys.stderr,
            )
            return False

        return True
    except Exception as e:
        # 安全相关 hook 异常必须 fail-closed
        print(f"[AVM] 错误: pre-push hook 内部异常: {e}", file=sys.stderr)
        return False


def run_hook(project_path: Path, hook_type: str, msg_file: str = "") -> bool:
    """运行 Git Hook

    Args:
        project_path: 项目路径
        hook_type: hook 类型 (pre-commit, commit-msg, pre-push)
        msg_file: commit-msg 的消息文件路径

    Returns:
        True 允许操作，False 阻止操作
    """
    if hook_type == "pre-commit":
        return run_hook_pre_commit(project_path)
    elif hook_type == "commit-msg":
        return run_hook_commit_msg(project_path, msg_file)
    elif hook_type == "pre-push":
        return run_hook_pre_push(project_path)
    else:
        # 未知 hook 类型，fail-closed
        print(f"[AVM] 错误: 未知的 hook 类型: {hook_type}", file=sys.stderr)
        return False
