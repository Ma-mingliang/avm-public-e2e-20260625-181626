"""AVM report 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..core.locking import TaskLocker
from ..core.report import ReportGenerator

console = Console()


def run_report(
    project_path: Path,
    action: str = "generate",
    json_output: bool = False,
) -> bool:
    """报告管理

    Args:
        project_path: 项目路径
        action: 操作类型（generate/list）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    try:
        if action == "list":
            return _list_reports(project_path, json_output)
        else:
            return _generate_report(project_path, json_output)
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            console.print(f"[red]错误: {e}[/red]")
        return False


def _generate_report(project_path: Path, json_output: bool) -> bool:
    """生成接手报告"""
    generator = ReportGenerator(project_path)

    # 获取当前任务锁
    locker = TaskLocker(project_path)
    task_lock = locker.get_lock()

    report = generator.generate_handover_report(task_lock=task_lock)
    report_path = generator.save_report(report)

    result = {
        "success": True,
        "report_path": str(report_path),
        "version": report.formal_version,
    }

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console.print("[bold green]接手报告已生成[/bold green]")
        console.print(f"  路径: {report_path}")
        if report.formal_version:
            console.print(f"  版本: {report.formal_version}")

    return True


def _list_reports(project_path: Path, json_output: bool) -> bool:
    """列出所有报告"""
    generator = ReportGenerator(project_path)
    reports = generator.list_reports()

    if json_output:
        print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
    else:
        if not reports:
            console.print("[dim]暂无报告[/dim]")
        else:
            console.print("[bold]接手报告列表[/bold]")
            for r in reports:
                console.print(f"  {r['filename']}")
                console.print(f"    大小: {r['size']} 字节, 修改时间: {r['modified']}")

    return True
