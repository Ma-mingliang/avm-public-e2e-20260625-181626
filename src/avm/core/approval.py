"""AVM 审批管理"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..exceptions import ApprovalError, ApprovalExpiredError, ApprovalKeyUnavailableError, ScopeExpansionError
from ..models import ApprovalRecord, ApprovalType, TaskLock, TaskStatus
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
        所有持久化形式均为 hex，运行时统一返回原始字节。
        返回 bytes 类型。
        """
        import os

        # 1. 环境变量
        env_key = os.environ.get("AVM_HMAC_KEY")
        if env_key:
            try:
                key = bytes.fromhex(env_key)
            except ValueError as exc:
                raise ApprovalKeyUnavailableError("AVM_HMAC_KEY 必须是 hex 编码") from exc
            if len(key) < 32:
                raise ApprovalKeyUnavailableError("AVM_HMAC_KEY 至少需要 32 字节")
            return key

        # 2. keyring (Windows Credential Manager)
        try:
            import keyring

            stored = keyring.get_password(CREDENTIAL_SERVICE, "hmac-signing-key")
            if stored:
                try:
                    key = bytes.fromhex(stored)
                except ValueError as exc:
                    raise ApprovalKeyUnavailableError("keyring 中的审批密钥格式无效") from exc
                if len(key) < 32:
                    raise ApprovalKeyUnavailableError("keyring 中的审批密钥长度不足")
                return key

            # 生成新密钥并存储
            key = generate_random_key()
            keyring.set_password(CREDENTIAL_SERVICE, "hmac-signing-key", key.hex())
            return key
        except ApprovalKeyUnavailableError:
            raise
        except Exception as exc:
            raise ApprovalKeyUnavailableError("审批签名密钥不可用") from exc

    def create_approval(
        self,
        task_lock: TaskLock,
        approval_type: ApprovalType,
        approver: str,
        scope_files: list[str] | None = None,
        notes: str = "",
        content_hash: str = "",
        approval_source: str = "human",
        policy_version: str = "",
        call_id: str = "",
        approved_head_sha: str = "",
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
            "task_id": task_lock.task_id,
            "version": task_lock.version,
            "agent": task_lock.agent.value if hasattr(task_lock.agent, "value") else str(task_lock.agent),
            "approval_type": approval_type.value if hasattr(approval_type, "value") else str(approval_type),
            "approver": approver,
            "scope_files": scope_files or [],
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "content_hash": content_hash,
            "approval_source": approval_source,
            "policy_version": policy_version,
            "call_id": call_id,
            "approved_head_sha": approved_head_sha,
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
            approval_source=approval_source,
            agent=content["agent"],
            policy_version=policy_version,
            call_id=call_id,
            approved_head_sha=approved_head_sha,
        )

        # 持久化
        self._save_approval(record)
        return record

    def validate_approval(
        self,
        task_lock: TaskLock,
        actual_files: list[str] | None = None,
        actual_content_hash: str = "",
        expected_type: ApprovalType | None = None,
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

        if record.task_id != task_lock.task_id:
            raise ApprovalError(f"审批任务不匹配: {record.task_id} != {task_lock.task_id}")

        # 检查版本匹配
        if record.version != task_lock.version:
            raise ApprovalError(f"审批版本不匹配: {record.version} != {task_lock.version}")

        final_states = {
            TaskStatus.PR_READY,
            TaskStatus.MERGING,
            TaskStatus.TAGGING,
            TaskStatus.RELEASING,
            TaskStatus.PUBLISH_INCOMPLETE,
        }
        required_type = expected_type
        if required_type is None and task_lock.status in final_states:
            required_type = ApprovalType.FINAL_RELEASE
        if required_type is not None and record.approval_type != required_type:
            raise ApprovalError(f"审批类型不匹配: {record.approval_type.value} != {required_type.value}")

        # 检查过期
        if record.is_expired():
            raise ApprovalExpiredError(f"审批已过期: {record.expires_at}")

        # 验证签名
        key = self._get_signing_key()
        content = {
            "task_id": record.task_id,
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
            "approval_source": record.approval_source,
            "policy_version": record.policy_version,
            "call_id": record.call_id,
            "approved_head_sha": record.approved_head_sha,
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
        except Exception as exc:
            raise ApprovalError(f"审批记录损坏: {task_id}") from exc

    def _load_all_approvals(self) -> dict[str, Any]:
        """加载所有审批记录"""
        if not self.approval_path.exists():
            return {}

        try:
            approvals = read_json(self.approval_path)
        except Exception as exc:
            raise ApprovalError("审批记录损坏，拒绝继续") from exc
        if not isinstance(approvals, dict):
            raise ApprovalError("审批记录损坏，根节点必须是对象")
        return approvals

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
