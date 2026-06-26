"""AVM 哈希和校验工具"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path


def compute_file_sha256(file_path: Path | str) -> str:
    """计算文件SHA-256哈希"""
    sha256 = hashlib.sha256()
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)

    return sha256.hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """计算字节数据SHA-256哈希"""
    return hashlib.sha256(data).hexdigest()


def compute_string_sha256(text: str, encoding: str = "utf-8") -> str:
    """计算字符串SHA-256哈希"""
    return hashlib.sha256(text.encode(encoding)).hexdigest()


def compute_manifest_hash(manifest_parts: list[str]) -> str:
    """计算清单哈希

    将多个字符串部分拼接后计算SHA-256。
    """
    combined = "|".join(manifest_parts)
    return compute_string_sha256(combined)


def compute_hmac_signature(key: bytes, message: str) -> str:
    """计算HMAC签名"""
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_signature(key: bytes, message: str, signature: str) -> bool:
    """验证HMAC签名"""
    expected = compute_hmac_signature(key, message)
    return hmac.compare_digest(expected, signature)


def generate_random_key(length: int = 32) -> bytes:
    """生成随机密钥"""
    return os.urandom(length)


def compute_approval_hash(
    base_commit: str,
    file_manifest: list[dict[str, str]],
    commit_message_hash: str,
    pr_body_hash: str,
    release_body_hash: str,
    config_hash: str,
) -> str:
    """计算审批哈希

    Args:
        base_commit: 基准提交SHA
        file_manifest: 文件清单 [{"path": "...", "sha256": "..."}]
        commit_message_hash: 提交消息哈希
        pr_body_hash: PR正文哈希
        release_body_hash: Release正文哈希
        config_hash: 配置哈希

    Returns:
        审批哈希值
    """
    parts = [base_commit]

    # 排序文件清单
    sorted_files = sorted(file_manifest, key=lambda x: x["path"])
    for f in sorted_files:
        parts.append(f"{f['path']}:{f['sha256']}")

    parts.extend([commit_message_hash, pr_body_hash, release_body_hash, config_hash])

    return compute_manifest_hash(parts)


def short_hash(full_hash: str, length: int = 8) -> str:
    """获取短哈希"""
    return full_hash[:length]
