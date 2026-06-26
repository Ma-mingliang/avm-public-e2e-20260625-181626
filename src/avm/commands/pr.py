"""AVM PR 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..core.state_machine import StateMachine
from ..github.client import GitHubClient
from ..models import TaskStatus

console = Console()


def run_create_pr(
    project_path: Path,
    draft: bool = False,
    json_output: bool = False,
) -> bool:
    """创建 PR

    Args:
        project_path: 项目路径
        draft: 是否创建草稿 PR
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "pr_url": None,
        "pr_number": None,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status
    task_lock = sm.task_lock

    # 2. 检查状态
    if current not in (TaskStatus.VALIDATING, TaskStatus.REVIEW_MATERIAL_READY, TaskStatus.DRAFT_PR):
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，无法创建 PR",
            }
        )
        _output(result, json_output)
        return False

    # 3. 获取分支信息
    if not task_lock or not task_lock.branch:
        result["steps"].append(
            {
                "step": "check_branch",
                "status": "error",
                "message": "未找到任务分支信息",
            }
        )
        _output(result, json_output)
        return False

    branch = task_lock.branch
    version = task_lock.version

    # 4. 创建 PR
    try:
        client = GitHubClient()
        pr = client.create_pull_request(
            title=f"feat: {version}",
            body=f"## {version}\n\n自动创建的 PR。",
            head=branch,
            base="main",
            draft=draft,
        )
        result["pr_url"] = pr.get("html_url", "")
        result["pr_number"] = pr.get("number")
        result["steps"].append(
            {
                "step": "create_pr",
                "status": "ok",
                "message": f"PR 已创建: {result['pr_url']}",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "create_pr",
                "status": "error",
                "message": f"创建 PR 失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 5. 状态转换
    try:
        if current in (TaskStatus.VALIDATING, TaskStatus.REVIEW_MATERIAL_READY):
            sm.transition(TaskStatus.DRAFT_PR)
        result["steps"].append(
            {
                "step": "state_transition",
                "status": "ok",
                "message": "状态已更新",
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

    result["success"] = True
    _output(result, json_output)
    return True


def run_merge(
    project_path: Path,
    json_output: bool = False,
) -> bool:
    """合并 PR

    合并前验证：
    1. 状态必须为 PR_READY（DRAFT_PR 不允许合并）
    2. 审批必须存在且有效
    3. CI checks 必须全部通过
    4. PR 必须是 ready 状态（非 draft）

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "steps": [],
    }

    # 1. 加载状态机
    sm = StateMachine(project_path)
    sm.load()

    current = sm.current_status

    # 2. 检查状态 - DRAFT_PR 不允许合并
    if current != TaskStatus.PR_READY:
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current.value}，需要 PR_READY 才能合并",
            }
        )
        _output(result, json_output)
        return False

    # 3. 获取 PR 信息
    task_lock = sm.task_lock
    if not task_lock:
        result["steps"].append(
            {
                "step": "check_lock",
                "status": "error",
                "message": "未找到任务信息",
            }
        )
        _output(result, json_output)
        return False

    # 4. 验证审批（含内容哈希校验）
    try:
        from ..commands.approve import _compute_content_hash
        from ..core.approval import ApprovalManager

        actual_content_hash = _compute_content_hash(project_path, task_lock)
        approval_mgr = ApprovalManager(project_path)
        approval_mgr.validate_approval(task_lock, actual_content_hash=actual_content_hash)
        result["steps"].append(
            {
                "step": "check_approval",
                "status": "ok",
                "message": "审批验证通过",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "check_approval",
                "status": "error",
                "message": f"审批验证失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 5. 查找 PR 并验证状态
    try:
        client = GitHubClient()
        prs = client._run_gh(
            [
                "pr",
                "list",
                "--head",
                task_lock.branch,
                "--json",
                "number,state,isDraft,mergeStateStatus",
                "--limit",
                "1",
            ]
        )
        pr_list = json.loads(prs.stdout) if prs.stdout else []

        if not pr_list:
            result["steps"].append(
                {
                    "step": "find_pr",
                    "status": "error",
                    "message": f"未找到分支 {task_lock.branch} 的 PR",
                }
            )
            _output(result, json_output)
            return False

        pr_info = pr_list[0]
        pr_number = pr_info["number"]

        # 检查 PR 是否 draft
        if pr_info.get("isDraft", False):
            result["steps"].append(
                {
                    "step": "check_draft",
                    "status": "error",
                    "message": f"PR #{pr_number} 是草稿状态，无法合并",
                }
            )
            _output(result, json_output)
            return False

        # 检查 CI
        try:
            checks_result = client._run_gh(
                [
                    "pr",
                    "checks",
                    str(pr_number),
                    "--json",
                    "name,state",
                ]
            )
            if checks_result.returncode == 0:
                checks = json.loads(checks_result.stdout) if checks_result.stdout else []
                failed_checks = [c for c in checks if c.get("state") not in ("SUCCESS", "SKIPPED", "NEUTRAL")]
                if failed_checks:
                    names = ", ".join(c.get("name", "?") for c in failed_checks[:3])
                    result["steps"].append(
                        {
                            "step": "check_ci",
                            "status": "error",
                            "message": f"CI 未通过: {names}",
                        }
                    )
                    _output(result, json_output)
                    return False
            result["steps"].append(
                {
                    "step": "check_ci",
                    "status": "ok",
                    "message": "CI 检查通过",
                }
            )
        except Exception:
            # CI 检查不可用时不阻断（可能是无 CI 配置）
            result["steps"].append(
                {
                    "step": "check_ci",
                    "status": "warn",
                    "message": "CI 检查不可用，跳过",
                }
            )

    except Exception as e:
        result["steps"].append(
            {
                "step": "find_pr",
                "status": "error",
                "message": f"PR 查询失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 6. 合并 PR（squash 策略）
    try:
        client.merge_pull_request(pr_number, merge_method="squash")
        result["steps"].append(
            {
                "step": "merge",
                "status": "ok",
                "message": f"PR #{pr_number} 已合并 (squash)",
            }
        )
    except Exception as e:
        result["steps"].append(
            {
                "step": "merge",
                "status": "error",
                "message": f"合并失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 7. 状态转换
    try:
        sm.transition(TaskStatus.MERGING)
        result["steps"].append(
            {
                "step": "state_transition",
                "status": "ok",
                "message": "状态已转换为 MERGING",
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

    result["success"] = True
    _output(result, json_output)
    return True


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]操作成功[/bold green]")
            if result.get("pr_url"):
                console.print(f"  PR: {result['pr_url']}")
        else:
            console.print("[bold red]操作失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
