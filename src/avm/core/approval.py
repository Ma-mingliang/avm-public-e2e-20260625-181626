"""AVM 审批管理"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..exceptions import ApprovalError, ApprovalExpiredError, ScopeExpansionError
from ..models import ApprovalRecord, ApprovalType, TaskLock
from .hashing import compute_hmac_signature, generate_random_key, verify_hmac_signature
from .io import atomic_write_json, read_json
from .paths import get_version_dir

# 审批有效期（小时）
APPROVAL_VALIDITY_HOURS = 4

# 凭据管理服务名
CREDENTIAL_SERVICE = "AgentVersionManager"


class ApprovalManager:
    """审批管理器

    管理 HMAC 签名的审批记录，确保审批不可伪造且有过期时间。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.approval_path = get_version_dir(project_root) / "approvals.json"

    def _get_signing_key(self) -> bytes:
        """获取签名密钥

        优先从环境变量获取，其次从 keyring 获取，最后生成并存储。
        返回 bytes 类型。
        """
        import os

        # 1. 环境变量
        env_key = os.environ.get("AVM_HMAC_KEY")
        if env_key:
            return env_key.encode("utf-8") if isinstance(env_key, str) else env_key

        # 2. keyring (Windows Credential Manager)
        try:
            import keyring

            stored = keyring.get_password(CREDENTIAL_SERVICE, "hmac-signing-key")
            if stored:
                return stored.encode("utf-8") if isinstance(stored, str) else stored

            # 生成新密钥并存储
            key = generate_random_key()
            keyring.set_password(CREDENTIAL_SERVICE, "hmac-signing-key", key.hex())
            return key
        except Exception:
            # keyring 不可用时，使用基于机器的确定性密钥
            import hashlib
            import platform

            machine_id = f"{platform.node()}-{platform.machine()}"
            return hashlib.sha256(f"avm-fallback-{machine_id}".encode()).digest()

    def create_approval(
        self,
        task_lock: TaskLock,
        approval_type: ApprovalType,
        approver: str,
        scope_files: list[str] | None = None,
        notes: str = "",
        content_hash: str = "",
    ) -> ApprovalRecord:
        """创建审批记录

        Args:
            task_lock: 当前任务锁
            approval_type: 审批类型
            approver: 审批人
            scope_files: 允许修改的文件列表
            notes: 审批备注
            content_hash: 内容哈希（绑定 base_commit、文件 SHA-256、配置等）

        Returns:
            审批记录
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=APPROVAL_VALIDITY_HOURS)

        # 构建审批内容
        content = {
            "version": task_lock.version,
            "agent": task_lock.agent.value if hasattr(task_lock.agent, "value") else str(task_lock.agent),
            "approval_type": approval_type.value if hasattr(approval_type, "value") else str(approval_type),
            "approver": approver,
            "scope_files": scope_files or [],
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "content_hash": content_hash,
        }

        # 计算 HMAC 签名
        key = self._get_signing_key()
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        signature = compute_hmac_signature(key, content_str)

        # 创建记录
        record = ApprovalRecord(
            task_id=task_lock.task_id,
            version=task_lock.version,
            approval_type=approval_type,
            approver=approver,
            signature=signature,
            scope_files=scope_files or [],
            notes=notes,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            content_hash=content_hash,
        )

        # 持久化
        self._save_approval(record)
        return record

    def validate_approval(
        self,
        task_lock: TaskLock,
        actual_files: list[str] | None = None,
        actual_content_hash: str = "",
    ) -> bool:
        """验证审批有效性

        Args:
            task_lock: 当前任务锁
            actual_files: 实际修改的文件列表
            actual_content_hash: 实际内容哈希（用于校验文件内容是否变化）

        Returns:
            是否有效

        Raises:
            ApprovalError: 审批无效
            ApprovalExpiredError: 审批已过期
            ScopeExpansionError: 超出范围
        """
        record = self._load_approval(task_lock.task_id)
        if record is None:
            raise ApprovalError("未找到审批记录")

        # 检查版本匹配
        if record.version != task_lock.version:
            raise ApprovalError(f"审批版本不匹配: {record.version} != {task_lock.version}")

        # 检查过期
        if record.is_expired():
            raise ApprovalExpiredError(f"审批已过期: {record.expires_at}")

        # 验证签名
        key = self._get_signing_key()
        content = {
            "version": record.version,
            "agent": task_lock.agent.value if hasattr(task_lock.agent, "value") else str(task_lock.agent),
            "approval_type": (
                record.approval_type.value if hasattr(record.approval_type, "value") else str(record.approval_type)
            ),
            "approver": record.approver,
            "scope_files": record.scope_files,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "content_hash": record.content_hash,
        }
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)

        if not verify_hmac_signature(key, content_str, record.signature):
            raise ApprovalError("审批签名验证失败")

        # 验证内容哈希（文件内容是否被篡改）
        if not record.content_hash:
            raise ApprovalError("审批记录缺少内容哈希，无法验证文件完整性")
        if actual_content_hash and record.content_hash != actual_content_hash:
            raise ApprovalError(
                f"审批内容哈希不匹配: 文件内容已被修改。"
                f"审批哈希={record.content_hash[:16]}..., "
                f"实际哈希={actual_content_hash[:16]}..."
            )

        # 检查范围
        if actual_files and record.scope_files:
            self._validate_scope(record.scope_files, actual_files)

        return True

    def _validate_scope(
        self,
        allowed_files: list[str],
        actual_files: list[str],
    ) -> None:
        """验证修改范围

        Args:
            allowed_files: 允许修改的文件列表
            actual_files: 实际修改的文件列表

        Raises:
            ScopeExpansionError: 存在范围外文件
        """
        # 规范化路径
        allowed_normalized = {self._normalize_path(f) for f in allowed_files}
        actual_normalized = {self._normalize_path(f) for f in actual_files}

        # 检查每个实际文件是否在允许范围内
        outside_scope = []
        for f in actual_normalized:
            # 精确匹配或前缀匹配（目录级）
            allowed = False
            for a in allowed_normalized:
                if f == a or f.startswith(a + "/") or a.startswith(f + "/"):
                    allowed = True
                    break
            if not allowed:
                outside_scope.append(f)

        if outside_scope:
            raise ScopeExpansionError(
                f"以下文件超出审批范围: {', '.join(outside_scope)}",
                new_files=outside_scope,
            )

    def _normalize_path(self, path: str) -> str:
        """规范化文件路径"""
        return str(Path(path).as_posix()).strip("/")

    def _save_approval(self, record: ApprovalRecord) -> None:
        """保存审批记录"""
        # 加载现有记录
        approvals = self._load_all_approvals()

        # 更新或添加
        approvals[record.task_id] = record.model_dump()

        atomic_write_json(self.approval_path, approvals)

    def _load_approval(self, task_id: str) -> ApprovalRecord | None:
        """加载审批记录"""
        approvals = self._load_all_approvals()

        data = approvals.get(task_id)
        if data is None:
            return None

        try:
            return ApprovalRecord(**data)
        except Exception:
            return None

    def _load_all_approvals(self) -> dict[str, Any]:
        """加载所有审批记录"""
        if not self.approval_path.exists():
            return {}

        try:
            return read_json(self.approval_path)
        except Exception:
            return {}

    def get_approval_info(self, task_id: str) -> dict[str, Any] | None:
        """获取审批信息"""
        record = self._load_approval(task_id)
        if record is None:
            return None

        return {
            "task_id": record.task_id,
            "version": record.version,
            "approval_type": (
                record.approval_type.value if hasattr(record.approval_type, "value") else str(record.approval_type)
            ),
            "approver": record.approver,
            "scope_files": record.scope_files,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "is_expired": record.is_expired(),
            "notes": record.notes,
        }

    def revoke_approval(self, task_id: str) -> bool:
        """撤销审批"""
        approvals = self._load_all_approvals()

        if task_id not in approvals:
            return False

        del approvals[task_id]
        atomic_write_json(self.approval_path, approvals)
        return True
