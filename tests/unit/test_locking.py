"""AVM 任务锁测试"""

import pytest

from avm.core.locking import TaskLocker
from avm.exceptions import LockError
from avm.models import AgentType, TaskLock, TaskStatus


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestTaskLocker:
    """任务锁测试"""

    def test_initial_state(self, temp_project):
        """测试初始状态"""
        locker = TaskLocker(temp_project)
        assert not locker.is_locked()
        assert locker.get_lock() is None

    def test_acquire_lock(self, temp_project):
        """测试获取锁"""
        locker = TaskLocker(temp_project)

        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )

        assert locker.acquire_lock(lock)
        assert locker.is_locked()

    def test_acquire_lock_already_locked(self, temp_project):
        """测试锁已被占用时获取锁"""
        locker = TaskLocker(temp_project)

        lock1 = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test1",
            base_commit="abc123",
        )
        locker.acquire_lock(lock1)

        lock2 = TaskLock(
            status=TaskStatus.RESERVED,
            version="v2",
            agent=AgentType.HERMES,
            branch="agent/v2-test2",
            base_commit="def456",
        )

        with pytest.raises(LockError) as exc_info:
            locker.acquire_lock(lock2)
        assert "任务锁已被占用" in str(exc_info.value)

    def test_release_lock(self, temp_project):
        """测试释放锁"""
        locker = TaskLocker(temp_project)

        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )

        locker.acquire_lock(lock)
        assert locker.is_locked()

        locker.release_lock()
        assert not locker.is_locked()

    def test_update_lock(self, temp_project):
        """测试更新锁"""
        locker = TaskLocker(temp_project)

        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        locker.acquire_lock(lock)

        locker.update_lock(status=TaskStatus.MODIFYING)
        updated = locker.get_lock()
        assert updated.status == TaskStatus.MODIFYING

    def test_get_lock_info(self, temp_project):
        """测试获取锁信息"""
        locker = TaskLocker(temp_project)

        # 无锁时
        info = locker.get_lock_info()
        assert not info["locked"]

        # 有锁时
        lock = TaskLock(
            status=TaskStatus.RESERVED,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
        )
        locker.acquire_lock(lock)

        info = locker.get_lock_info()
        assert info["locked"]
        assert info["version"] == "v1"
        assert info["agent"] == "claude-code"

    def test_stale_lock_detection(self, temp_project):
        """测试残留锁检测"""
        locker = TaskLocker(temp_project)

        # 创建一个超时的锁
        lock = TaskLock(
            status=TaskStatus.MODIFYING,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
            started_at="2020-01-01T00:00:00",  # 很久以前
        )
        locker.acquire_lock(lock)

        assert locker.check_stale_lock()

    def test_stale_lock_detected_not_cleaned(self, temp_project):
        """测试残留锁被检测但不自动清理（设计要求不按时间自动清理）"""
        locker = TaskLocker(temp_project)

        # 创建一个超时的锁
        lock = TaskLock(
            status=TaskStatus.MODIFYING,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1-test",
            base_commit="abc123",
            started_at="2020-01-01T00:00:00",
        )
        locker.acquire_lock(lock)

        # check_stale_lock 检测到残留
        assert locker.check_stale_lock()
        # 但锁仍然存在（不自动清理）
        assert locker.is_locked()
