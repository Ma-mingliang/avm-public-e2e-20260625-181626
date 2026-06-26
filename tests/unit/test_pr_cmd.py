"""AVM PR 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.pr import run_create_pr, run_merge
from avm.core.io import atomic_write_json
from avm.core.paths import get_task_lock_path


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


def _create_lock(project_dir: Path, status: str, branch: str = "agent/v1") -> None:
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
            "branch": branch,
            "base_commit": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


class TestRunCreatePr:
    """create-pr 命令测试"""

    @patch("avm.commands.pr.GitHubClient")
    def test_create_pr_success(self, mock_gh_cls, project_dir):
        """测试创建 PR 成功"""
        _create_lock(project_dir, "VALIDATING")

        mock_gh = MagicMock()
        mock_gh.create_pull_request.return_value = {
            "html_url": "https://github.com/test/pr/1",
            "number": 1,
        }
        mock_gh_cls.return_value = mock_gh

        result = run_create_pr(project_dir)
        assert result is True

    def test_create_pr_wrong_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "RESERVED")

        result = run_create_pr(project_dir)
        assert result is False

    def test_create_pr_no_branch(self, project_dir):
        """测试无分支信息"""
        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "VALIDATING",
                "version": "v1",
                "agent": "claude-code",
                "branch": "",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
            },
        )

        result = run_create_pr(project_dir)
        assert result is False

    @patch("avm.commands.pr.GitHubClient")
    def test_create_pr_json(self, mock_gh_cls, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "VALIDATING")

        mock_gh = MagicMock()
        mock_gh.create_pull_request.return_value = {
            "html_url": "https://github.com/test/pr/1",
            "number": 1,
        }
        mock_gh_cls.return_value = mock_gh

        result = run_create_pr(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True

    @patch("avm.commands.pr.GitHubClient")
    def test_create_pr_draft(self, mock_gh_cls, project_dir):
        """测试创建草稿 PR"""
        _create_lock(project_dir, "VALIDATING")

        mock_gh = MagicMock()
        mock_gh.create_pull_request.return_value = {
            "html_url": "https://github.com/test/pr/1",
            "number": 1,
        }
        mock_gh_cls.return_value = mock_gh

        result = run_create_pr(project_dir, draft=True)
        assert result is True


class TestRunMerge:
    """merge 命令测试"""

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_success(self, mock_gh_cls, project_dir):
        """测试合并成功"""
        _create_lock(project_dir, "PR_READY")

        mock_gh = MagicMock()
        # PR list response
        pr_list_result = MagicMock()
        pr_list_result.stdout = json.dumps([{"number": 1, "state": "OPEN", "isDraft": False}])
        # CI checks response
        checks_result = MagicMock()
        checks_result.returncode = 0
        checks_result.stdout = json.dumps([])

        def run_gh_side_effect(args):
            if "checks" in args:
                return checks_result
            return pr_list_result

        mock_gh._run_gh.side_effect = run_gh_side_effect
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as mock_approval_cls:
            mock_approval = MagicMock()
            mock_approval.validate_approval.return_value = True
            mock_approval_cls.return_value = mock_approval

            result = run_merge(project_dir)
            assert result is True

    def test_merge_wrong_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "RESERVED")

        result = run_merge(project_dir)
        assert result is False
