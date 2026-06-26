"""AVM 安全扫描器

在提交前扫描文件内容，检测并阻断敏感信息泄露：
- API 密钥、Token
- 私钥
- .env 文件
- 大文件
- 自定义敏感模式
"""

from __future__ import annotations

import re
from pathlib import Path

from ..exceptions import AVMError
from ..models import ProjectConfig

# 内置敏感模式（正则表达式）
BUILTIN_SENSITIVE_PATTERNS = [
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})", "AWS Secret Access Key"),
    # GitHub Token
    (r"gh[pousr]_[A-Za-z0-9_]{36,255}", "GitHub Token"),
    (r"github_pat_[A-Za-z0-9_]{22,255}", "GitHub Fine-grained Token"),
    # Generic API keys
    (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})", "API Key"),
    (r"(?i)(secret[_-]?key|secretkey)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})", "Secret Key"),
    (r"(?i)(access[_-]?token|accesstoken)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})", "Access Token"),
    # Private keys
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),
    # JWT
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT Token"),
    # Database URLs
    (r"(?i)(mysql|postgres|postgresql|mongodb|redis)://[^\s]+", "Database URL"),
    # Generic secrets
    (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]?([^\s'\"]{8,})", "Password"),
]

# 大文件阈值（字节）
DEFAULT_LARGE_FILE_THRESHOLD = 1 * 1024 * 1024  # 1MB

# 禁止提交的文件名模式
BLOCKED_FILE_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
]


class SecurityScanError(AVMError):
    """安全扫描错误"""

    pass


class SecurityScanner:
    """安全扫描器"""

    def __init__(self, config: ProjectConfig | None = None):
        self.config = config
        self._patterns = self._build_patterns()

    def _build_patterns(self) -> list[tuple]:
        """构建敏感模式列表"""
        patterns = list(BUILTIN_SENSITIVE_PATTERNS)

        # 添加配置中的自定义模式
        if self.config and self.config.risk.sensitive_patterns:
            for pattern_str in self.config.risk.sensitive_patterns:
                try:
                    re.compile(pattern_str)
                    patterns.append((pattern_str, f"自定义模式: {pattern_str[:30]}"))
                except re.error:
                    pass  # 跳过无效正则

        return patterns

    def scan_files(
        self,
        files: list[str],
        base_path: Path,
        max_file_size: int = DEFAULT_LARGE_FILE_THRESHOLD,
    ) -> dict:
        """扫描文件列表

        Args:
            files: 文件路径列表（相对于 base_path）
            base_path: 项目根路径
            max_file_size: 大文件阈值（字节）

        Returns:
            扫描结果字典
        """
        findings: list[dict] = []
        blocked_files: list[str] = []
        large_files: list[str] = []
        scanned_count = 0
        skipped_count = 0

        for file_path in files:
            full_path = base_path / file_path

            # 检查是否为禁止文件
            if self._is_blocked_file(file_path):
                blocked_files.append(file_path)
                findings.append(
                    {
                        "file": file_path,
                        "type": "blocked_file",
                        "severity": "CRITICAL",
                        "message": f"禁止提交的文件: {file_path}",
                    }
                )
                continue

            # 检查文件是否存在
            if not full_path.exists():
                skipped_count += 1
                continue

            # 检查文件大小
            try:
                file_size = full_path.stat().st_size
                if file_size > max_file_size:
                    large_files.append(file_path)
                    findings.append(
                        {
                            "file": file_path,
                            "type": "large_file",
                            "severity": "HIGH",
                            "message": (
                                f"文件过大 ({file_size / 1024:.0f}KB > {max_file_size / 1024:.0f}KB): {file_path}"
                            ),
                        }
                    )
                    continue
            except OSError:
                skipped_count += 1
                continue

            # 扫描文件内容
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                file_findings = self._scan_content(content, file_path)
                findings.extend(file_findings)
                scanned_count += 1
            except (OSError, UnicodeDecodeError):
                skipped_count += 1

        return {
            "scanned": scanned_count,
            "skipped": skipped_count,
            "blocked_files": blocked_files,
            "large_files": large_files,
            "findings": findings,
            "has_critical": any(f["severity"] == "CRITICAL" for f in findings),
            "has_high": any(f["severity"] == "HIGH" for f in findings),
        }

    def _is_blocked_file(self, file_path: str) -> bool:
        """检查是否为禁止提交的文件"""
        name = Path(file_path).name.lower()
        for pattern in BLOCKED_FILE_PATTERNS:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
        return False

    def _scan_content(self, content: str, file_path: str) -> list[dict]:
        """扫描文件内容中的敏感信息"""
        findings = []

        for pattern_str, description in self._patterns:
            try:
                matches = re.finditer(pattern_str, content)
                for match in matches:
                    # 获取匹配行号
                    line_num = content[: match.start()].count("\n") + 1
                    matched_text = match.group(0)

                    # 脱敏显示
                    masked = self._mask_secret(matched_text)

                    findings.append(
                        {
                            "file": file_path,
                            "line": line_num,
                            "type": "sensitive_pattern",
                            "severity": "CRITICAL",
                            "pattern": description,
                            "matched": masked,
                            "message": f"{file_path}:{line_num} 检测到 {description}: {masked}",
                        }
                    )
            except re.error:
                continue

        return findings

    def _mask_secret(self, text: str) -> str:
        """脱敏显示密钥"""
        if len(text) <= 8:
            return "*" * len(text)
        visible = min(4, len(text) // 4)
        return text[:visible] + "*" * (len(text) - 2 * visible) + text[-visible:]

    def scan_staged_files(self, base_path: Path) -> dict:
        """扫描 Git 暂存区文件

        Args:
            base_path: 项目根路径

        Returns:
            扫描结果
        """
        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=str(base_path),
            )
            if result.returncode != 0:
                return {
                    "scanned": 0,
                    "skipped": 0,
                    "blocked_files": [],
                    "large_files": [],
                    "findings": [],
                    "has_critical": False,
                    "has_high": False,
                    "error": "无法获取暂存区文件",
                }

            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return self.scan_files(files, base_path)
        except Exception as e:
            return {
                "scanned": 0,
                "skipped": 0,
                "blocked_files": [],
                "large_files": [],
                "findings": [],
                "has_critical": False,
                "has_high": False,
                "error": str(e),
            }
