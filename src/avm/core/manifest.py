"""AVM Release Manifest 生成与验证模块"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from ..models import TaskLock


def generate_release_manifest(
    task_lock: TaskLock,
    merge_sha: str,
    release_url: str = "",
) -> dict[str, Any]:
    """生成 release manifest

    Args:
        task_lock: 任务锁
        merge_sha: merge commit SHA
        release_url: GitHub Release URL

    Returns:
        manifest 字典（含 manifest_hash）
    """
    manifest: dict[str, Any] = {
        "task_id": task_lock.task_id,
        "version": task_lock.version,
        "approval_id": task_lock.approval_id or "",
        "merge_sha": merge_sha,
        "manifest_hash": "",  # 占位，计算后填入
        "content_hash": task_lock.base_commit,
        "agent": task_lock.agent.value if hasattr(task_lock.agent, "value") else str(task_lock.agent),
        "branch": task_lock.branch,
        "base_commit": task_lock.base_commit,
        "pr_number": task_lock.pr_number,
        "published_at": datetime.now(UTC).isoformat(),
    }

    # 计算 manifest_hash（排除 manifest_hash 字段本身）
    manifest_hash = _compute_manifest_hash(manifest)
    manifest["manifest_hash"] = manifest_hash

    return manifest


def format_release_body(manifest: dict[str, Any]) -> str:
    """将 manifest 格式化为 release body

    Args:
        manifest: manifest 字典

    Returns:
        Markdown 格式的 release body
    """
    lines = [
        "## Release Manifest",
        "",
        f"- **Task ID**: `{manifest['task_id']}`",
        f"- **Version**: `{manifest['version']}`",
        f"- **Agent**: {manifest['agent']}",
        f"- **Branch**: `{manifest['branch']}`",
        f"- **Merge SHA**: `{manifest['merge_sha']}`",
        f"- **PR Number**: {manifest['pr_number'] or 'N/A'}",
        f"- **Published At**: {manifest['published_at']}",
        "",
        "### Manifest JSON",
        "",
        "```json",
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines)


def verify_manifest_hash(manifest: dict[str, Any]) -> bool:
    """验证 manifest 哈希是否正确

    Args:
        manifest: 含 manifest_hash 的 manifest 字典

    Returns:
        哈希是否有效
    """
    stored_hash = manifest.get("manifest_hash", "")
    if not stored_hash:
        return False

    computed_hash = _compute_manifest_hash(manifest)
    return computed_hash == stored_hash


def _compute_manifest_hash(manifest: dict[str, Any]) -> str:
    """计算 manifest 内容哈希（排除 manifest_hash 字段本身）

    使用 SHA-256，对排除 manifest_hash 后的 dict 排序 keys 序列化。

    Args:
        manifest: manifest 字典

    Returns:
        SHA-256 hex digest
    """
    # 排除 manifest_hash 字段后序列化
    filtered = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    canonical = json.dumps(filtered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
