"""AVM install 命令"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..update.installer import Installer

console = Console()


def run_install(
    install_path: Path | None = None,
    source: Path | None = None,
    json_output: bool = False,
) -> bool:
    """安装 AVM

    Args:
        install_path: 安装目录
        source: 安装源（wheel 文件路径）
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    installer = Installer(install_path)

    result = installer.install(source)

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]安装成功[/bold green]")
        else:
            console.print("[bold red]安装失败[/bold red]")
            for step in result["steps"]:
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")

    return result["success"]
