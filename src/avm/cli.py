"""AVM CLI 入口"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from . import __version__

app = typer.Typer(
    name="avm",
    help="智能体版本管理器 - Agent Version Manager",
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """显示版本"""
    if value:
        console.print(f"AVM 版本: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True, help="显示版本"
    ),
) -> None:
    """智能体版本管理器 (AVM) - 管理 Claude Code、Hermes、Codex 的版本工作流"""


@app.command()
def doctor(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """检查环境和配置"""
    from .commands.doctor import run_doctor

    project_path = Path(project) if project else Path.cwd()
    success = run_doctor(project_path, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def install(
    path: str | None = typer.Option(None, "--path", help="安装路径"),
) -> None:
    """安装AVM"""
    from .commands.install import run_install

    install_path = Path(path) if path else None
    success = run_install(install_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def update_check(
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """检查更新"""
    from .commands.update import run_update_check

    has_update = run_update_check(json_output)
    raise typer.Exit(code=0 if has_update else 2)


@app.command()
def update() -> None:
    """更新AVM"""
    from .commands.update import run_update

    success = run_update()
    raise typer.Exit(code=0 if success else 1)


@app.command()
def rollback() -> None:
    """回滚AVM"""
    from .commands.update import run_rollback

    success = run_rollback()
    raise typer.Exit(code=0 if success else 1)


@app.command("init-project")
def init_project(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    name: str | None = typer.Option(None, "--name", "-n", help="项目名称"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """初始化项目"""
    from .commands.init_project import run_init_project

    project_path = Path(project) if project else Path.cwd()
    success = run_init_project(project_path, name, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def status(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """显示项目状态"""
    from .commands.status import run_status

    project_path = Path(project) if project else Path.cwd()
    success = run_status(project_path, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def preflight(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    agent: str = typer.Option("claude-code", "--agent", "-a", help="Agent类型"),
    task: str = typer.Option("", "--task", "-t", help="任务描述"),
    files: list[str] = typer.Option([], "--files", "-f", help="变更文件列表"),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """修改前预检"""
    from .commands.preflight import run_preflight

    project_path = Path(project) if project else Path.cwd()
    success = run_preflight(project_path, agent, task, files or None, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def start(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    version: str = typer.Option("", "--version", help="版本号"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """开始任务"""
    from .commands.start import run_start

    project_path = Path(project) if project else Path.cwd()
    success = run_start(project_path, version, json_output=json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def checkpoint(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    message: str = typer.Option("", "--message", "-m", help="提交消息"),
) -> None:
    """阶段提交"""
    from .commands.checkpoint import run_checkpoint

    project_path = Path(project) if project else Path.cwd()
    success = run_checkpoint(project_path, message)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def validate(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """运行验证"""
    from .commands.validate import run_validate

    project_path = Path(project) if project else Path.cwd()
    success = run_validate(project_path, json_output=json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command("prepare-review")
def prepare_review(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """准备审阅材料"""
    from .commands.review import run_prepare_review

    project_path = Path(project) if project else Path.cwd()
    success = run_prepare_review(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def approve(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """用户审批"""
    from .commands.approve import run_approve

    project_path = Path(project) if project else Path.cwd()
    success = run_approve(project_path, json_output=json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command("create-pr")
def create_pr(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    draft: bool = typer.Option(False, "--draft", help="创建草稿PR"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """创建PR"""
    from .commands.pr import run_create_pr

    project_path = Path(project) if project else Path.cwd()
    success = run_create_pr(project_path, draft, json_output=json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def merge(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """合并PR"""
    from .commands.pr import run_merge

    project_path = Path(project) if project else Path.cwd()
    success = run_merge(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def publish(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """发布版本"""
    from .commands.publish import run_publish

    project_path = Path(project) if project else Path.cwd()
    success = run_publish(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def resume(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """恢复中断任务"""
    from .commands.recovery import run_resume

    project_path = Path(project) if project else Path.cwd()
    success = run_resume(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def abandon(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """废弃任务"""
    from .commands.recovery import run_abandon

    project_path = Path(project) if project else Path.cwd()
    success = run_abandon(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def recover(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """恢复任务"""
    from .commands.recovery import run_recover

    project_path = Path(project) if project else Path.cwd()
    success = run_recover(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command("document-start")
def document_start(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    files: list[str] = typer.Option([], "--files", "-f", help="文档文件"),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """开始文档任务"""
    from .commands.document import run_document_start

    project_path = Path(project) if project else Path.cwd()
    success = run_document_start(project_path, files, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command("document-complete")
def document_complete(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """完成文档任务"""
    from .commands.document import run_document_complete

    project_path = Path(project) if project else Path.cwd()
    success = run_document_complete(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command("archive-pending-docs")
def archive_pending_docs(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """归档待处理文档"""
    from .commands.document import run_archive_pending_docs

    project_path = Path(project) if project else Path.cwd()
    success = run_archive_pending_docs(project_path)
    raise typer.Exit(code=0 if success else 1)


@app.command("backup-list")
def backup_list(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """列出备份"""
    from .commands.backup import run_backup_list

    project_path = Path(project) if project else Path.cwd()
    success = run_backup_list(project_path, json_output=json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command("backup-restore")
def backup_restore(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    backup_id: str = typer.Option("", "--id", help="备份ID"),
) -> None:
    """恢复备份"""
    from .commands.backup import run_backup_restore

    project_path = Path(project) if project else Path.cwd()
    success = run_backup_restore(project_path, backup_id)
    raise typer.Exit(code=0 if success else 1)


@app.command("config-backup-list")
def config_backup_list(
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """列出配置备份"""
    from .commands.config import run_config_backup_list

    success = run_config_backup_list(json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command("config-restore")
def config_restore(
    backup_id: str = typer.Option("", "--id", help="备份ID"),
) -> None:
    """恢复配置"""
    from .commands.config import run_config_restore

    success = run_config_restore(backup_id)
    raise typer.Exit(code=0 if success else 1)


@app.command("launch")
def launch(
    agent_name: str | None = typer.Argument(None, help="Agent名称 (claude-code/hermes/codex)"),
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    task: str = typer.Option("", "--task", "-t", help="任务描述"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """启动Agent"""
    from .commands.launch import run_launch

    project_path = Path(project) if project else Path.cwd()
    success = run_launch(project_path, agent_name, task, json_output)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def hook(
    hook_type: str = typer.Argument(help="Hook类型 (pre-commit, commit-msg, pre-push)"),
    msg_file: str = typer.Argument(default="", help="提交消息文件路径 (仅 commit-msg)"),
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
) -> None:
    """Git Hook 处理"""
    from .commands.hook import run_hook

    project_path = Path(project) if project else Path.cwd()
    success = run_hook(project_path, hook_type, msg_file)
    raise typer.Exit(code=0 if success else 1)


@app.command()
def report(
    project: str | None = typer.Option(None, "--project", "-p", help="项目路径"),
    action: str = typer.Option("generate", "--action", "-a", help="操作 (generate/list)"),
    json_output: bool = typer.Option(False, "--json", help="JSON输出"),
) -> None:
    """生成或查看接手报告"""
    from .commands.report import run_report

    project_path = Path(project) if project else Path.cwd()
    success = run_report(project_path, action, json_output)
    raise typer.Exit(code=0 if success else 1)


if __name__ == "__main__":
    app()
