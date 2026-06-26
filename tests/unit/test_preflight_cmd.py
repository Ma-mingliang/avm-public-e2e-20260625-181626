"""AVM preflight 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.preflight import run_preflight


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    return tmp_path


class TestRunPreflight:
    """preflight 命令测试"""

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_success(self, mock_detect, project_dir):
        """测试预检成功"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        result = run_preflight(project_dir, task="test task")
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_failure(self, mock_detect, project_dir):
        """测试预检失败"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {
            "passed": False,
            "checks": [{"name": "git", "passed": False}],
        }
        mock_detect.return_value = mock_adapter

        result = run_preflight(project_dir, task="test task")
        assert result is False

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_no_agent(self, mock_detect, project_dir):
        """测试无可用 Agent"""
        mock_detect.return_value = None

        result = run_preflight(project_dir)
        assert result is False

    @patch("avm.commands.preflight.get_adapter")
    def test_preflight_with_agent(self, mock_get_adapter, project_dir):
        """测试指定 Agent"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_get_adapter.return_value = mock_adapter

        result = run_preflight(project_dir, agent="claude-code")
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_json(self, mock_detect, project_dir, capsys):
        """测试 JSON 输出"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        result = run_preflight(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True

    @patch("avm.commands.preflight.get_adapter")
    def test_preflight_invalid_agent(self, mock_get_adapter, project_dir):
        """测试无效 Agent 类型"""
        mock_get_adapter.side_effect = ValueError("invalid")

        result = run_preflight(project_dir, agent="invalid-agent")
        assert result is False

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_with_files_classify(self, mock_classifier_cls, mock_detect, project_dir):
        """测试带文件的任务分类"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.MANDATORY_PROJECT_VERSION
        mock_classifier_cls.return_value = mock_classifier

        result = run_preflight(project_dir, task="test", changed_files=["README.md"])
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_blocked_unclear(self, mock_classifier_cls, mock_detect, project_dir):
        """测试任务被阻断"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.BLOCKED_UNCLEAR
        mock_classifier_cls.return_value = mock_classifier

        result = run_preflight(project_dir, task="test", changed_files=["unknown.xyz"])
        assert result is False

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.SecurityScanner")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_security_critical(self, mock_classifier_cls, mock_scanner_cls, mock_detect, project_dir):
        """测试安全扫描发现严重问题"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.MANDATORY_PROJECT_VERSION
        mock_classifier_cls.return_value = mock_classifier

        mock_scanner = MagicMock()
        mock_scanner.scan_files.return_value = {
            "has_critical": True,
            "has_high": False,
            "scanned": 1,
            "findings": [{"severity": "CRITICAL", "message": "API key leaked"}],
        }
        mock_scanner_cls.return_value = mock_scanner

        result = run_preflight(project_dir, task="test", changed_files=["config.py"])
        assert result is False

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.SecurityScanner")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_security_high(self, mock_classifier_cls, mock_scanner_cls, mock_detect, project_dir):
        """测试安全扫描发现高风险"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.MANDATORY_PROJECT_VERSION
        mock_classifier_cls.return_value = mock_classifier

        mock_scanner = MagicMock()
        mock_scanner.scan_files.return_value = {
            "has_critical": False,
            "has_high": True,
            "scanned": 1,
            "findings": [{"severity": "HIGH", "message": "hardcoded secret"}],
        }
        mock_scanner_cls.return_value = mock_scanner

        result = run_preflight(project_dir, task="test", changed_files=["config.py"])
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.SecurityScanner")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_security_ok(self, mock_classifier_cls, mock_scanner_cls, mock_detect, project_dir):
        """测试安全扫描通过"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.MANDATORY_PROJECT_VERSION
        mock_classifier_cls.return_value = mock_classifier

        mock_scanner = MagicMock()
        mock_scanner.scan_files.return_value = {
            "has_critical": False,
            "has_high": False,
            "scanned": 3,
            "findings": [],
        }
        mock_scanner_cls.return_value = mock_scanner

        result = run_preflight(project_dir, task="test", changed_files=["a.py", "b.py"])
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    @patch("avm.commands.preflight.SecurityScanner")
    @patch("avm.commands.preflight.TaskClassifier")
    def test_preflight_security_error(self, mock_classifier_cls, mock_scanner_cls, mock_detect, project_dir):
        """测试安全扫描异常"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        from avm.models import TaskType

        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = TaskType.MANDATORY_PROJECT_VERSION
        mock_classifier_cls.return_value = mock_classifier

        mock_scanner = MagicMock()
        mock_scanner.scan_files.return_value = {"error": "scan failed"}
        mock_scanner_cls.return_value = mock_scanner

        result = run_preflight(project_dir, task="test", changed_files=["a.py"])
        assert result is True

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_exception(self, mock_detect, project_dir):
        """测试预检异常"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.side_effect = RuntimeError("check failed")
        mock_detect.return_value = mock_adapter

        result = run_preflight(project_dir, task="test")
        assert result is False

    @patch("avm.commands.preflight.detect_agent")
    def test_preflight_with_task_type_output(self, mock_detect, project_dir):
        """测试输出包含任务类型"""
        mock_adapter = MagicMock()
        mock_adapter.agent_type.value = "claude-code"
        mock_adapter.name = "Claude Code"
        mock_adapter.preflight_check.return_value = {"passed": True, "checks": []}
        mock_detect.return_value = mock_adapter

        result = run_preflight(project_dir, task="test task")
        assert result is True
