"""AVM backup 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..core.backup import BackupManager

console = Console()


def run_backup_list(
    project_path: Path,
    version: str | None = None,
    json_output: bool = False,
) -> bool:
    """列出备份

    Args:
        project_path: 项目路径
        version: 过滤版本（可选）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    backup_mgr = BackupManager(project_path)

    try:
        backups = backup_mgr.list_backups(version=version)
    except Exception as e:
        console.print(f"[red]列出备份失败: {e}[/red]")
        return False

    if json_output:
        print(json.dumps({"backups": backups}, ensure_ascii=False, indent=2))
        return True

    if not backups:
        console.print("[yellow]没有备份记录[/yellow]")
        return True

    table = Table(title="备份列表")
    table.add_column("版本", style="cyan")
    table.add_column("时间", style="green")
    table.add_column("文件数", justify="right")
    table.add_column("大小", justify="right")

    for backup in backups:
        table.add_row(
            backup.get("version", ""),
            backup.get("created_at", ""),
            str(backup.get("file_count", 0)),
            _format_size(backup.get("total_size", 0)),
        )

    console.print(table)
    return True


def run_backup_restore(
    project_path: Path,
    backup_id: str,
    target_dir: str | None = None,
    json_output: bool = False,
) -> bool:
    """恢复备份

    Args:
        project_path: 项目路径
        backup_id: 备份 ID
        target_dir: 恢复目标目录（可选）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    backup_mgr = BackupManager(project_path)

    result = {
        "success": False,
        "backup_id": backup_id,
        "restored_files": [],
        "steps": [],
    }

    try:
        target = Path(target_dir) if target_dir else None
        restored = backup_mgr.restore_backup(backup_id, target_path=target)
        if isinstance(restored, list):
            result["restored_files"] = restored
            result["success"] = True
            result["steps"].append(
                {
                    "step": "restore",
                    "status": "ok",
                    "message": f"已恢复 {len(restored)} 个文件",
                }
            )
        else:
            restored_path = Path(restored)
            if restored_path.is_dir():
                result["restored_files"] = [f.name for f in restored_path.iterdir() if f.is_file()]
            else:
                result["restored_files"] = [restored_path.name]
            result["success"] = True
            result["steps"].append(
                {
                    "step": "restore",
                    "status": "ok",
                    "message": f"已恢复到: {restored_path}",
                }
            )
    except Exception as e:
        result["steps"].append(
            {
                "step": "restore",
                "status": "error",
                "message": f"恢复失败: {e}",
            }
        )

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result["success"]

    if result["success"]:
        console.print(f"[green]备份恢复成功: {backup_id}[/green]")
        for f in result["restored_files"]:
            console.print(f"  ✓ {f}")
    else:
        console.print("[red]备份恢复失败[/red]")
        for step in result["steps"]:
            if step["status"] == "error":
                console.print(f"  ✗ {step['message']}")

    return result["success"]


def _format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
