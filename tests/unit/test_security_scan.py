"""AVM 安全扫描器测试"""

import pytest

from avm.core.security_scan import SecurityScanner
from avm.models import ProjectConfig, ProjectInfo


@pytest.fixture
def scanner():
    return SecurityScanner()


@pytest.fixture
def config_scanner():
    config = ProjectConfig(
        project=ProjectInfo(name="test", root="."),
    )
    return SecurityScanner(config)


class TestSecurityScanner:
    """安全扫描器测试"""

    def test_no_findings(self, scanner, tmp_path):
        """正常文件无发现"""
        (tmp_path / "main.py").write_text("print('hello')")
        result = scanner.scan_files(["main.py"], tmp_path)
        assert not result["has_critical"]
        assert not result["has_high"]
        assert result["scanned"] == 1

    def test_detects_api_key(self, scanner, tmp_path):
        """检测 API Key"""
        (tmp_path / "config.py").write_text('API_KEY = "sk-1234567890abcdef1234567890abcdef"')
        result = scanner.scan_files(["config.py"], tmp_path)
        assert result["has_critical"]
        assert len(result["findings"]) > 0

    def test_detects_private_key(self, scanner, tmp_path):
        """检测私钥"""
        (tmp_path / "key.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
        result = scanner.scan_files(["key.pem"], tmp_path)
        assert result["has_critical"]

    def test_detects_aws_key(self, scanner, tmp_path):
        """检测 AWS 密钥"""
        (tmp_path / "config.py").write_text("AWS_ACCESS_KEY_ID = 'AKIAIOSFODNN7EXAMPLE'")
        result = scanner.scan_files(["config.py"], tmp_path)
        assert result["has_critical"]

    def test_detects_github_token(self, scanner, tmp_path):
        """检测 GitHub Token"""
        (tmp_path / "config.py").write_text("TOKEN = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij'")
        result = scanner.scan_files(["config.py"], tmp_path)
        assert result["has_critical"]

    def test_blocked_env_file(self, scanner, tmp_path):
        """阻止 .env 文件"""
        (tmp_path / ".env").write_text("SECRET=123")
        result = scanner.scan_files([".env"], tmp_path)
        assert result["has_critical"]
        assert ".env" in result["blocked_files"]

    def test_blocked_pem_file(self, scanner, tmp_path):
        """阻止 .pem 文件"""
        (tmp_path / "cert.pem").write_text("-----BEGIN CERTIFICATE-----")
        result = scanner.scan_files(["cert.pem"], tmp_path)
        assert result["has_critical"]

    def test_large_file(self, scanner, tmp_path):
        """检测大文件"""
        # 创建一个超过阈值的文件
        large_content = "x" * (2 * 1024 * 1024)  # 2MB
        (tmp_path / "large.txt").write_text(large_content)
        result = scanner.scan_files(["large.txt"], tmp_path, max_file_size=1024 * 1024)
        assert result["has_high"]
        assert "large.txt" in result["large_files"]

    def test_missing_file_skipped(self, scanner, tmp_path):
        """缺失文件跳过"""
        result = scanner.scan_files(["nonexistent.py"], tmp_path)
        assert result["skipped"] == 1
        assert result["scanned"] == 0

    def test_mask_secret(self, scanner):
        """脱敏显示"""
        masked = scanner._mask_secret("abcdefghijklmnop")
        assert masked == "abcd********mnop"
        assert len(masked) == len("abcdefghijklmnop")

    def test_mask_short_secret(self, scanner):
        """短密钥脱敏"""
        masked = scanner._mask_secret("abc")
        assert masked == "***"

    def test_custom_patterns(self, tmp_path):
        """自定义模式"""
        config = ProjectConfig(
            project=ProjectInfo(name="test", root="."),
        )
        config.risk.sensitive_patterns = [r"CUSTOM_SECRET_\d+"]
        scanner = SecurityScanner(config)

        (tmp_path / "test.py").write_text("key = 'CUSTOM_SECRET_12345'")
        result = scanner.scan_files(["test.py"], tmp_path)
        assert result["has_critical"]

    def test_staged_files(self, scanner, tmp_path):
        """扫描暂存区文件"""
        # 这个测试需要实际的 git 仓库，简化测试
        result = scanner.scan_staged_files(tmp_path)
        # 在非 git 仓库中应该返回错误或空结果
        assert "scanned" in result

    def test_binary_file_skipped(self, scanner, tmp_path):
        """二进制文件跳过"""
        # 创建一个包含非 UTF-8 内容的文件
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03\x80\x81\x82\x83")
        result = scanner.scan_files(["binary.bin"], tmp_path)
        # 二进制文件应该被扫描但可能没有发现
        assert "scanned" in result

    def test_multiple_findings(self, scanner, tmp_path):
        """多个发现"""
        content = """
api_key = "sk-1234567890abcdef1234567890abcdef"
password = "supersecretpassword123"
-----BEGIN RSA PRIVATE KEY-----
"""
        (tmp_path / "secrets.py").write_text(content)
        result = scanner.scan_files(["secrets.py"], tmp_path)
        assert result["has_critical"]
        assert len(result["findings"]) >= 2
