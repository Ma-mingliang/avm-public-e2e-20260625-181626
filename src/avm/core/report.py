"""AVM 报告生成

生成接手报告、版本报告和验证报告。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import HandoverReport, TaskLock
from .io import atomic_write_json, read_json
from .paths import get_handover_report_path, get_version_dir


class ReportGenerator:
    """报告生成器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.version_dir = get_version_dir(project_root)
        self.handover_dir = self.version_dir / "交接"

    def generate_handover_report(
        self,
        task_lock: TaskLock | None = None,
        project_goal: str = "",
        architecture: str = "",
    ) -> HandoverReport:
        """生成接手报告

        Args:
            task_lock: 当前任务锁（可选）
            project_goal: 项目目标描述
            architecture: 架构描述

        Returns:
            接手报告对象
        """
        report = HandoverReport(
            formal_version=task_lock.version if task_lock else "",
            formal_branch=task_lock.branch if task_lock else "",
            base_commit=task_lock.base_commit if task_lock else "",
            generated_agent=task_lock.agent.value if task_lock else "",
            project_goal=project_goal,
            architecture=architecture,
            build_test_commands=self._get_build_test_commands(),
            recent_changes=self._get_recent_changes(),
            current_config=self._get_current_config(),
            current_risks=self._get_current_risks(),
            history_index=self._get_history_index(),
        )
        return report

    def save_report(self, report: HandoverReport) -> Path:
        """保存报告到文件

        Args:
            report: 接手报告

        Returns:
            报告文件路径
        """
        self.handover_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        version = report.formal_version or "unversioned"
        filename = f"接手报告_{version}_{timestamp}.md"
        report_path = self.handover_dir / filename

        # 渲染 Markdown
        content = self._render_markdown(report)
        report_path.write_text(content, encoding="utf-8")

        # 更新最新报告链接
        latest_path = get_handover_report_path(self.project_root)
        latest_path.write_text(content, encoding="utf-8")

        # 更新历史索引
        self._update_history_index(filename, report)

        return report_path

    def list_reports(self) -> list[dict[str, Any]]:
        """列出所有报告"""
        if not self.handover_dir.exists():
            return []

        reports = []
        for f in sorted(self.handover_dir.glob("接手报告_*.md"), reverse=True):
            reports.append(
                {
                    "filename": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
                }
            )
        return reports

    def _render_markdown(self, report: HandoverReport) -> str:
        """渲染报告为 Markdown"""
        lines = [
            "# 接手项目审查报告",
            "",
            f"**版本**: {report.formal_version or 'N/A'}",
            f"**分支**: {report.formal_branch or 'N/A'}",
            f"**基线提交**: {report.base_commit[:12] if report.base_commit else 'N/A'}",
            f"**生成时间**: {report.generated_at}",
            f"**生成 Agent**: {report.generated_agent or 'N/A'}",
            "",
            "---",
            "",
        ]

        sections = [
            ("项目目标", report.project_goal),
            ("架构概述", report.architecture),
            ("构建与测试命令", report.build_test_commands),
            ("近期变更", report.recent_changes),
            ("当前配置", report.current_config),
            ("当前风险", report.current_risks),
            ("历史遗留问题", report.legacy_issues),
            ("待办事项", report.pending_tasks),
            ("待归档文档", report.pending_doc_archives),
        ]

        for title, content in sections:
            lines.append(f"## {title}")
            lines.append("")
            lines.append(content if content else "（暂无）")
            lines.append("")

        if report.history_index:
            lines.append("## 历史报告索引")
            lines.append("")
            lines.append(report.history_index)
            lines.append("")

        if report.when_to_review_history:
            lines.append("## 何时查阅历史")
            lines.append("")
            lines.append(report.when_to_review_history)
            lines.append("")

        return "\n".join(lines)

    def _get_build_test_commands(self) -> str:
        """获取构建和测试命令"""
        commands = []
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            commands.append("- 测试: `pytest`")
            commands.append("- Lint: `ruff check`")
            commands.append("- 格式化: `ruff format`")
        package_json = self.project_root / "package.json"
        if package_json.exists():
            commands.append("- 测试: `npm test`")
            commands.append("- 构建: `npm run build`")
        if not commands:
            commands.append("（未检测到标准构建配置）")
        return "\n".join(commands)

    def _get_recent_changes(self) -> str:
        """获取近期变更摘要"""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                return "\n".join(f"- {line}" for line in lines)
        except Exception:
            pass
        return "（无法获取 Git 日志）"

    def _get_current_config(self) -> str:
        """获取当前配置摘要"""
        config_path = self.version_dir / "配置.yaml"
        if config_path.exists():
            try:
                content = config_path.read_text(encoding="utf-8")
                # 只取前 20 行
                lines = content.split("\n")[:20]
                return "```yaml\n" + "\n".join(lines) + "\n```"
            except Exception:
                pass
        return "（配置文件不存在）"

    def _get_current_risks(self) -> str:
        """获取当前风险"""
        risks = []
        # 检查未提交更改
        try:
            import subprocess

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                count = len(result.stdout.strip().split("\n"))
                risks.append(f"- 存在 {count} 个未提交的更改")
        except Exception:
            pass

        # 检查敏感文件
        for sf in [".env", ".env.local", ".env.production"]:
            if (self.project_root / sf).exists():
                risks.append(f"- 检测到敏感文件: {sf}")

        return "\n".join(risks) if risks else "（未检测到明显风险）"

    def _get_history_index(self) -> str:
        """获取历史报告索引"""
        index_path = self.handover_dir / "索引.json"
        if not index_path.exists():
            return ""

        try:
            index = read_json(index_path)
            entries = index.get("reports", [])
            if not entries:
                return ""

            lines = ["| 版本 | 文件 | 生成时间 |", "|------|------|----------|"]
            for entry in entries[-10:]:  # 最近 10 条
                ver = entry.get("version", "N/A")
                fn = entry.get("filename", "N/A")
                at = entry.get("generated_at", "N/A")
                lines.append(f"| {ver} | {fn} | {at} |")
            return "\n".join(lines)
        except Exception:
            return ""

    def _update_history_index(self, filename: str, report: HandoverReport) -> None:
        """更新历史报告索引"""
        self.handover_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.handover_dir / "索引.json"

        if index_path.exists():
            try:
                index = read_json(index_path)
            except Exception:
                index = {"reports": []}
        else:
            index = {"reports": []}

        index["reports"].append(
            {
                "version": report.formal_version,
                "filename": filename,
                "generated_at": report.generated_at,
                "generated_agent": report.generated_agent,
            }
        )

        atomic_write_json(index_path, index)
