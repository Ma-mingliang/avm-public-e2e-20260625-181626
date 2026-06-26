"""AVM hook 命令测试"""

from unittest.mock import MagicMock, patch

import pytest

from avm.commands.hook import (
    run_hook,
    run_hook_commit_msg,
    run_hook_pre_commit,
    run_hook_pre_push,
)


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def msg_file(tmp_path):
    """创建临时提交消息文件"""
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("feat: 测试提交消息", encoding="utf-8")
    return str(msg)


class TestRunHookPreCommit:
    """pre-commit hook 测试"""

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_commit_idle_allows(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试空闲状态无敏感信息时允许提交"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = True
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_status.return_value = {"modified": [], "added": []}
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_commit(project_dir) is True

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_commit_no_sensitive(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试无敏感信息时允许提交"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = False
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_status.return_value = {"modified": [], "added": []}
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_commit(project_dir) is True

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_commit_idle_still_scans(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试 IDLE 状态仍扫描敏感信息"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = True
        mock_sm_cls.return_value = mock_sm

        # 创建包含敏感信息的文件
        secret_file = project_dir / "secret.env"
        secret_file.write_text('API_KEY = "sk-1234567890abcdef1234567890abcdef"', encoding="utf-8")

        mock_git = MagicMock()
        mock_git.get_status.return_value = {"modified": ["secret.env"], "added": []}
        mock_git_cls.return_value = mock_git

        # IDLE 状态下也应阻止敏感信息提交
        assert run_hook_pre_commit(project_dir) is False

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_commit_sensitive_detected(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试检测到敏感信息时阻止提交"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = False
        mock_sm_cls.return_value = mock_sm

        # 创建包含敏感信息的文件
        secret_file = project_dir / "config.py"
        secret_file.write_text('API_KEY = "sk-1234567890abcdef1234567890abcdef"', encoding="utf-8")

        mock_git = MagicMock()
        mock_git.get_status.return_value = {"modified": ["config.py"], "added": []}
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_commit(project_dir) is False

    @patch("avm.commands.hook.StateMachine", side_effect=Exception("sm error"))
    def test_pre_commit_exception_blocks(self, _mock, project_dir):
        """测试异常时阻止提交（fail-closed）"""
        assert run_hook_pre_commit(project_dir) is False


class TestRunHookCommitMsg:
    """commit-msg hook 测试"""

    def test_commit_msg_valid(self, project_dir, msg_file):
        """测试有效提交消息"""
        assert run_hook_commit_msg(project_dir, msg_file) is True

    def test_commit_msg_empty(self, project_dir, tmp_path):
        """测试空提交消息"""
        msg = tmp_path / "EMPTY_MSG"
        msg.write_text("", encoding="utf-8")
        assert run_hook_commit_msg(project_dir, str(msg)) is False

    def test_commit_msg_file_not_exists(self, project_dir, tmp_path):
        """测试消息文件不存在"""
        assert run_hook_commit_msg(project_dir, str(tmp_path / "nonexistent")) is True

    def test_commit_msg_long_first_line(self, project_dir, tmp_path):
        """测试首行过长"""
        msg = tmp_path / "LONG_MSG"
        msg.write_text("a" * 150 + "\n\nbody", encoding="utf-8")
        # 警告但不阻止
        assert run_hook_commit_msg(project_dir, str(msg)) is True


class TestRunHookPrePush:
    """pre-push hook 测试"""

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_push_idle_allows(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试空闲状态允许推送到非默认分支"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = True
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature-branch"
        mock_git.get_default_branch.return_value = "main"
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_push(project_dir) is True

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_push_idle_blocks_default_branch(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试 IDLE 状态阻止推送到默认分支"""
        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = True
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "main"
        mock_git.get_default_branch.return_value = "main"
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_push(project_dir) is False

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_push_pr_ready_allows(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试 PR_READY 状态允许推送"""
        from avm.models import TaskStatus

        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = False
        mock_sm.current_status = TaskStatus.PR_READY
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "agent/v1-claude-code"
        mock_git.get_default_branch.return_value = "main"
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_push(project_dir) is True

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine")
    def test_pre_push_reserved_blocks(self, mock_sm_cls, mock_git_cls, project_dir):
        """测试 RESERVED 状态阻止推送"""
        from avm.models import TaskStatus

        mock_sm = MagicMock()
        mock_sm.is_idle.return_value = False
        mock_sm.current_status = TaskStatus.RESERVED
        mock_sm_cls.return_value = mock_sm

        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "agent/v1-claude-code"
        mock_git.get_default_branch.return_value = "main"
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_push(project_dir) is False

    @patch("avm.commands.hook.GitOps")
    @patch("avm.commands.hook.StateMachine", side_effect=Exception("sm error"))
    def test_pre_push_exception_blocks(self, _mock_sm, mock_git_cls, project_dir):
        """测试异常时阻止推送（fail-closed）"""
        mock_git = MagicMock()
        mock_git.get_current_branch.return_value = "feature-branch"
        mock_git.get_default_branch.return_value = "main"
        mock_git_cls.return_value = mock_git

        assert run_hook_pre_push(project_dir) is False


class TestRunHook:
    """run_hook 分发测试"""

    def test_hook_pre_commit(self, project_dir):
        """测试 pre-commit 分发"""
        with patch("avm.commands.hook.run_hook_pre_commit", return_value=True):
            assert run_hook(project_dir, "pre-commit") is True

    def test_hook_commit_msg(self, project_dir, msg_file):
        """测试 commit-msg 分发"""
        with patch("avm.commands.hook.run_hook_commit_msg", return_value=True):
            assert run_hook(project_dir, "commit-msg", msg_file) is True

    def test_hook_pre_push(self, project_dir):
        """测试 pre-push 分发"""
        with patch("avm.commands.hook.run_hook_pre_push", return_value=True):
            assert run_hook(project_dir, "pre-push") is True

    def test_hook_unknown_type(self, project_dir):
        """测试未知 hook 类型阻止（fail-closed）"""
        assert run_hook(project_dir, "unknown-hook") is False
