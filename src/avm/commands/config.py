"""AVM config 命令 - 全局配置备份与恢复"""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from ..config import get_global_dir
from ..core.backup import BackupManager

console = Console()


def _get_global_backup_mgr() -> BackupManager:
    """获取全局配置的备份管理器"""
    global_dir = get_global_dir()
    return BackupManager(global_dir)


def run_config_backup_list(json_output: bool = False) -> bool:
    """列出全局配置备份

    Args:
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    try:
        mgr = _get_global_backup_mgr()
        backups = mgr.list_backups()
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            console.print(f"[red]列出配置备份失败: {e}[/red]")
        return False

    if json_output:
        print(json.dumps({"success": True, "backups": backups}, ensure_ascii=False, indent=2))
        return True

    if not backups:
        console.print("[yellow]没有配置备份记录[/yellow]")
        return True

    table = Table(title="配置备份列表")
    table.add_column("备份名称", style="cyan")
    table.add_column("版本", style="green")
    table.add_column("时间", style="dim")
    table.add_column("文件数", justify="right")

    for backup in backups:
        table.add_row(
            backup.get("backup_name", ""),
            backup.get("version", ""),
            backup.get("timestamp", ""),
            str(len(backup.get("files", []))),
        )

    console.print(table)
    return True


def run_config_restore(backup_id: str, json_output: bool = False) -> bool:
    """恢复全局配置备份

    Args:
        backup_id: 备份 ID（backup_name）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    if not backup_id:
        if json_output:
            print(json.dumps({"success": False, "error": "未指定备份 ID"}, ensure_ascii=False))
        else:
            console.print("[red]未指定备份 ID[/red]")
        return False

    try:
        mgr = _get_global_backup_mgr()
        mgr.restore_backup(backup_id)
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            console.print(f"[red]恢复配置失败: {e}[/red]")
        return False

    if json_output:
        print(json.dumps({"success": True, "backup_id": backup_id}, ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]配置已恢复: {backup_id}[/green]")

    return True
