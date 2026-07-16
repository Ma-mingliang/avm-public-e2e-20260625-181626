"""AVM 审批管理测试"""

from datetime import UTC, datetime, timedelta

import keyring
import pytest

from avm.core.approval import ApprovalManager
from avm.exceptions import ApprovalError, ApprovalExpiredError, ScopeExpansionError
from avm.models import AgentType, ApprovalRecord, ApprovalType, TaskLock, TaskStatus


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def approval_test_key(monkeypatch):
    """审批测试必须显式提供密钥，不依赖主机 keyring。"""
    monkeypatch.setenv("AVM_HMAC_KEY", "11" * 32)


@pytest.fixture
def sample_task_lock():
    """创建示例任务锁"""
    return TaskLock(
        task_id="test-task-001",
        status=TaskStatus.RESERVED,
        version="v1",
        agent=AgentType.CLAUDE_CODE,
        branch="agent/v1-test",
        base_commit="abc123",
    )


class TestApprovalManager:
    """审批管理器测试"""

    def test_create_approval(self, temp_project, sample_task_lock):
        """测试创建审批"""
        manager = ApprovalManager(temp_project)

        record = manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            scope_files=["src/main.py", "tests/test_main.py"],
            notes="测试审批",
            content_hash="test-content-hash-abc123",
        )

        assert record.task_id == sample_task_lock.task_id
        assert record.version == "v1"
        assert record.approval_type == ApprovalType.START
        assert record.approver == "测试用户"
        assert len(record.signature) > 0
        assert len(record.scope_files) == 2

    def test_validate_approval_valid(self, temp_project, sample_task_lock):
        """测试验证有效审批"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="test-content-hash-abc123",
        )

        assert manager.validate_approval(sample_task_lock)

    def test_validate_approval_not_found(self, temp_project, sample_task_lock):
        """测试验证不存在的审批"""
        manager = ApprovalManager(temp_project)

        with pytest.raises(ApprovalError) as exc_info:
            manager.validate_approval(sample_task_lock)
        assert "未找到审批记录" in str(exc_info.value)

    def test_validate_approval_expired(self, temp_project, sample_task_lock):
        """测试验证过期审批"""
        manager = ApprovalManager(temp_project)

        # 创建已过期的审批
        now = datetime.now(UTC)
        record = ApprovalRecord(
            task_id=sample_task_lock.task_id,
            version=sample_task_lock.version,
            approval_type=ApprovalType.START,
            approver="测试用户",
            created_at=(now - timedelta(hours=10)).isoformat(),
            expires_at=(now - timedelta(hours=1)).isoformat(),
        )

        # 手动保存
        from avm.core.io import atomic_write_json

        approvals = {record.task_id: record.model_dump()}
        atomic_write_json(manager.approval_path, approvals)

        with pytest.raises(ApprovalExpiredError):
            manager.validate_approval(sample_task_lock)

    def test_validate_scope_within(self, temp_project, sample_task_lock):
        """测试范围验证 - 文件在范围内"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            scope_files=["src/", "tests/"],
            content_hash="test-content-hash-abc123",
        )

        # 在范围内的文件
        assert manager.validate_approval(
            sample_task_lock,
            actual_files=["src/main.py", "tests/test_main.py"],
        )

    def test_validate_scope_outside(self, temp_project, sample_task_lock):
        """测试范围验证 - 文件超出范围"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            scope_files=["src/main.py"],
            content_hash="test-content-hash-abc123",
        )

        with pytest.raises(ScopeExpansionError) as exc_info:
            manager.validate_approval(
                sample_task_lock,
                actual_files=["src/main.py", "config/secret.yaml"],
            )
        assert "config/secret.yaml" in str(exc_info.value)

    def test_get_approval_info(self, temp_project, sample_task_lock):
        """测试获取审批信息"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.FINAL_RELEASE,
            approver="发布管理员",
            notes="最终发布审批",
            content_hash="test-content-hash-abc123",
        )

        info = manager.get_approval_info(sample_task_lock.task_id)
        assert info is not None
        assert info["version"] == "v1"
        assert info["approver"] == "发布管理员"
        assert info["is_expired"] is False

    def test_revoke_approval(self, temp_project, sample_task_lock):
        """测试撤销审批"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="test-content-hash-abc123",
        )

        assert manager.revoke_approval(sample_task_lock.task_id)
        assert manager.get_approval_info(sample_task_lock.task_id) is None

    def test_revoke_nonexistent_approval(self, temp_project):
        """测试撤销不存在的审批"""
        manager = ApprovalManager(temp_project)
        assert not manager.revoke_approval("nonexistent-task")

    def test_approval_signature_integrity(self, temp_project, sample_task_lock):
        """测试审批签名完整性"""
        manager = ApprovalManager(temp_project)

        record = manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="test-content-hash-abc123",
        )

        # 篡改签名后验证应失败
        from avm.core.io import atomic_write_json

        approvals = manager._load_all_approvals()
        approvals[record.task_id]["signature"] = "tampered-signature"
        atomic_write_json(manager.approval_path, approvals)

        with pytest.raises(ApprovalError) as exc_info:
            manager.validate_approval(sample_task_lock)
        assert "签名验证失败" in str(exc_info.value)

    def test_multiple_approvals(self, temp_project):
        """测试多个审批记录"""
        manager = ApprovalManager(temp_project)

        lock1 = TaskLock(
            task_id="task-1",
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        lock2 = TaskLock(
            task_id="task-2",
            status=TaskStatus.RESERVED,
            version="v2",
            agent=AgentType.HERMES,
            branch="agent/v2-test",
            base_commit="def456",
        )

        manager.create_approval(
            task_lock=lock1,
            approval_type=ApprovalType.START,
            approver="用户A",
            content_hash="test-hash-1",
        )
        manager.create_approval(
            task_lock=lock2,
            approval_type=ApprovalType.FINAL_RELEASE,
            approver="用户B",
            content_hash="test-hash-2",
        )

        info1 = manager.get_approval_info("task-1")
        info2 = manager.get_approval_info("task-2")

        assert info1["approver"] == "用户A"
        assert info2["approver"] == "用户B"

    def test_version_mismatch(self, temp_project, sample_task_lock):
        """测试版本不匹配"""
        manager = ApprovalManager(temp_project)

        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="test-content-hash-abc123",
        )

        # 修改任务锁版本
        sample_task_lock.version = "v99"

        with pytest.raises(ApprovalError) as exc_info:
            manager.validate_approval(sample_task_lock)
        assert "版本不匹配" in str(exc_info.value)

    def test_start_approval_cannot_authorize_final_release(self, temp_project, sample_task_lock):
        manager = ApprovalManager(temp_project)
        manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="subject-hash",
        )
        sample_task_lock.status = TaskStatus.PR_READY

        with pytest.raises(ApprovalError, match="审批类型"):
            manager.validate_approval(sample_task_lock, actual_content_hash="subject-hash")

    def test_signed_approval_cannot_be_replayed_to_another_task(self, temp_project, sample_task_lock):
        manager = ApprovalManager(temp_project)
        record = manager.create_approval(
            task_lock=sample_task_lock,
            approval_type=ApprovalType.START,
            approver="测试用户",
            content_hash="subject-hash",
        )
        other = sample_task_lock.model_copy(update={"task_id": "other-task"})
        approvals = manager._load_all_approvals()
        approvals[other.task_id] = approvals[record.task_id]
        from avm.core.io import atomic_write_json

        atomic_write_json(manager.approval_path, approvals)

        with pytest.raises(ApprovalError, match="任务不匹配"):
            manager.validate_approval(other, actual_content_hash="subject-hash")

    def test_corrupted_approval_store_is_not_silently_overwritten(self, temp_project, sample_task_lock):
        manager = ApprovalManager(temp_project)
        manager.approval_path.parent.mkdir(parents=True, exist_ok=True)
        manager.approval_path.write_text("{broken", encoding="utf-8")

        with pytest.raises(ApprovalError, match="审批记录损坏"):
            manager.create_approval(
                task_lock=sample_task_lock,
                approval_type=ApprovalType.START,
                approver="测试用户",
                content_hash="subject-hash",
            )

        assert manager.approval_path.read_text(encoding="utf-8") == "{broken"


def test_generated_key_round_trips_through_keyring(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.delenv("AVM_HMAC_KEY", raising=False)
    monkeypatch.setattr(keyring, "get_password", lambda service, user: saved.get((service, user)))
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, user, value: saved.__setitem__((service, user), value),
    )
    manager = ApprovalManager(tmp_path)

    assert manager._get_signing_key() == manager._get_signing_key()


def test_keyring_failure_without_environment_key_is_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("AVM_HMAC_KEY", raising=False)

    def fail(*_args):
        raise RuntimeError("offline")

    monkeypatch.setattr(keyring, "get_password", fail)

    with pytest.raises(ApprovalError, match="密钥不可用"):
        ApprovalManager(tmp_path)._get_signing_key()
