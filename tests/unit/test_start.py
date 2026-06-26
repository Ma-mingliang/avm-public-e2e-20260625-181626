"""AVM start 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.start import run_start


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    # 创建版本管理目录
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestRunStart:
    """start 命令测试"""

    @patch("avm.commands.start.GitOps")
    @patch("avm.commands.start.detect_agent")
    @patch("avm.commands.start.VersionCalculator")
    def test_start_success(self, mock_calc_cls, mock_detect, mock_git_cls, project_dir):
        """测试成功开始任务"""
        # Mock GitOps
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        # Mock detect_agent
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True}
        mock_detect.return_value = mock_adapter

        # Mock VersionCalculator
        mock_calc = MagicMock()
        mock_calc.get_next_version.return_value = 1
        mock_calc_cls.return_value = mock_calc

        result = run_start(project_dir)
        assert result is True

    @patch("avm.commands.start.GitOps")
    def test_start_not_git_repo(self, mock_git_cls, project_dir):
        """测试非 Git 仓库"""
        mock_git = MagicMock()
        mock_git.is_repo.return_value = False
        mock_git_cls.return_value = mock_git

        result = run_start(project_dir)
        assert result is False

    @patch("avm.commands.start.GitOps")
    def test_start_already_active(self, mock_git_cls, project_dir):
        """测试已有活动任务"""
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git

        # 创建一个活动状态的任务锁
        from avm.core.io import atomic_write_json
        from avm.core.paths import get_task_lock_path

        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "RESERVED",
                "version": "v1",
                "agent": "claude-code",
                "branch": "agent/v1",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
            },
        )

        result = run_start(project_dir)
        assert result is False

    @patch("avm.commands.start.GitOps")
    @patch("avm.commands.start.detect_agent")
    def test_start_no_agent(self, mock_detect, mock_git_cls, project_dir):
        """测试无可用 Agent"""
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_detect.return_value = None

        result = run_start(project_dir)
        assert result is False

    @patch("avm.commands.start.GitOps")
    @patch("avm.commands.start.detect_agent")
    @patch("avm.commands.start.VersionCalculator")
    def test_start_json_output(self, mock_calc_cls, mock_detect, mock_git_cls, project_dir, capsys):
        """测试 JSON 输出"""
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True}
        mock_detect.return_value = mock_adapter

        mock_calc = MagicMock()
        mock_calc.get_next_version.return_value = 1
        mock_calc_cls.return_value = mock_calc

        result = run_start(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["version"] == "v1"
