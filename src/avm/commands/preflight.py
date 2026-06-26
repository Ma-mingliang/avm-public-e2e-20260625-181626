"""AVM preflight 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..adapters.factory import detect_agent, get_adapter
from ..config import load_project_config
from ..core.classifier import TaskClassifier
from ..core.security_scan import SecurityScanner
from ..models import AgentType, ProjectConfig, TaskType

console = Console()


def _load_config(project_path: Path) -> ProjectConfig | None:
    """加载项目配置（统一从 版本管理/配置.yaml 读取）"""
    try:
        return load_project_config(project_path)
    except Exception:
        return None


def run_preflight(
    project_path: Path,
    agent: str | None = None,
    task: str = "",
    changed_files: list[str] | None = None,
    json_output: bool = False,
) -> bool:
    """修改前预检

    Args:
        project_path: 项目路径
        agent: 指定 Agent（可选，自动检测）
        task: 任务描述
        changed_files: 变更文件列表（用于分类和安全扫描）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "agent": None,
        "task_type": None,
        "checks": [],
        "steps": [],
    }

    config = _load_config(project_path)

    # 1. 检测 Agent
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
    result["steps"].append(
        {
            "step": "detect_agent",
            "status": "ok",
            "message": f"检测到 Agent: {adapter.name}",
        }
    )

    # 2. 任务分类
    if changed_files:
        classifier = TaskClassifier(config)
        task_type = classifier.classify(changed_files, task, project_path)
        result["task_type"] = task_type.value
        result["steps"].append(
            {
                "step": "classify",
                "status": "ok",
                "message": f"任务分类: {task_type.value}",
            }
        )

        # 阻断不明确的任务
        if task_type == TaskType.BLOCKED_UNCLEAR:
            result["steps"].append(
                {
                    "step": "classify",
                    "status": "error",
                    "message": "任务类型无法确定或包含缺失文件，已阻断",
                }
            )
            _output(result, json_output)
            return False

    # 3. 安全扫描
    if changed_files:
        scanner = SecurityScanner(config)
        scan_result = scanner.scan_files(changed_files, project_path)

        if scan_result.get("error"):
            result["steps"].append(
                {
                    "step": "security_scan",
                    "status": "warn",
                    "message": f"安全扫描异常: {scan_result['error']}",
                }
            )
        elif scan_result["has_critical"]:
            findings = scan_result["findings"]
            critical_msgs = [f["message"] for f in findings if f["severity"] == "CRITICAL"][:3]
            result["steps"].append(
                {
                    "step": "security_scan",
                    "status": "error",
                    "message": f"安全扫描发现 {len(findings)} 个严重问题: {'; '.join(critical_msgs)}",
                    "findings": findings,
                }
            )
            _output(result, json_output)
            return False
        elif scan_result["has_high"]:
            findings = scan_result["findings"]
            high_msgs = [f["message"] for f in findings if f["severity"] == "HIGH"][:3]
            result["steps"].append(
                {
                    "step": "security_scan",
                    "status": "warn",
                    "message": f"安全扫描警告: {'; '.join(high_msgs)}",
                }
            )
        else:
            result["steps"].append(
                {
                    "step": "security_scan",
                    "status": "ok",
                    "message": f"安全扫描通过 (已扫描 {scan_result['scanned']} 个文件)",
                }
            )

    # 4. Agent 预检
    try:
        preflight_result = adapter.preflight_check()
        result["checks"] = preflight_result.get("checks", [])
        passed = preflight_result.get("passed", False)

        if passed:
            result["steps"].append(
                {
                    "step": "preflight",
                    "status": "ok",
                    "message": "预检通过",
                }
            )
        else:
            failed_checks = [c for c in result["checks"] if not c.get("passed", True)]
            result["steps"].append(
                {
                    "step": "preflight",
                    "status": "error",
                    "message": f"预检未通过: {len(failed_checks)} 项检查失败",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "preflight",
                "status": "error",
                "message": f"预检执行失败: {e}",
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
            console.print("[bold green]预检通过[/bold green]")
            console.print(f"  Agent: {result['agent']}")
            if result.get("task_type"):
                console.print(f"  任务类型: {result['task_type']}")
        else:
            console.print("[bold red]预检失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
            for check in result.get("checks", []):
                if not check.get("passed", True):
                    console.print(f"  [red]✗ {check.get('name', 'unknown')}[/red]")
