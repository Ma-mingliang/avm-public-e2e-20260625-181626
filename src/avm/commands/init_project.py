"""AVM init-project 命令"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ..config import create_default_config, save_project_config
from ..core.paths import get_version_dir
from ..git.ops import GitOps

console = Console()


def run_init_project(project_path: Path, name: str | None = None, json_output: bool = False) -> bool:
    """初始化项目

    Args:
        project_path: 项目路径
        name: 项目名称（可选）
        json_output: 是否输出 JSON

    Returns:
        是否成功
    """
    try:
        result = _init_project(project_path, name)

        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_result(result)

        return result["success"]
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            console.print(f"[red]错误: {e}[/red]")
        return False


def _init_project(project_path: Path, name: str | None) -> dict[str, Any]:
    """执行项目初始化

    Args:
        project_path: 项目路径
        name: 项目名称

    Returns:
        初始化结果
    """
    project_path = Path(project_path).resolve()
    results = {
        "success": True,
        "project_path": str(project_path),
        "steps": [],
    }

    # 1. 检查是否为 Git 仓库，非 Git 目录则自动初始化
    git = GitOps(project_path)
    if not git.detect_repo():
        # 自动初始化 Git 仓库
        try:
            import subprocess

            init_result = subprocess.run(
                ["git", "init"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if init_result.returncode != 0:
                results["steps"].append(
                    {
                        "step": "git_init",
                        "status": "error",
                        "message": f"Git 初始化失败: {init_result.stderr.strip()}",
                    }
                )
                results["success"] = False
                return results
            results["steps"].append(
                {
                    "step": "git_init",
                    "status": "ok",
                    "message": "已自动初始化 Git 仓库",
                }
            )
        except Exception as e:
            results["steps"].append(
                {
                    "step": "git_init",
                    "status": "error",
                    "message": f"Git 初始化失败: {e}",
                }
            )
            results["success"] = False
            return results
    else:
        results["steps"].append(
            {
                "step": "git_check",
                "status": "ok",
                "message": "Git 仓库检测通过",
            }
        )

    # 2. 检查未提交更改
    try:
        status = git.get_status()
        has_changes = status.get("modified", []) or status.get("untracked", [])
        if has_changes:
            results["steps"].append(
                {
                    "step": "check_changes",
                    "status": "warn",
                    "message": (
                        f"检测到 {len(status.get('modified', []))} 个修改文件"
                        f"和 {len(status.get('untracked', []))} 个未跟踪文件"
                    ),
                }
            )
    except Exception:
        pass

    # 3. 创建版本管理目录结构
    version_dir = get_version_dir(project_path)
    dirs_created = []

    # 主目录
    version_dir.mkdir(parents=True, exist_ok=True)
    dirs_created.append(str(version_dir))

    # 子目录（包含设计要求的所有目录）
    subdirs = [
        "正式版本",
        "文档版本",
        "废弃版本",
        "中断任务",
        "待归档文档记录",
        "备份",
        "审批",
        "交接",
        "临时",
    ]
    for subdir in subdirs:
        sub_path = version_dir / subdir
        sub_path.mkdir(parents=True, exist_ok=True)
        dirs_created.append(str(sub_path))

    results["steps"].append(
        {
            "step": "create_dirs",
            "status": "ok",
            "message": f"创建目录结构: {len(dirs_created)} 个目录",
            "dirs": dirs_created,
        }
    )

    # 3. 创建配置文件
    project_name = name or project_path.name
    config = create_default_config(project_path, project_name)
    save_project_config(config, project_path)

    results["steps"].append(
        {
            "step": "create_config",
            "status": "ok",
            "message": f"创建配置文件: {version_dir / '配置.yaml'}",
        }
    )

    # 4. 创建版本索引
    index_path = version_dir / "版本索引.json"
    if not index_path.exists():
        index = {
            "schema_version": 1,
            "project_name": project_name,
            "created_at": datetime.now(UTC).isoformat(),
            "formal_versions": [],
            "document_versions": [],
            "abandoned_versions": [],
            "pending_archives": [],
        }
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        results["steps"].append(
            {
                "step": "create_index",
                "status": "ok",
                "message": f"创建版本索引: {index_path}",
            }
        )
    else:
        results["steps"].append(
            {
                "step": "create_index",
                "status": "skip",
                "message": "版本索引已存在",
            }
        )

    # 5. 安装 Git Hooks
    try:
        if git.install_hooks():
            hooks_status = git.check_hooks()
            installed = [k for k, v in hooks_status.items() if v]
            results["steps"].append(
                {
                    "step": "install_hooks",
                    "status": "ok",
                    "message": f"安装 Git Hooks: {', '.join(installed)}",
                }
            )
        else:
            results["steps"].append(
                {
                    "step": "install_hooks",
                    "status": "warn",
                    "message": "Git Hooks 安装失败（可手动安装）",
                }
            )
    except Exception as e:
        results["steps"].append(
            {
                "step": "install_hooks",
                "status": "warn",
                "message": f"Git Hooks 安装异常: {e}",
            }
        )

    # 6. 创建 README（如果不存在）
    readme_path = version_dir / "README.md"
    if not readme_path.exists():
        readme_content = f"""# {project_name} - 版本管理

本目录由 Agent Version Manager (AVM) 管理。

## 目录结构

- `正式版本/` - 正式版本记录
- `文档版本/` - 文档版本记录
- `备份/` - 文件备份
- `审批/` - 审批记录
- `交接/` - 交接报告
- `版本索引.json` - 版本索引
- `配置.yaml` - 项目配置

## 使用方法

使用 AVM CLI 管理版本：

```bash
avm status          # 查看状态
avm preflight       # 预检
avm start           # 开始任务
avm validate        # 验证
avm publish         # 发布
```
"""
        readme_path.write_text(readme_content, encoding="utf-8")
        results["steps"].append(
            {
                "step": "create_readme",
                "status": "ok",
                "message": f"创建 README: {readme_path}",
            }
        )

    # 7. 创建 .gitignore（如果不存在）
    gitignore_path = version_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_content = """# AVM 临时文件
*.tmp
*.lock
__pycache__/

# 任务锁（本地）
任务锁.json
"""
        gitignore_path.write_text(gitignore_content, encoding="utf-8")
        results["steps"].append(
            {
                "step": "create_gitignore",
                "status": "ok",
                "message": f"创建 .gitignore: {gitignore_path}",
            }
        )

    # 8. 扫描敏感文件
    try:
        # 扫描常见敏感文件
        sensitive_files = [".env", ".env.local", ".env.production", "id_rsa", "id_dsa"]
        found_sensitive = []
        for sf in sensitive_files:
            if (project_path / sf).exists():
                found_sensitive.append(sf)

        if found_sensitive:
            results["steps"].append(
                {
                    "step": "scan_sensitive",
                    "status": "warn",
                    "message": f"检测到敏感文件: {', '.join(found_sensitive)}，请确保已在 .gitignore 中排除",
                }
            )
        else:
            results["steps"].append(
                {
                    "step": "scan_sensitive",
                    "status": "ok",
                    "message": "未检测到常见敏感文件",
                }
            )
    except Exception as e:
        results["steps"].append(
            {
                "step": "scan_sensitive",
                "status": "skip",
                "message": f"敏感文件扫描跳过: {e}",
            }
        )

    # 9. 创建 Agent 规则文件
    try:
        _create_agent_rules(project_path, project_name)
        results["steps"].append(
            {
                "step": "create_agent_rules",
                "status": "ok",
                "message": "创建 Agent 规则文件",
            }
        )
    except Exception as e:
        results["steps"].append(
            {
                "step": "create_agent_rules",
                "status": "warn",
                "message": f"Agent 规则文件创建失败: {e}",
            }
        )

    # 10. 检查 Git LFS 建议
    try:
        # 检查是否有大文件
        large_files = []
        for ext in [".zip", ".tar.gz", ".mp4", ".mov", ".psd", ".ai"]:
            for f in project_path.rglob(f"*{ext}"):
                if f.stat().st_size > 1024 * 1024:  # > 1MB
                    large_files.append(str(f.relative_to(project_path)))

        if large_files:
            results["steps"].append(
                {
                    "step": "suggest_lfs",
                    "status": "warn",
                    "message": f"检测到 {len(large_files)} 个大文件，建议启用 Git LFS",
                }
            )
    except Exception:
        pass

    # 11. 创建基线提交和 v1 标签（仅对新初始化的仓库）
    if any(s.get("step") == "git_init" and s["status"] == "ok" for s in results["steps"]):
        try:
            import subprocess

            # 配置 git user（如果未配置）
            for key, val in [("user.email", "avm@localhost"), ("user.name", "AVM")]:
                subprocess.run(
                    ["git", "config", key, val],
                    cwd=project_path,
                    capture_output=True,
                    timeout=10,
                )

            # 暂存所有文件
            subprocess.run(
                ["git", "add", "."],
                cwd=project_path,
                capture_output=True,
                timeout=30,
            )

            # 基线提交
            commit_result = subprocess.run(
                ["git", "commit", "-m", f"chore: 初始化 {project_name} 的 AVM 版本管理"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if commit_result.returncode != 0:
                results["steps"].append(
                    {
                        "step": "baseline_commit",
                        "status": "warn",
                        "message": f"基线提交失败: {commit_result.stderr.strip()}",
                    }
                )
            else:
                results["steps"].append(
                    {
                        "step": "baseline_commit",
                        "status": "ok",
                        "message": "已创建基线提交",
                    }
                )

                # 创建 v1 标签
                tag_result = subprocess.run(
                    ["git", "tag", "-a", "v1", "-m", f"Baseline v1 for {project_name}"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if tag_result.returncode == 0:
                    results["steps"].append(
                        {
                            "step": "baseline_tag",
                            "status": "ok",
                            "message": "已创建基线标签 v1",
                        }
                    )
                else:
                    results["steps"].append(
                        {
                            "step": "baseline_tag",
                            "status": "warn",
                            "message": f"标签创建失败: {tag_result.stderr.strip()}",
                        }
                    )

                # 更新版本索引，记录 v1
                _update_index_with_baseline(version_dir, project_name)

        except Exception as e:
            results["steps"].append(
                {
                    "step": "baseline",
                    "status": "warn",
                    "message": f"基线创建异常: {e}",
                }
            )

    return results


def _update_index_with_baseline(version_dir: Path, project_name: str) -> None:
    """更新版本索引，记录基线 v1"""
    import json
    from datetime import UTC, datetime

    index_path = version_dir / "版本索引.json"
    if not index_path.exists():
        return

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return

    # 检查 v1 是否已存在
    for v in index.get("formal_versions", []):
        if v.get("version") == "v1":
            return

    index["formal_versions"].append(
        {
            "version": "v1",
            "status": "released",
            "created_at": datetime.now(UTC).isoformat(),
            "description": f"{project_name} 基线版本",
        }
    )

    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _create_agent_rules(project_path: Path, project_name: str) -> None:
    """创建 Agent 规则文件"""
    # CLAUDE.md
    claude_md = project_path / "CLAUDE.md"
    if not claude_md.exists():
        content = f"""# {project_name}

## AVM 版本管理

本项目使用 Agent Version Manager (AVM) 管理版本。

### 规则

1. 遵循 AVM 版本管理流程
2. 不得直接推送到 main 分支
3. 所有变更必须通过 PR 审批
4. 提交前运行安全扫描: `avm hook pre-commit`
5. 保持提交消息格式规范

### 常用命令

- `avm status` - 查看状态
- `avm preflight` - 预检
- `avm start` - 开始任务
- `avm validate` - 验证
- `avm publish` - 发布
"""
        claude_md.write_text(content, encoding="utf-8")

    # AGENTS.md
    agents_md = project_path / "AGENTS.md"
    if not agents_md.exists():
        content = f"""# {project_name} - Agent 配置

## 版本管理

使用 AVM (Agent Version Manager) 管理版本。

## 工作流

1. `avm preflight` - 预检
2. `avm start` - 开始任务
3. 执行修改
4. `avm validate` - 验证
5. `avm create-pr` - 创建 PR
6. `avm merge` - 合并
7. `avm publish` - 发布
"""
        agents_md.write_text(content, encoding="utf-8")


def _print_result(result: dict[str, Any]) -> None:
    """打印初始化结果"""
    if result["success"]:
        console.print("[bold green]项目初始化成功[/bold green]")
    else:
        console.print("[bold red]项目初始化失败[/bold red]")

    console.print(f"项目路径: {result['project_path']}")
    console.print("")

    for step in result.get("steps", []):
        status = step["status"]
        message = step["message"]

        if status == "ok":
            icon = "[green]✓[/green]"
        elif status == "warn":
            icon = "[yellow]⚠[/yellow]"
        elif status == "error":
            icon = "[red]✗[/red]"
        elif status == "skip":
            icon = "[dim]-[/dim]"
        else:
            icon = "?"

        console.print(f"  {icon} {message}")
