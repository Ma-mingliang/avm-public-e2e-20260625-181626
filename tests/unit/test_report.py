"""AVM 报告生成测试"""

import json

import pytest

from avm.commands.report import run_report
from avm.core.report import ReportGenerator
from avm.models import AgentType, HandoverReport, TaskLock, TaskStatus


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestReportGenerator:
    """报告生成器测试"""

    def test_generate_report_no_lock(self, project_dir):
        """测试无任务锁时生成报告"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()

        assert isinstance(report, HandoverReport)
        assert report.formal_version == ""
        assert report.generated_agent == ""

    def test_generate_report_with_lock(self, project_dir):
        """测试有任务锁时生成报告"""
        lock = TaskLock(
            status=TaskStatus.BRANCH_READY,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1",
            base_commit="abc123",
        )
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report(task_lock=lock)

        assert report.formal_version == "v1"
        assert report.formal_branch == "agent/v1"
        assert report.base_commit == "abc123"
        assert report.generated_agent == "claude-code"

    def test_save_report(self, project_dir):
        """测试保存报告"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report(project_goal="测试目标")
        path = gen.save_report(report)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "接手项目审查报告" in content
        assert "测试目标" in content

    def test_save_report_updates_latest(self, project_dir):
        """测试保存报告更新最新链接"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        gen.save_report(report)

        latest = project_dir / "版本管理" / "最新接手项目审查报告.md"
        assert latest.exists()

    def test_save_report_updates_history(self, project_dir):
        """测试保存报告更新历史索引"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        gen.save_report(report)

        index_path = project_dir / "版本管理" / "交接" / "索引.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["reports"]) == 1

    def test_list_reports_empty(self, project_dir):
        """测试列出空报告"""
        gen = ReportGenerator(project_dir)
        reports = gen.list_reports()
        assert reports == []

    def test_list_reports_after_save(self, project_dir):
        """测试保存后列出报告"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        gen.save_report(report)

        reports = gen.list_reports()
        assert len(reports) == 1
        assert "接手报告" in reports[0]["filename"]

    def test_render_markdown_sections(self, project_dir):
        """测试 Markdown 渲染包含所有章节"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report(
            project_goal="目标",
            architecture="架构",
        )
        content = gen._render_markdown(report)

        assert "## 项目目标" in content
        assert "## 架构概述" in content
        assert "## 构建与测试命令" in content
        assert "## 近期变更" in content
        assert "## 当前配置" in content
        assert "## 当前风险" in content

    def test_build_test_commands_with_pyproject(self, project_dir):
        """测试检测 pyproject.toml 构建命令"""
        (project_dir / "pyproject.toml").write_text("[tool.pytest]", encoding="utf-8")
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "pytest" in report.build_test_commands

    def test_build_test_commands_with_package_json(self, project_dir):
        """测试检测 package.json 构建命令"""
        (project_dir / "package.json").write_text("{}", encoding="utf-8")
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "npm test" in report.build_test_commands

    def test_build_test_commands_none(self, project_dir):
        """测试无构建配置"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "未检测到" in report.build_test_commands

    def test_get_current_config_with_file(self, project_dir):
        """测试读取配置文件"""
        config_path = project_dir / "版本管理" / "配置.yaml"
        config_path.write_text("project_name: test\nversion: 1.0\n", encoding="utf-8")

        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "project_name" in report.current_config

    def test_get_current_config_no_file(self, project_dir):
        """测试无配置文件"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "不存在" in report.current_config

    def test_get_current_risks_with_changes(self, project_dir):
        """测试检测未提交更改"""
        import subprocess

        subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=project_dir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=project_dir, capture_output=True)
        (project_dir / "README.md").write_text("# Test", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=project_dir, capture_output=True)
        (project_dir / "new_file.txt").write_text("uncommitted", encoding="utf-8")

        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert "未提交" in report.current_risks

    def test_get_current_risks_with_env_file(self, project_dir):
        """测试检测敏感文件"""
        (project_dir / ".env").write_text("SECRET=123", encoding="utf-8")

        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        assert ".env" in report.current_risks

    def test_get_history_index_with_entries(self, project_dir):
        """测试历史索引渲染"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report()
        gen.save_report(report)

        lock2 = TaskLock(
            status=TaskStatus.BRANCH_READY,
            version="v2",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v2",
            base_commit="def456",
        )
        report2 = gen.generate_handover_report(task_lock=lock2)
        content = gen._render_markdown(report2)
        assert "历史报告索引" in content

    def test_render_markdown_with_all_fields(self, project_dir):
        """测试所有字段渲染"""
        gen = ReportGenerator(project_dir)
        report = gen.generate_handover_report(
            project_goal="目标",
            architecture="架构",
        )
        report.legacy_issues = "遗留问题"
        report.pending_tasks = "待办事项"
        report.pending_doc_archives = "待归档"
        report.when_to_review_history = "何时查阅"

        content = gen._render_markdown(report)
        assert "遗留问题" in content
        assert "待办事项" in content
        assert "待归档" in content
        assert "何时查阅" in content


class TestRunReport:
    """report 命令测试"""

    def test_generate_report(self, project_dir):
        """测试生成报告"""
        result = run_report(project_dir, action="generate")
        assert result is True

        # 验证文件创建
        handover_dir = project_dir / "版本管理" / "交接"
        assert handover_dir.exists()
        assert len(list(handover_dir.glob("接手报告_*.md"))) == 1

    def test_list_reports_empty(self, project_dir):
        """测试列出空报告"""
        result = run_report(project_dir, action="list")
        assert result is True

    def test_list_reports_after_generate(self, project_dir):
        """测试生成后列出报告"""
        run_report(project_dir, action="generate")
        result = run_report(project_dir, action="list")
        assert result is True

    def test_json_output(self, project_dir, capsys):
        """测试 JSON 输出"""
        result = run_report(project_dir, action="generate", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert "report_path" in data
