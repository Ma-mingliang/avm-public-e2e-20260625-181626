"""AVM launch 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.launch import run_launch
from avm.core.io import atomic_write_json
from avm.core.paths import get_task_lock_path


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


def _create_lock(project_dir: Path, status: str) -> None:
    """创建任务锁"""
    lock_path = get_task_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        lock_path,
        {
            "schema_version": 1,
            "status": status,
            "version": "v1",
            "agent": "claude-code",
            "branch": "agent/v1",
            "base_commit": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


class TestRunLaunch:
    """launch 命令测试"""

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_success(self, mock_run, mock_popen, project_dir):
        """测试启动成功"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0")
        mock_popen.return_value = MagicMock()

        result = run_launch(project_dir)
        assert result is True

    def test_launch_no_task(self, project_dir):
        """测试无活动任务"""
        result = run_launch(project_dir)
        assert result is False

    def test_launch_error_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_launch(project_dir)
        assert result is False

    def test_launch_terminal_state(self, project_dir):
        """测试终态"""
        _create_lock(project_dir, "COMPLETE")

        result = run_launch(project_dir)
        assert result is False

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_with_description(self, mock_run, mock_popen, project_dir):
        """测试带任务描述启动"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0")
        mock_popen.return_value = MagicMock()

        result = run_launch(project_dir, task_description="实现新功能")
        assert result is True

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_generates_claude_md(self, mock_run, mock_popen, project_dir):
        """测试生成 CLAUDE.md"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0")
        mock_popen.return_value = MagicMock()

        run_launch(project_dir)
        claude_md = project_dir / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert "v1" in content

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_json_output(self, mock_run, mock_popen, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0")
        mock_popen.return_value = MagicMock()

        result = run_launch(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["agent"] == "claude-code"

    @patch("avm.adapters.factory.detect_agent")
    def test_launch_unknown_agent(self, mock_detect, project_dir):
        """测试未知 Agent"""
        _create_lock(project_dir, "MODIFYING")

        result = run_launch(project_dir, agent_name="unknown-agent")
        assert result is False

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_agent_not_available(self, mock_run, mock_popen, project_dir):
        """测试 Agent 不可用"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = run_launch(project_dir)
        assert result is False

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_hermes_agent(self, mock_run, mock_popen, project_dir):
        """测试 Hermes Agent"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="hermes 1.0.0")
        mock_popen.return_value = MagicMock()

        result = run_launch(project_dir, agent_name="hermes")
        assert result is True

    @patch("avm.commands.launch.subprocess.Popen")
    @patch("avm.adapters.claude_code.subprocess.run")
    def test_launch_codex_agent(self, mock_run, mock_popen, project_dir):
        """测试 Codex Agent"""
        _create_lock(project_dir, "MODIFYING")

        mock_run.return_value = MagicMock(returncode=0, stdout="codex 1.0.0")
        mock_popen.return_value = MagicMock()

        result = run_launch(project_dir, agent_name="codex")
        assert result is True
