"""AVM publish 命令测试"""

import json
import re
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.publish import _perform_cleanup, run_publish
from avm.core.approval import ApprovalManager
from avm.core.io import atomic_write_json
from avm.core.paths import get_task_lock_path
from avm.core.state_machine import StateMachine
from avm.models import TaskLock


@pytest.fixture(autouse=True)
def valid_final_approval(monkeypatch):
    monkeypatch.setattr(ApprovalManager, "validate_approval", lambda *_args, **_kwargs: True)


@pytest.fixture
def project_dir(tmp_path):
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


def _create_lock(project_dir, status, version="v1", merge_sha="abc123def456"):
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
            "approved_head_sha": "approved-head",
            "merge_sha": merge_sha,
            "pr_number": 1,
        },
    )


class TestRunPublish:
    @patch("avm.commands.approve._compute_content_hash", return_value="approval-hash")
    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_uses_persisted_approved_head(self, mock_git_cls, mock_gh_cls, mock_hash, project_dir):
        """任务分支被合并删除后，发布仍必须验证最终审批时冻结的 SHA。"""
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh

        assert run_publish(project_dir) is True
        args, kwargs = mock_hash.call_args
        assert args[0] == project_dir
        assert kwargs == {"git": mock_git, "head_sha": "approved-head"}

    def test_publish_blocks_legacy_lock_without_approved_head(self, project_dir):
        """旧锁缺少冻结 SHA 时，禁止用合并后的 HEAD 猜测审批对象。"""
        _create_lock(project_dir, "MERGING")
        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        data.pop("approved_head_sha")
        atomic_write_json(lock_path, data)

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_success(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir)
        assert result is True

    def test_publish_wrong_state(self, project_dir):
        _create_lock(project_dir, "RESERVED")
        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_rejects_invalid_final_approval(self, mock_git_cls, mock_gh_cls, project_dir, monkeypatch):
        _create_lock(project_dir, "MERGING")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_head_sha.return_value = "head"
        mock_git.get_tree_sha.return_value = "tree"
        mock_git.get_status.return_value = {"modified": [], "added": []}
        mock_git.create_annotated_tag.return_value = True
        mock_git.push_tag.return_value = True
        mock_git.delete_branch.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = mock_gh_cls.return_value
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.get_tag_target.return_value = None
        mock_gh.get_release.return_value = None
        mock_gh.create_release.return_value = {"url": "https://example.invalid/v1"}
        mock_gh.delete_reference.return_value = True
        mock_gh.delete_branch.return_value = True

        def invalid(*_args, **_kwargs):
            raise RuntimeError("invalid approval")

        monkeypatch.setattr(ApprovalManager, "validate_approval", invalid)

        assert run_publish(project_dir, json_output=True) is False

    def test_publish_no_version(self, project_dir):
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
                "merge_sha": "abc123",
            },
        )
        result = run_publish(project_dir)
        assert result is False

    def test_publish_no_merge_sha(self, project_dir):
        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "PR_READY",
                "version": "v1",
                "agent": "claude-code",
                "branch": "agent/v1",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
                "merge_sha": "",
            },
        )
        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitOps")
    def test_publish_not_git_repo(self, mock_git_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = False
        mock_git_cls.return_value = mock_git
        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_json_output(self, mock_git_cls, mock_gh_cls, project_dir, capsys):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir, json_output=True)
        assert result is True
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["version"] == "v1"
        assert data["tag"] == "v1"

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_from_tagging_state(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "TAGGING")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir)
        assert result is True

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_from_incomplete_state(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PUBLISH_INCOMPLETE")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir)
        assert result is True

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_merge_sha_not_found(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = None
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir)
        assert result is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_rejects_merge_outside_default_branch(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "MERGING")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.get_default_branch.return_value = "main"
        mock_git.create_annotated_tag.return_value = True
        mock_git.push_tag.return_value = True
        mock_git.delete_branch.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.is_commit_on_branch.return_value = False
        mock_gh.get_tag_target.return_value = None
        mock_gh.get_release.return_value = None
        mock_gh.create_release.return_value = {"url": "https://example.invalid/v1"}
        mock_gh.delete_reference.return_value = True
        mock_gh.delete_branch.return_value = True
        mock_gh_cls.return_value = mock_gh

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_publish_cleanup(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh_cls.return_value = mock_gh
        result = run_publish(project_dir, json_output=True)
        assert result is True

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_cleanup_false_keeps_publish_incomplete(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.create_annotated_tag.return_value = True
        mock_git.push_tag.return_value = True
        mock_git.delete_branch.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh.delete_reference.return_value = False
        mock_gh.delete_branch.return_value = True
        mock_gh_cls.return_value = mock_gh

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_release_manifest_hash_matches_persisted_lock(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git = MagicMock()
        mock_git.is_repo.return_value = True
        mock_git.create_annotated_tag.return_value = True
        mock_git.push_tag.return_value = True
        mock_git.delete_branch.return_value = True
        mock_git_cls.return_value = mock_git
        mock_gh = MagicMock()
        mock_gh.get_commit_sha.return_value = "abc123def456"
        mock_gh.get_tag_target.return_value = None
        mock_gh.get_release.return_value = None
        mock_gh.create_release.return_value = {"url": "https://github.com/test/releases/v1"}
        mock_gh.delete_reference.return_value = True
        mock_gh.delete_branch.return_value = True
        mock_gh_cls.return_value = mock_gh

        assert run_publish(project_dir, json_output=True) is True
        body = mock_gh.create_release.call_args.kwargs["body"]
        match = re.search(r'"manifest_hash"\s*:\s*"([0-9a-f]{64})"', body)
        assert match is not None
        assert StateMachine(project_dir).load().manifest_hash == match.group(1)

    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_remote_commit_query_exception_blocks_publish(self, mock_git_cls, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git_cls.return_value.is_repo.return_value = True
        mock_gh_cls.return_value.get_commit_sha.side_effect = RuntimeError("network")

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish.PublishSaga")
    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_tag_reconciliation_failure_blocks_publish(self, mock_git_cls, mock_gh_cls, saga_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git_cls.return_value.is_repo.return_value = True
        mock_gh_cls.return_value.get_commit_sha.return_value = "abc123def456"
        saga_cls.return_value.ensure_tag.side_effect = RuntimeError("tag conflict")

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish.PublishSaga")
    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_release_reconciliation_failure_blocks_publish(self, mock_git_cls, mock_gh_cls, saga_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git_cls.return_value.is_repo.return_value = True
        mock_gh_cls.return_value.get_commit_sha.return_value = "abc123def456"
        saga_cls.return_value.ensure_tag.return_value = None
        saga_cls.return_value.ensure_release.side_effect = RuntimeError("release conflict")

        assert run_publish(project_dir, json_output=True) is False

    @patch("avm.commands.publish._perform_cleanup", side_effect=RuntimeError("cleanup crashed"))
    @patch("avm.commands.publish.PublishSaga")
    @patch("avm.commands.publish.GitHubClient")
    @patch("avm.commands.publish.GitOps")
    def test_cleanup_exception_blocks_publish(self, mock_git_cls, mock_gh_cls, saga_cls, _cleanup, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_git_cls.return_value.is_repo.return_value = True
        mock_gh_cls.return_value.get_commit_sha.return_value = "abc123def456"
        saga_cls.return_value.ensure_tag.return_value = None
        saga_cls.return_value.ensure_release.return_value = "https://example.invalid/v1"

        assert run_publish(project_dir, json_output=True) is False


def test_cleanup_with_no_refs_or_branch_is_empty():
    lock = TaskLock(remote_lock_ref=None, branch="")
    assert _perform_cleanup(MagicMock(), MagicMock(), lock) == []


def test_cleanup_reports_remote_and_local_branch_failures():
    lock = TaskLock(remote_lock_ref=None, branch="agent/v1")
    github = MagicMock()
    github.delete_branch.return_value = False
    git = MagicMock()
    git.delete_branch.return_value = False

    steps = _perform_cleanup(github, git, lock)

    assert [step["status"] for step in steps] == ["error", "error"]
