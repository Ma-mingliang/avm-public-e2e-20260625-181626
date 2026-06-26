"""AVM approve 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.approve import run_approve
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


class TestRunApprove:
    """approve 命令测试"""

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_success(self, mock_git_cls, project_dir):
        """测试开始审批成功"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user")
        assert result is True

    def test_approve_final_success(self, project_dir):
        """测试最终审批成功"""
        _create_lock(project_dir, "WAIT_FINAL_APPROVAL")

        result = run_approve(project_dir, approver="test-user")
        assert result is True

    def test_approve_wrong_state(self, project_dir):
        """测试错误状态"""
        _create_lock(project_dir, "RESERVED")

        result = run_approve(project_dir)
        assert result is False

    @patch("avm.commands.approve.GitOps")
    def test_approve_json_output(self, mock_git_cls, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["approval_id"] is not None

    def test_approve_no_lock(self, project_dir):
        """测试没有任务锁时审批失败"""
        # 不创建锁文件
        result = run_approve(project_dir)
        assert result is False

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_with_notes(self, mock_git_cls, project_dir):
        """测试带备注的开始审批"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user", notes="approved")
        assert result is True

    @patch("avm.commands.approve.GitOps")
    def test_approve_final_with_json_output(self, mock_git_cls, project_dir, capsys):
        """测试最终审批 JSON 输出"""
        _create_lock(project_dir, "WAIT_FINAL_APPROVAL")

        result = run_approve(project_dir, approver="test-user", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["status"] == "PR_READY"

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_transition_to_reserved(self, mock_git_cls, project_dir):
        """测试开始审批后状态转换为 BRANCH_READY"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user")
        assert result is True

        from avm.core.state_machine import StateMachine
        from avm.models import TaskStatus
        sm = StateMachine(project_dir)
        sm.load()
        assert sm.current_status == TaskStatus.BRANCH_READY

    @patch("avm.commands.approve.GitOps")
    def test_approve_final_transition_to_pr_ready(self, mock_git_cls, project_dir):
        """测试最终审批后状态转换为 PR_READY"""
        _create_lock(project_dir, "WAIT_FINAL_APPROVAL")

        result = run_approve(project_dir, approver="test-user")
        assert result is True

        from avm.core.state_machine import StateMachine
        from avm.models import TaskStatus
        sm = StateMachine(project_dir)
        sm.load()
        assert sm.current_status == TaskStatus.PR_READY

    def test_approve_wrong_state_not_approval(self, project_dir):
        """测试非审批状态"""
        _create_lock(project_dir, "MODIFYING")

        result = run_approve(project_dir)
        assert result is False

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_with_json_output(self, mock_git_cls, project_dir, capsys):
        """测试开始审批 JSON 输出"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["approval_id"] is not None

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_with_invalid_version(self, mock_git_cls, project_dir):
        """测试无效版本号审批失败"""
        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "WAIT_START_APPROVAL",
                "version": "invalid",
                "agent": "claude-code",
                "branch": "agent/v1",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
            },
        )

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = True
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user")
        assert result is False

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_branch_creation_fails(self, mock_git_cls, project_dir):
        """测试分支创建失败回滚"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = False
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user")
        assert result is False

    @patch("avm.commands.approve.GitOps")
    def test_approve_start_checkout_fails(self, mock_git_cls, project_dir):
        """测试分支切换失败回滚"""
        _create_lock(project_dir, "WAIT_START_APPROVAL")

        mock_git = MagicMock()
        mock_git.create_branch.return_value = True
        mock_git.checkout.return_value = False
        mock_git_cls.return_value = mock_git

        result = run_approve(project_dir, approver="test-user")
        assert result is False
