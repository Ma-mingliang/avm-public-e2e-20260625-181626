"""AVM 异常模型"""

from __future__ import annotations


class AVMError(Exception):
    """AVM 基础异常"""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(AVMError):
    """配置错误"""


class GitError(AVMError):
    """Git操作错误"""


class GitHubError(AVMError):
    """GitHub操作错误"""


class LockError(AVMError):
    """锁操作错误"""

    def __init__(self, message: str, lock_holder: str = ""):
        super().__init__(message, exit_code=2)
        self.lock_holder = lock_holder


class VersionError(AVMError):
    """版本操作错误"""


class ApprovalError(AVMError):
    """审批错误"""


class ApprovalExpiredError(ApprovalError):
    """审批已过期"""

    def __init__(self, message: str, changed_files: list[str] | None = None):
        super().__init__(message)
        self.changed_files = changed_files or []


class SecurityError(AVMError):
    """安全检查错误"""

    def __init__(self, message: str, findings: list[dict] | None = None):
        super().__init__(message, exit_code=3)
        self.findings = findings or []


class BackupError(AVMError):
    """备份操作错误"""


class ValidationError(AVMError):
    """验证错误"""


class NetworkError(AVMError):
    """网络错误"""

    def __init__(self, message: str):
        super().__init__(message, exit_code=4)


class AuthError(AVMError):
    """认证错误"""

    def __init__(self, message: str):
        super().__init__(message, exit_code=5)


class ScopeExpansionError(AVMError):
    """修改范围扩大错误"""

    def __init__(self, message: str, new_files: list[str] | None = None):
        super().__init__(message)
        self.new_files = new_files or []
