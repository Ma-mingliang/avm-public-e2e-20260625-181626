"""AVM publish 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.publish import run_publish
from avm.core.io import atomic_write_json
from avm.core.paths import get_task_lock_path


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


def _create_lock(project_dir: Path, status: str, version: str = "v1") -> None:
    """创建任务锁"""
    lock_path = get_task_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        lock_path,
        {
            "schema_version": 1,
            "status": status,
            "version": version,
            "agent": "claude-code",
            "branch": f"agent/{version}",
            "base_commit": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


class TestRunPublish:
    """publish 命令测试"""

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    @patch("avm.commands.publish.ApprovalManager")
    @patch("avm.commands.approve._compute_content_hash", return_value="test-hash")
    def test_publish_success(self, mock_hash, mock_approval_cls, mock_git_cls, mock_gh_cls, project_dir):
        """测试发布成功"""
        _create_lock(project_dir, "PR_READY")

        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        mock_gh = MagicMock()
        mock_gh.create_release.return_value = {"html_url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh

        mock_approval = MagicMock()
        mock_approval.validate_approval.return_value = True
        mock_approval_cls.return_value = mock_approval

        result = run_publish(project_dir)
        assert result is True

    def test_publish_wrong_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "RESERVED")

        result = run_publish(project_dir)
        assert result is False

    def test_publish_no_version(self, project_dir):
        """测试无版本信息"""
        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "PR_READY",
                "version": "",
                "agent": "claude-code",
                "branch": "",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
            },
        )

        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitOps")
    def test_publish_not_git_repo(self, mock_git_cls, project_dir):
        """测试非 Git 仓库"""
        _create_lock(project_dir, "PR_READY")

        mock_git = MagicMock()
        mock_git.is_repo.return_value = False
        mock_git_cls.return_value = mock_git

        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    @patch("avm.commands.publish.ApprovalManager")
    @patch("avm.commands.approve._compute_content_hash", return_value="test-hash")
    def test_publish_json_output(self, mock_hash, mock_approval_cls, mock_git_cls, mock_gh_cls, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "PR_READY")

        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        mock_gh = MagicMock()
        mock_gh.create_release.return_value = {"html_url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh

        mock_approval = MagicMock()
        mock_approval.validate_approval.return_value = True
        mock_approval_cls.return_value = mock_approval

        result = run_publish(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["version"] == "v1"
        assert data["tag"] == "v1"

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    @patch("avm.commands.publish.ApprovalManager")
    @patch("avm.commands.approve._compute_content_hash", return_value="test-hash")
    def test_publish_from_tagging_state(self, mock_hash, mock_approval_cls, mock_git_cls, mock_gh_cls, project_dir):
        """测试从 TAGGING 状态发布"""
        _create_lock(project_dir, "TAGGING")

        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        mock_gh = MagicMock()
        mock_gh.create_release.return_value = {"html_url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh

        mock_approval = MagicMock()
        mock_approval.validate_approval.return_value = True
        mock_approval_cls.return_value = mock_approval

        result = run_publish(project_dir)
        assert result is True

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    @patch("avm.commands.publish.ApprovalManager")
    @patch("avm.commands.approve._compute_content_hash", return_value="test-hash")
    def test_publish_from_incomplete_state(self, mock_hash, mock_approval_cls, mock_git_cls, mock_gh_cls, project_dir):
        """测试从 PUBLISH_INCOMPLETE 状态恢复发布"""
        _create_lock(project_dir, "PUBLISH_INCOMPLETE")

        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "abc123"
        mock_git_cls.return_value = mock_git

        mock_gh = MagicMock()
        mock_gh.create_release.return_value = {"html_url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh

        mock_approval = MagicMock()
        mock_approval.validate_approval.return_value = True
        mock_approval_cls.return_value = mock_approval

        result = run_publish(project_dir)
        assert result is True
