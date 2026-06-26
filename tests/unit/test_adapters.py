"""AVM Agent 适配器测试"""

from unittest.mock import MagicMock, patch

import pytest

from avm.adapters.base import AgentAdapter
from avm.adapters.claude_code import ClaudeCodeAdapter
from avm.adapters.codex import CodexAdapter
from avm.adapters.factory import detect_agent, get_adapter, get_all_adapters, get_available_adapters
from avm.adapters.hermes import HermesAdapter
from avm.models import AgentType, TaskLock, TaskStatus


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    return tmp_path


class TestClaudeCodeAdapter:
    """Claude Code 适配器测试"""

    def test_agent_type(self, temp_project):
        """测试 Agent 类型"""
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.agent_type == AgentType.CLAUDE_CODE

    def test_name(self, temp_project):
        """测试名称"""
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.name == "Claude Code"

    def test_is_available(self, temp_project):
        """测试可用性检查"""
        adapter = ClaudeCodeAdapter(temp_project)
        # 不检查实际可用性，只测试方法不抛异常
        result = adapter.is_available()
        assert isinstance(result, bool)

    def test_get_version(self, temp_project):
        """测试获取版本"""
        adapter = ClaudeCodeAdapter(temp_project)
        version = adapter.get_version()
        assert isinstance(version, str)

    def test_preflight_check(self, temp_project):
        """测试预检"""
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.preflight_check()
        assert "passed" in result
        assert "checks" in result

    def test_start_task(self, temp_project):
        """测试开始任务"""
        adapter = ClaudeCodeAdapter(temp_project)
        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        assert adapter.start_task(lock)

    def test_validate(self, temp_project):
        """测试验证"""
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.validate()
        assert "passed" in result

    def test_prepare_review(self, temp_project):
        """测试准备审查"""
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.prepare_review()
        assert "passed" in result

    def test_get_status(self, temp_project):
        """测试获取状态"""
        adapter = ClaudeCodeAdapter(temp_project)
        status = adapter.get_status()
        assert "agent" in status
        assert "available" in status

    def test_get_adapter_info(self, temp_project):
        """测试获取适配器信息"""
        adapter = ClaudeCodeAdapter(temp_project)
        info = adapter.get_adapter_info()
        assert info["agent_type"] == "claude-code"
        assert info["name"] == "Claude Code"


class TestHermesAdapter:
    """Hermes 适配器测试"""

    def test_agent_type(self, temp_project):
        """测试 Agent 类型"""
        adapter = HermesAdapter(temp_project)
        assert adapter.agent_type == AgentType.HERMES

    def test_name(self, temp_project):
        """测试名称"""
        adapter = HermesAdapter(temp_project)
        assert adapter.name == "Hermes"

    def test_preflight_check(self, temp_project):
        """测试预检"""
        adapter = HermesAdapter(temp_project)
        result = adapter.preflight_check()
        assert "passed" in result
        assert "checks" in result

    def test_start_task(self, temp_project):
        """测试开始任务"""
        adapter = HermesAdapter(temp_project)
        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.HERMES,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        assert adapter.start_task(lock)

    def test_validate(self, temp_project):
        """测试验证"""
        adapter = HermesAdapter(temp_project)
        result = adapter.validate()
        assert "passed" in result

    def test_prepare_review(self, temp_project):
        """测试准备审查"""
        adapter = HermesAdapter(temp_project)
        result = adapter.prepare_review()
        assert result["passed"]

    def test_get_status(self, temp_project):
        """测试获取状态"""
        adapter = HermesAdapter(temp_project)
        status = adapter.get_status()
        assert "agent" in status
        assert "available" in status


class TestCodexAdapter:
    """Codex 适配器测试"""

    def test_agent_type(self, temp_project):
        """测试 Agent 类型"""
        adapter = CodexAdapter(temp_project)
        assert adapter.agent_type == AgentType.CODEX

    def test_name(self, temp_project):
        """测试名称"""
        adapter = CodexAdapter(temp_project)
        assert adapter.name == "Codex"

    def test_preflight_check(self, temp_project):
        """测试预检"""
        adapter = CodexAdapter(temp_project)
        result = adapter.preflight_check()
        assert "passed" in result
        assert "checks" in result

    def test_start_task(self, temp_project):
        """测试开始任务"""
        adapter = CodexAdapter(temp_project)
        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CODEX,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        assert adapter.start_task(lock)

    def test_validate(self, temp_project):
        """测试验证"""
        adapter = CodexAdapter(temp_project)
        result = adapter.validate()
        assert "passed" in result

    def test_prepare_review(self, temp_project):
        """测试准备审查"""
        adapter = CodexAdapter(temp_project)
        result = adapter.prepare_review()
        assert result["passed"]

    def test_get_status(self, temp_project):
        """测试获取状态"""
        adapter = CodexAdapter(temp_project)
        status = adapter.get_status()
        assert "agent" in status
        assert "available" in status


class TestClaudeCodeAdapterMocked:
    """Claude Code 适配器 Mock 测试"""

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_is_available_success(self, mock_run, temp_project):
        """测试可用性检查成功"""
        mock_run.return_value = MagicMock(returncode=0)
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.is_available()

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_is_available_failure(self, mock_run, temp_project):
        """测试可用性检查失败"""
        mock_run.return_value = MagicMock(returncode=1)
        adapter = ClaudeCodeAdapter(temp_project)
        assert not adapter.is_available()

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_is_available_exception(self, mock_run, temp_project):
        """测试可用性检查异常"""
        mock_run.side_effect = FileNotFoundError
        adapter = ClaudeCodeAdapter(temp_project)
        assert not adapter.is_available()

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_get_version_success(self, mock_run, temp_project):
        """测试获取版本成功"""
        mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0\n")
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.get_version() == "1.0.0"

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_get_version_failure(self, mock_run, temp_project):
        """测试获取版本失败"""
        mock_run.return_value = MagicMock(returncode=1)
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.get_version() == "unknown"

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_get_version_exception(self, mock_run, temp_project):
        """测试获取版本异常"""
        mock_run.side_effect = FileNotFoundError
        adapter = ClaudeCodeAdapter(temp_project)
        assert adapter.get_version() == "unknown"

    @patch("avm.adapters.claude_code.subprocess.run")
    def test_preflight_available_with_version(self, mock_run, temp_project):
        """测试预检可用且有版本"""
        mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0")
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.preflight_check()
        assert result["passed"]
        assert len(result["checks"]) == 2

    def test_checkpoint_success(self, temp_project):
        """测试阶段提交成功"""
        import subprocess

        subprocess.run(["git", "init"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=temp_project, capture_output=True)
        (temp_project / "README.md").write_text("# Test", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_project, capture_output=True)

        # Create a new file so there's something to commit
        (temp_project / "checkpoint.txt").write_text("data", encoding="utf-8")

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.checkpoint("test checkpoint")
        assert result

    def test_checkpoint_failure(self, temp_project):
        """测试阶段提交失败"""
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.checkpoint("test")
        assert not result

    def test_get_status_with_version(self, temp_project):
        """测试获取状态（有版本）"""
        adapter = ClaudeCodeAdapter(temp_project)
        status = adapter.get_status()
        assert "agent" in status
        assert "available" in status


class TestHermesAdapterMocked:
    """Hermes 适配器 Mock 测试"""

    @patch("avm.adapters.hermes.subprocess.run")
    def test_is_available_success(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0)
        adapter = HermesAdapter(temp_project)
        assert adapter.is_available()

    @patch("avm.adapters.hermes.subprocess.run")
    def test_is_available_exception(self, mock_run, temp_project):
        mock_run.side_effect = FileNotFoundError
        adapter = HermesAdapter(temp_project)
        assert not adapter.is_available()

    @patch("avm.adapters.hermes.subprocess.run")
    def test_get_version_success(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0, stdout="2.0.0\n")
        adapter = HermesAdapter(temp_project)
        assert adapter.get_version() == "2.0.0"

    @patch("avm.adapters.hermes.subprocess.run")
    def test_get_version_failure(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=1)
        adapter = HermesAdapter(temp_project)
        assert adapter.get_version() == "unknown"

    @patch("avm.adapters.hermes.subprocess.run")
    def test_preflight_available_with_version(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0, stdout="2.0.0")
        adapter = HermesAdapter(temp_project)
        result = adapter.preflight_check()
        assert result["passed"]
        assert len(result["checks"]) == 2

    def test_checkpoint_success(self, temp_project):
        import subprocess

        subprocess.run(["git", "init"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=temp_project, capture_output=True)
        (temp_project / "README.md").write_text("# Test", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_project, capture_output=True)
        (temp_project / "checkpoint.txt").write_text("data", encoding="utf-8")

        adapter = HermesAdapter(temp_project)
        result = adapter.checkpoint("test checkpoint")
        assert result

    def test_checkpoint_failure(self, temp_project):
        adapter = HermesAdapter(temp_project)
        result = adapter.checkpoint("test")
        assert not result


class TestCodexAdapterMocked:
    """Codex 适配器 Mock 测试"""

    @patch("avm.adapters.codex.subprocess.run")
    def test_is_available_success(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0)
        adapter = CodexAdapter(temp_project)
        assert adapter.is_available()

    @patch("avm.adapters.codex.subprocess.run")
    def test_is_available_exception(self, mock_run, temp_project):
        mock_run.side_effect = FileNotFoundError
        adapter = CodexAdapter(temp_project)
        assert not adapter.is_available()

    @patch("avm.adapters.codex.subprocess.run")
    def test_get_version_success(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0, stdout="3.0.0\n")
        adapter = CodexAdapter(temp_project)
        assert adapter.get_version() == "3.0.0"

    @patch("avm.adapters.codex.subprocess.run")
    def test_get_version_failure(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=1)
        adapter = CodexAdapter(temp_project)
        assert adapter.get_version() == "unknown"

    @patch("avm.adapters.codex.subprocess.run")
    def test_preflight_available_with_version(self, mock_run, temp_project):
        mock_run.return_value = MagicMock(returncode=0, stdout="3.0.0")
        adapter = CodexAdapter(temp_project)
        result = adapter.preflight_check()
        assert result["passed"]
        assert len(result["checks"]) == 2

    def test_checkpoint_success(self, temp_project):
        import subprocess

        subprocess.run(["git", "init"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=temp_project, capture_output=True)
        (temp_project / "README.md").write_text("# Test", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=temp_project, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_project, capture_output=True)
        (temp_project / "checkpoint.txt").write_text("data", encoding="utf-8")

        adapter = CodexAdapter(temp_project)
        result = adapter.checkpoint("test checkpoint")
        assert result

    def test_checkpoint_failure(self, temp_project):
        adapter = CodexAdapter(temp_project)
        result = adapter.checkpoint("test")
        assert not result


class TestRunValidationCommands:
    """run_validation_commands 测试"""

    def test_no_config(self, temp_project):
        """测试无配置时跳过验证"""
        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert result["passed"]
        assert len(result["checks"]) == 1

    def test_with_config_no_commands(self, temp_project):
        """测试配置无命令"""
        version_dir = temp_project / "版本管理"
        version_dir.mkdir(parents=True)
        config_path = version_dir / "配置.yaml"
        config_path.write_text("project_name: test\nvalidation:\n  commands: []\n", encoding="utf-8")

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert result["passed"]

    def test_command_success(self, temp_project):
        """测试命令成功"""
        import sys

        version_dir = temp_project / "版本管理"
        version_dir.mkdir(parents=True)
        config_path = version_dir / "配置.yaml"
        exe = sys.executable
        config_path.write_text(
            f"project_name: test\nvalidation:\n  commands:\n"
            f"    - name: echo_test\n      command: [{exe}, -c, 'pass']\n",
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert result["passed"]
        assert any(c["name"] == "echo_test" and c["passed"] for c in result["checks"])

    def test_command_failure(self, temp_project):
        """测试命令失败"""
        import sys

        version_dir = temp_project / "版本管理"
        version_dir.mkdir(parents=True)
        config_path = version_dir / "配置.yaml"
        exe = sys.executable
        config_path.write_text(
            f"project_name: test\nvalidation:\n  commands:\n"
            f"    - name: fail_test\n      command: [{exe}, -c, 'import sys; sys.exit(1)']\n",
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert not result["passed"]
        assert any(c["name"] == "fail_test" and not c["passed"] for c in result["checks"])

    def test_command_not_found(self, temp_project):
        """测试命令未找到"""
        version_dir = temp_project / "版本管理"
        version_dir.mkdir(parents=True)
        config_path = version_dir / "配置.yaml"
        config_path.write_text(
            "project_name: test\nvalidation:\n  commands:\n    - name: missing\n      command: [nonexistent_cmd_xyz]\n",
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert not result["passed"]
        assert any("未找到" in c["message"] for c in result["checks"])

    def test_empty_command_args(self, temp_project):
        """测试空命令参数"""
        version_dir = temp_project / "版本管理"
        version_dir.mkdir(parents=True)
        config_path = version_dir / "配置.yaml"
        config_path.write_text(
            "project_name: test\nvalidation:\n  commands:\n    - name: empty\n      command: []\n",
            encoding="utf-8",
        )

        adapter = ClaudeCodeAdapter(temp_project)
        result = adapter.run_validation_commands()
        assert result["passed"]


class TestAdapterFactory:
    """适配器工厂测试"""

    def test_get_adapter_claude_code(self, temp_project):
        """测试获取 Claude Code 适配器"""
        adapter = get_adapter(AgentType.CLAUDE_CODE, temp_project)
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_get_adapter_hermes(self, temp_project):
        """测试获取 Hermes 适配器"""
        adapter = get_adapter(AgentType.HERMES, temp_project)
        assert isinstance(adapter, HermesAdapter)

    def test_get_adapter_codex(self, temp_project):
        """测试获取 Codex 适配器"""
        adapter = get_adapter(AgentType.CODEX, temp_project)
        assert isinstance(adapter, CodexAdapter)

    def test_get_all_adapters(self, temp_project):
        """测试获取所有适配器"""
        adapters = get_all_adapters(temp_project)
        assert len(adapters) == 3

    def test_get_available_adapters(self, temp_project):
        """测试获取可用适配器"""
        adapters = get_available_adapters(temp_project)
        # 可能没有可用的适配器
        assert isinstance(adapters, list)

    def test_detect_agent(self, temp_project):
        """测试自动检测 Agent"""
        agent = detect_agent(temp_project)
        # 可能没有可用的 Agent
        assert agent is None or isinstance(agent, AgentAdapter)
