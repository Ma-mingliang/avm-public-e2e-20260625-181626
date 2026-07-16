"""AVM 任务锁管理"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..exceptions import LockError
from ..models import TaskLock, TaskStatus
from .task_store import TaskStore


class TaskLocker:
    """任务锁管理器

    管理本地任务锁，确保同一项目同一时间只有一个活动任务。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._store = TaskStore(project_root)
        self.lock_path = self._store.path

    def get_lock(self) -> TaskLock | None:
        """获取当前任务锁

        Returns:
            任务锁，不存在时返回 None

        Raises:
            LockError: 如果锁文件存在但内容损坏
        """
        try:
            return self._store.read()
        except Exception as e:
            raise LockError(f"任务锁文件损坏: {e}") from e

    def is_locked(self) -> bool:
        """检查是否有活动锁"""
        lock = self.get_lock()
        if lock is None:
            return False

        # 检查是否为活动状态
        return lock.status.is_active()

    def acquire_lock(self, task_lock: TaskLock) -> bool:
        """获取任务锁

        Args:
            task_lock: 任务锁数据

        Returns:
            是否成功获取

        Raises:
            LockError: 如果锁已被占用
        """
        try:
            self._store.acquire(task_lock)
            return True
        except Exception as e:
            existing = self.get_lock()
            holder = existing.agent if existing else "unknown"
            raise LockError(f"任务锁已被占用: {holder}", lock_holder=str(holder)) from e

    def release_lock(self) -> bool:
        """释放任务锁"""
        self._store.delete()
        return True

    def update_lock(self, **kwargs) -> bool:
        """更新任务锁"""
        lock = self.get_lock()
        if lock is None:
            return False

        for key, value in kwargs.items():
            if hasattr(lock, key):
                setattr(lock, key, value)

        self._store.compare_and_write(lock, lock)
        return True

    def check_stale_lock(self, timeout_hours: int = 1) -> bool:
        """检查残留锁（仅检测，不自动清理）

        设计要求：锁不得按时间自动清理，需要用户审批恢复。
        此方法仅用于报告，不执行清理。

        Returns:
            是否疑似残留锁
        """
        lock = self.get_lock()
        if lock is None:
            return False

        # 检查是否为终态
        if lock.status.is_terminal() or lock.status == TaskStatus.IDLE:
            return False

        # 检查是否超时
        try:
            started_at = datetime.fromisoformat(lock.started_at.replace("Z", "+00:00"))
            now = datetime.now(started_at.tzinfo) if started_at.tzinfo else datetime.now()
            if now - started_at > timedelta(hours=timeout_hours):
                return True
        except (ValueError, TypeError):
            return True

        return False

    def get_lock_info(self) -> dict[str, Any]:
        """获取锁信息"""
        lock = self.get_lock()
        if lock is None:
            return {"locked": False}

        return {
            "locked": lock.status.is_active(),
            "task_id": lock.task_id,
            "version": lock.version,
            "agent": lock.agent,
            "branch": lock.branch,
            "status": lock.status.value,
            "started_at": lock.started_at,
        }
