"""AVM doctor 命令"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def run_doctor(project_path: Path, json_output: bool = False) -> bool:
    """检查环境和配置"""
    results: dict[str, Any] = {
        "python": _check_python(),
        "git": _check_git(),
        "gh": _check_gh(),
        "git_lfs": _check_git_lfs(),
        "project": _check_project(project_path),
    }

    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_results(results)

    return all(r.get("ok", False) for r in results.values())


def _check_python() -> dict[str, Any]:
    """检查Python"""
    import sys

    version = sys.version_info
    ok = version.major == 3 and version.minor >= 11
    return {
        "name": "Python",
        "ok": ok,
        "version": f"{version.major}.{version.minor}.{version.micro}",
        "message": "OK" if ok else f"需要 Python 3.11+，当前 {version.major}.{version.minor}",
    }


def _check_git() -> dict[str, Any]:
    """检查Git"""
    git_path = shutil.which("git")
    if not git_path:
        return {"name": "Git", "ok": False, "message": "Git 未安装"}

    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip().replace("git version ", "")
        return {"name": "Git", "ok": True, "version": version, "message": "OK"}
    except Exception as e:
        return {"name": "Git", "ok": False, "message": str(e)}


def _check_gh() -> dict[str, Any]:
    """检查GitHub CLI"""
    gh_path = shutil.which("gh")
    if not gh_path:
        return {"name": "GitHub CLI", "ok": False, "message": "gh 未安装"}

    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
        authenticated = "Logged in" in result.stdout or "Logged in" in result.stderr
        return {
            "name": "GitHub CLI",
            "ok": authenticated,
            "message": "已登录" if authenticated else "未登录，请运行 gh auth login",
        }
    except Exception as e:
        return {"name": "GitHub CLI", "ok": False, "message": str(e)}


def _check_git_lfs() -> dict[str, Any]:
    """检查Git LFS"""
    lfs_path = shutil.which("git-lfs")
    if not lfs_path:
        # 尝试 git lfs
        try:
            result = subprocess.run(["git", "lfs", "version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"name": "Git LFS", "ok": True, "message": "OK"}
        except Exception:
            pass
        return {"name": "Git LFS", "ok": False, "message": "Git LFS 未安装"}

    return {"name": "Git LFS", "ok": True, "message": "OK"}


def _check_project(project_path: Path) -> dict[str, Any]:
    """检查项目"""
    if not project_path.exists():
        return {"name": "项目", "ok": False, "message": f"路径不存在: {project_path}"}

    git_dir = project_path / ".git"
    if not git_dir.exists():
        return {"name": "项目", "ok": False, "message": "不是Git仓库"}

    version_dir = project_path / "版本管理"
    config_file = version_dir / "配置.yaml"
    initialized = config_file.exists()

    return {
        "name": "项目",
        "ok": True,
        "initialized": initialized,
        "message": "已初始化" if initialized else "未初始化，运行 avm init-project",
    }


def _print_results(results: dict[str, Any]) -> None:
    """打印检查结果"""
    console.print("\n[bold]AVM 环境检查[/bold]\n")

    for key, result in results.items():
        name = result.get("name", key)
        ok = result.get("ok", False)
        message = result.get("message", "")

        status = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {status} {name}: {message}")

        if "version" in result:
            console.print(f"    版本: {result['version']}")

    console.print()
