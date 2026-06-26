"""AVM status 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.status import _get_status, _print_status, run_status


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestGetStatus:
    """_get_status 函数测试"""

    @patch("avm.commands.status.VersionCalculator")
    @patch("avm.commands.status.TaskLocker")
    @patch("avm.commands.status.GitOps")
    def test_get_status_git_repo_with_lock(self, mock_git_cls, mock_locker_cls, mock_calc_cls, project_dir):
        """测试 Git 仓库且有活动任务"""
        # Git mock
        mock_git = MagicMock()
        mock_git.detect_repo.return_value = True
        mock_git.get_current_branch.return_value = "main"
        mock_git.get_head_sha.return_value = "abc12345def67890"
        mock_git.get_uncommitted_changes.return_value = {
            "has_changes": True,
            "status": {"modified": ["file.py"], "untracked": []},
        }
        mock_git.check_hooks.return_value = {"pre-commit": True}
        mock_git_cls.return_value = mock_git

        # Lock mock
        mock_lock = MagicMock()
        mock_lock.status.is_active.return_value = True
        mock_lock.task_id = "test-id"
        mock_lock.version = "v1"
        mock_lock.agent.value = "claude-code"
        mock_lock.branch = "agent/v1"
        mock_lock.status.value = "RESERVED"
        mock_lock.started_at = "2024-01-01T00:00:00+00:00"
        mock_locker = MagicMock()
        mock_locker.get_lock.return_value = mock_lock
        mock_locker_cls.return_value = mock_locker

        # Version mock
        mock_calc = MagicMock()
        mock_calc.get_next_version.return_value = 3
        mock_calc.format_version.return_value = "v3"
        mock_calc_cls.return_value = mock_calc

        result = _get_status(project_dir)

        assert result["has_active_task"] is True
        assert result["git"]["is_repo"] is True
        assert result["git"]["branch"] == "main"
        assert result["task"]["version"] == "v1"
        assert result["version"]["next_version"] == 3

    @patch("avm.commands.status.VersionCalculator")
    @patch("avm.commands.status.TaskLocker")
    @patch("avm.commands.status.GitOps")
    def test_get_status_not_git_repo(self, mock_git_cls, mock_locker_cls, mock_calc_cls, project_dir):
        """测试非 Git 仓库"""
        mock_git = MagicMock()
        mock_git.detect_repo.return_value = False
        mock_git_cls.return_value = mock_git

        mock_locker = MagicMock()
        mock_locker.get_lock.return_value = None
        mock_locker_cls.return_value = mock_locker

        mock_calc = MagicMock()
        mock_calc.get_next_version.return_value = 1
        mock_calc.format_version.return_value = "v1"
        mock_calc_cls.return_value = mock_calc

        result = _get_status(project_dir)

        assert result["git"]["is_repo"] is False
        assert result["has_active_task"] is False

    @patch("avm.commands.status.VersionCalculator")
    @patch("avm.commands.status.TaskLocker")
    @patch("avm.commands.status.GitOps")
    def test_get_status_no_active_task(self, mock_git_cls, mock_locker_cls, mock_calc_cls, project_dir):
        """测试无活动任务"""
        mock_git = MagicMock()
        mock_git.detect_repo.return_value = True
        mock_git.get_current_branch.return_value = "main"
        mock_git.get_head_sha.return_value = "abc12345def67890"
        mock_git.get_uncommitted_changes.return_value = {"has_changes": False, "status": {}}
        mock_git.check_hooks.return_value = {}
        mock_git_cls.return_value = mock_git

        mock_locker = MagicMock()
        mock_locker.get_lock.return_value = None
        mock_locker_cls.return_value = mock_locker

        mock_calc = MagicMock()
        mock_calc.get_next_version.return_value = 1
        mock_calc.format_version.return_value = "v1"
        mock_calc_cls.return_value = mock_calc

        result = _get_status(project_dir)

        assert result["has_active_task"] is False
        assert result["task"]["has_active_task"] is False

    @patch("avm.commands.status.VersionCalculator")
    @patch("avm.commands.status.TaskLocker")
    @patch("avm.commands.status.GitOps")
    def test_get_status_version_error(self, mock_git_cls, mock_locker_cls, mock_calc_cls, project_dir):
        """测试版本计算失败"""
        mock_git = MagicMock()
        mock_git.detect_repo.return_value = False
        mock_git_cls.return_value = mock_git

        mock_locker = MagicMock()
        mock_locker.get_lock.return_value = None
        mock_locker_cls.return_value = mock_locker

        mock_calc = MagicMock()
        mock_calc.get_next_version.side_effect = Exception("no git tags")
        mock_calc_cls.return_value = mock_calc

        result = _get_status(project_dir)

        assert "error" in result["version"]


class TestRunStatus:
    """run_status 函数测试"""

    @patch("avm.commands.status._get_status")
    def test_run_status_active(self, mock_get_status, project_dir):
        """测试有活动任务时返回 True"""
        mock_get_status.return_value = {
            "has_active_task": True,
            "project_path": str(project_dir),
            "git": {},
            "task": {},
            "version": {},
            "hooks": {},
        }
        result = run_status(project_dir)
        assert result is True

    @patch("avm.commands.status._get_status")
    def test_run_status_no_active(self, mock_get_status, project_dir):
        """测试无活动任务时仍返回 True（命令成功）"""
        mock_get_status.return_value = {
            "has_active_task": False,
            "project_path": str(project_dir),
            "git": {},
            "task": {},
            "version": {},
            "hooks": {},
        }
        result = run_status(project_dir)
        assert result is True

    @patch("avm.commands.status._get_status")
    def test_run_status_json(self, mock_get_status, project_dir, capsys):
        """测试 JSON 输出"""
        mock_get_status.return_value = {"has_active_task": False, "git": {"is_repo": True}}
        result = run_status(project_dir, json_output=True)
        assert result is True
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "git" in data

    @patch("avm.commands.status._get_status", side_effect=Exception("test error"))
    def test_run_status_error(self, _mock, project_dir):
        """测试异常处理"""
        result = run_status(project_dir)
        assert result is False

    @patch("avm.commands.status._get_status", side_effect=Exception("test error"))
    def test_run_status_error_json(self, _mock, project_dir, capsys):
        """测试异常 JSON 输出"""
        result = run_status(project_dir, json_output=True)
        assert result is False
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "error" in data


class TestPrintStatus:
    """_print_status 函数测试"""

    def test_print_status_with_active_task(self):
        """测试打印有活动任务的状态"""
        result = {
            "project_path": "/tmp",
            "git": {
                "is_repo": True,
                "branch": "main",
                "head_sha": "abc12345",
                "has_changes": True,
                "modified_count": 2,
                "untracked_count": 1,
            },
            "task": {
                "has_active_task": True,
                "version": "v1",
                "agent": "claude-code",
                "branch": "agent/v1",
                "status": "RESERVED",
                "started_at": "2024-01-01",
            },
            "version": {"next_version": 3, "next_formatted": "v3"},
            "hooks": {"pre-commit": True, "commit-msg": False},
        }
        _print_status(result)

    def test_print_status_no_git(self):
        """测试打印非 Git 仓库状态"""
        result = {
            "project_path": "/tmp",
            "git": {"is_repo": False},
            "task": {"has_active_task": False},
            "version": {"next_version": 1, "next_formatted": "v1"},
            "hooks": {},
        }
        _print_status(result)

    def test_print_status_clean_workdir(self):
        """测试打印工作区干净的状态"""
        result = {
            "project_path": "/tmp",
            "git": {"is_repo": True, "branch": "main", "head_sha": "abc12345", "has_changes": False},
            "task": {"has_active_task": False},
            "version": {"next_version": 1, "next_formatted": "v1"},
            "hooks": {},
        }
        _print_status(result)

    def test_print_status_version_error(self):
        """测试版本信息有错误"""
        result = {
            "project_path": "/tmp",
            "git": {"is_repo": False},
            "task": {"has_active_task": False},
            "version": {"error": "no git tags"},
            "hooks": {},
        }
        _print_status(result)
