"""AVM validate 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.validate import run_validate
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
            "status": status.upper(),
            "version": "v1",
            "agent": "claude-code",
            "branch": "agent/v1",
            "base_commit": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


class TestRunValidate:
    """validate 命令测试"""

    @patch("avm.commands.validate.detect_agent")
    def test_validate_success(self, mock_detect, project_dir):
        """测试验证成功"""
        _create_lock(project_dir, "MODIFYING")

        mock_adapter = MagicMock()
        mock_adapter.name = "Claude Code"
        mock_adapter.validate.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        result = run_validate(project_dir)
        assert result is True

    @patch("avm.commands.validate.get_adapter")
    def test_validate_failure(self, mock_get_adapter, project_dir):
        """测试验证失败"""
        _create_lock(project_dir, "MODIFYING")

        mock_adapter = MagicMock()
        mock_adapter.name = "Claude Code"
        mock_adapter.validate.return_value = {"passed": False, "errors": ["test failed"]}
        mock_get_adapter.return_value = mock_adapter

        result = run_validate(project_dir)
        assert result is False

    def test_validate_wrong_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "RESERVED")

        result = run_validate(project_dir)
        assert result is False

    @patch("avm.commands.validate.get_adapter")
    def test_validate_with_agent_specified(self, mock_get_adapter, project_dir):
        """测试指定 Agent"""
        _create_lock(project_dir, "MODIFYING")

        mock_adapter = MagicMock()
        mock_adapter.name = "Claude Code"
        mock_adapter.validate.return_value = {"passed": True, "checks": []}
        mock_get_adapter.return_value = mock_adapter

        result = run_validate(project_dir, agent="claude-code")
        assert result is True

    @patch("avm.commands.validate.detect_agent")
    @patch("avm.commands.validate.get_adapter")
    def test_validate_no_agent(self, mock_get_adapter, mock_detect, project_dir):
        """测试无可用 Agent"""
        _create_lock(project_dir, "MODIFYING")
        mock_get_adapter.side_effect = ValueError("unsupported")
        mock_detect.return_value = None

        result = run_validate(project_dir)
        assert result is False

    @patch("avm.commands.validate.detect_agent")
    def test_validate_json_output(self, mock_detect, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "MODIFYING")

        mock_adapter = MagicMock()
        mock_adapter.name = "Claude Code"
        mock_adapter.validate.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        result = run_validate(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
