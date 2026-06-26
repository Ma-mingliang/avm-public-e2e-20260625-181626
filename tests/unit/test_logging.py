"""AVM 日志模块测试"""

import logging
from unittest.mock import patch

from avm.core.logging import (
    LEVEL_AUDIT,
    LEVEL_ERROR,
    LEVEL_INFO,
    SENSITIVE_PATTERNS,
    log_audit,
    log_error,
    sanitize_message,
    setup_logger,
)


class TestSanitizeMessage:
    """消息脱敏测试"""

    def test_sanitize_token(self):
        """测试 token 脱敏"""
        msg = "token=ghp_abc123def456"
        result = sanitize_message(msg)
        assert "ghp_abc123def456" not in result
        assert "[REDACTED]" in result

    def test_sanitize_password(self):
        """测试密码脱敏"""
        msg = "password: mysecret123"
        result = sanitize_message(msg)
        assert "mysecret123" not in result

    def test_sanitize_secret_key(self):
        """测试 secret key 脱敏"""
        msg = "secret_key=AKIA1234567890ABCDEF"
        result = sanitize_message(msg)
        assert "AKIA1234567890ABCDEF" not in result

    def test_sanitize_private_key(self):
        """测试私钥脱敏"""
        msg = "-----BEGIN RSA PRIVATE KEY-----\ndata"
        result = sanitize_message(msg)
        assert "-----BEGIN RSA PRIVATE KEY-----" not in result

    def test_sanitize_sk_key(self):
        """测试 sk- key 脱敏"""
        msg = "api_key=sk-abcdefghijklmnopqrstuvwx"
        result = sanitize_message(msg)
        assert "sk-abcdefghijklmnopqrstuvwx" not in result

    def test_no_sensitive_info(self):
        """测试无敏感信息"""
        msg = "正常日志消息"
        result = sanitize_message(msg)
        assert result == msg

    def test_multiple_sensitive_items(self):
        """测试多个敏感信息"""
        msg = "token=ghp_abc password=secret123"
        result = sanitize_message(msg)
        assert "ghp_abc" not in result
        assert "secret123" not in result


class TestSetupLogger:
    """日志记录器测试"""

    def test_setup_logger_returns_logger(self, tmp_path):
        """测试返回 Logger 实例"""
        with patch("avm.core.logging.get_log_dir", return_value=tmp_path):
            logger = setup_logger("test_avm")
            assert isinstance(logger, logging.Logger)
            logger.handlers.clear()

    def test_setup_logger_no_duplicate_handlers(self, tmp_path):
        """测试不重复添加 handler"""
        with patch("avm.core.logging.get_log_dir", return_value=tmp_path):
            logger1 = setup_logger("test_avm_dup")
            handler_count = len(logger1.handlers)
            logger2 = setup_logger("test_avm_dup")
            assert len(logger2.handlers) == handler_count
            logger2.handlers.clear()


class TestLogAudit:
    """审计日志测试"""

    def test_log_audit_creates_log(self, tmp_path):
        """测试审计日志创建"""
        with patch("avm.core.logging.get_log_file", return_value=tmp_path / "audit.log"):
            log_audit("test_action", {"key": "value"}, tmp_path)
            # 不抛异常即通过

    def test_log_audit_sanitizes_details(self, tmp_path):
        """测试审计日志脱敏"""
        with patch("avm.core.logging.get_log_file", return_value=tmp_path / "audit.log"):
            log_audit("test", {"token": "ghp_abc123"}, tmp_path)
            # 不抛异常即通过


class TestLogError:
    """错误日志测试"""

    def test_log_error_basic(self, tmp_path):
        """测试基本错误日志"""
        with patch("avm.core.logging.get_log_dir", return_value=tmp_path):
            log_error("测试错误")
            # 不抛异常即通过

    def test_log_error_with_exception(self, tmp_path):
        """测试带异常的错误日志"""
        with patch("avm.core.logging.get_log_dir", return_value=tmp_path):
            try:
                raise ValueError("测试异常")
            except ValueError as e:
                log_error("操作失败", e)
            # 不抛异常即通过


class TestConstants:
    """常量测试"""

    def test_level_constants(self):
        """测试日志级别常量"""
        assert LEVEL_INFO == "INFO"
        assert LEVEL_AUDIT == "AUDIT"
        assert LEVEL_ERROR == "ERROR"

    def test_sensitive_patterns_not_empty(self):
        """测试敏感信息模式非空"""
        assert len(SENSITIVE_PATTERNS) > 0
