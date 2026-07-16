"""AVM PR 命令测试"""

import json
import subprocess
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
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True)
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
            "base_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


def _pr_info(project_dir: Path, *, draft: bool = False, head_sha: str | None = None) -> dict:
    return {
        "number": 1,
        "state": "OPEN",
        "isDraft": draft,
        "baseRefName": "main",
        "headRefOid": head_sha
        or subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
    }


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
        pr_list_result.stdout = json.dumps([_pr_info(project_dir)])
        # CI checks response
        checks_result = MagicMock()
        checks_result.returncode = 0
        checks_result.stdout = json.dumps([])

        def run_gh_side_effect(args):
            if "checks" in args:
                return checks_result
            return pr_list_result

        mock_gh._run_gh.side_effect = run_gh_side_effect
        mock_gh.merge_pull_request.return_value = {"merged": True, "method": "squash", "merge_commit_sha": "merge123"}
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

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_rejects_empty_merge_sha(self, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_gh = MagicMock()
        pr_result = MagicMock(stdout=json.dumps([_pr_info(project_dir)]))
        checks_result = MagicMock(returncode=0, stdout=json.dumps([{"name": "tests", "state": "SUCCESS"}]))
        mock_gh._run_gh.side_effect = lambda args: checks_result if "checks" in args else pr_result
        mock_gh.merge_pull_request.return_value = {"merged": True, "merge_commit_sha": ""}
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as manager_cls:
            manager_cls.return_value.validate_approval.return_value = True
            assert run_merge(project_dir) is False

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_rejects_changed_remote_head(self, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_gh = MagicMock()
        pr_result = MagicMock(stdout=json.dumps([_pr_info(project_dir, head_sha="other")]))
        checks_result = MagicMock(returncode=0, stdout=json.dumps([{"name": "tests", "state": "SUCCESS"}]))
        mock_gh._run_gh.side_effect = lambda args: checks_result if "checks" in args else pr_result
        mock_gh.merge_pull_request.return_value = {"merged": True, "merge_commit_sha": "merge123"}
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as manager_cls:
            manager_cls.return_value.validate_approval.return_value = True
            assert run_merge(project_dir) is False

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_rejects_ci_query_failure(self, mock_gh_cls, project_dir):
        _create_lock(project_dir, "PR_READY")
        mock_gh = MagicMock()
        pr_result = MagicMock(stdout=json.dumps([_pr_info(project_dir)]))

        def run_gh(args):
            if "checks" in args:
                raise RuntimeError("network")
            return pr_result

        mock_gh._run_gh.side_effect = run_gh
        mock_gh.merge_pull_request.return_value = {"merged": True, "merge_commit_sha": "merge123"}
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as manager_cls:
            manager_cls.return_value.validate_approval.return_value = True
            assert run_merge(project_dir) is False


class TestRunCreatePrReady:
    """create-pr from PR_READY state"""

    @patch("avm.commands.pr.GitHubClient")
    def test_create_pr_accepts_pr_ready(self, mock_gh_cls, project_dir):
        """test: PR_READY state accepted by create-pr (status remains PR_READY, no regression)"""
        _create_lock(project_dir, "PR_READY")

        mock_gh = MagicMock()
        mock_gh.create_pull_request.return_value = {
            "html_url": "https://github.com/test/pr/1",
            "number": 1,
        }
        mock_gh_cls.return_value = mock_gh

        result = run_create_pr(project_dir)
        assert result is True

        # Verify no state regression - should still be PR_READY
        from avm.core.state_machine import StateMachine
        from avm.models import TaskStatus

        sm = StateMachine(project_dir)
        sm.load()
        assert sm.current_status == TaskStatus.PR_READY


class TestRunMergeDraftPr:
    """merge from DRAFT_PR state"""

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_handles_draft_pr_with_mark_ready(self, mock_gh_cls, project_dir):
        """test: DRAFT_PR merge attempts mark-ready then merge"""
        _create_lock(project_dir, "DRAFT_PR")

        mock_gh = MagicMock()

        # First call: PR list shows draft=True
        pr_list_draft = MagicMock()
        pr_list_draft.stdout = json.dumps([_pr_info(project_dir, draft=True)])

        # mark-ready call
        mark_ready_result = MagicMock()
        mark_ready_result.returncode = 0
        mark_ready_result.stdout = ""

        # Second call: PR list after mark-ready shows draft=False
        pr_list_ready = MagicMock()
        pr_list_ready.stdout = json.dumps([_pr_info(project_dir)])

        # CI checks
        checks_result = MagicMock()
        checks_result.returncode = 0
        checks_result.stdout = json.dumps([])

        call_count = [0]

        def run_gh_side_effect(args):
            call_count[0] += 1
            if "checks" in args:
                return checks_result
            if "ready" in args:
                return mark_ready_result
            # PR list - return draft first time, ready second time
            if call_count[0] <= 2:
                return pr_list_draft
            return pr_list_ready

        mock_gh._run_gh.side_effect = run_gh_side_effect
        mock_gh.merge_pull_request.return_value = {"merged": True, "method": "squash", "merge_commit_sha": "merge456"}
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as mock_approval_cls:
            mock_approval = MagicMock()
            mock_approval.validate_approval.return_value = True
            mock_approval_cls.return_value = mock_approval

            result = run_merge(project_dir)
            assert result is True

    @patch("avm.commands.pr.GitHubClient")
    def test_merge_draft_pr_still_draft_fails(self, mock_gh_cls, project_dir):
        """test: DRAFT_PR merge fails if PR stays draft after mark-ready"""
        _create_lock(project_dir, "DRAFT_PR")

        mock_gh = MagicMock()

        # PR list always shows draft=True
        pr_list_draft = MagicMock()
        pr_list_draft.stdout = json.dumps([_pr_info(project_dir, draft=True)])

        mark_ready_result = MagicMock()
        mark_ready_result.returncode = 0
        mark_ready_result.stdout = ""

        def run_gh_side_effect(args):
            if "ready" in args:
                return mark_ready_result
            return pr_list_draft

        mock_gh._run_gh.side_effect = run_gh_side_effect
        mock_gh_cls.return_value = mock_gh

        with patch("avm.core.approval.ApprovalManager") as mock_approval_cls:
            mock_approval = MagicMock()
            mock_approval.validate_approval.return_value = True
            mock_approval_cls.return_value = mock_approval

            result = run_merge(project_dir)
            assert result is False
