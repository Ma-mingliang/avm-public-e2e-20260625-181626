"""AVM 日志和审计"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import get_global_dir

# 敏感信息模式
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(token|password|secret|key|credential|auth)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(ghp_|gho_|ghu_|ghs_|ghr_)\w+"),
    re.compile(r"(?i)(sk-[a-zA-Z0-9]{20,})"),
    re.compile(r"(?i)(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)"),
    re.compile(r"(?i)(AKIA[0-9A-Z]{16})"),
]

# 日志级别
LEVEL_INFO = "INFO"
LEVEL_AUDIT = "AUDIT"
LEVEL_ERROR = "ERROR"


def get_log_dir() -> Path:
    """获取日志目录"""
    log_dir = get_global_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file(level: str = LEVEL_INFO) -> Path:
    """获取日志文件路径"""
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    return get_log_dir() / f"avm_{level.lower()}_{date_str}.log"


def sanitize_message(message: str) -> str:
    """脱敏日志消息"""
    result = message
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def setup_logger(name: str = "avm", level: int = logging.INFO) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 文件处理器
    log_file = get_log_file(LEVEL_INFO)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)

    # 格式
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


def log_audit(action: str, details: dict[str, Any], project_root: Path | None = None) -> None:
    """记录审计日志"""
    logger = logging.getLogger("avm.audit")
    if not logger.handlers:
        log_file = get_log_file(LEVEL_AUDIT)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [AUDIT] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    sanitized_details = {k: sanitize_message(str(v)) for k, v in details.items()}
    project_str = f" project={project_root}" if project_root else ""
    logger.info(f"action={action}{project_str} {sanitized_details}")


def log_error(message: str, exception: Exception | None = None) -> None:
    """记录错误日志"""
    logger = setup_logger("avm.error", logging.ERROR)
    sanitized = sanitize_message(message)
    if exception:
        logger.error(f"{sanitized}: {exception}")
    else:
        logger.error(sanitized)
