"""AVM update 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from .. import __version__
from ..update.installer import Installer

console = Console()


def run_update_check(json_output: bool = False) -> bool:
    """检查更新

    Args:
        json_output: JSON 输出格式

    Returns:
        是否有更新
    """
    installer = Installer()
    current = installer.get_current_version()

    # 简单比较版本（实际应查询 PyPI）
    has_update = current != __version__ and current != "not installed"

    if json_output:
        print(
            json.dumps(
                {
                    "current_version": current,
                    "installed_version": __version__,
                    "has_update": has_update,
                },
                ensure_ascii=False,
            )
        )
    else:
        console.print(f"当前版本: {__version__}")
        if current == "not installed":
            console.print("状态: 未安装")
        elif has_update:
            console.print("[yellow]有新版本可用[/yellow]")
        else:
            console.print("[green]已是最新版本[/green]")

    return has_update


def run_update(source: Path | None = None, json_output: bool = False) -> bool:
    """更新 AVM

    Args:
        source: 更新源（wheel 文件路径）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    installer = Installer()
    result = installer.update(source)

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]更新成功[/bold green]")
        else:
            console.print("[bold red]更新失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")

    return result["success"]


def run_rollback(json_output: bool = False) -> bool:
    """回滚 AVM

    Args:
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    installer = Installer()
    result = installer.rollback()

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]回滚成功[/bold green]")
        else:
            console.print("[bold red]回滚失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")

    return result["success"]
