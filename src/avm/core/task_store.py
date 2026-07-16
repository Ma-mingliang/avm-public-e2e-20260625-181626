"""并发安全、fail-closed 的任务状态存储。"""

from __future__ import annotations

from pathlib import Path

from filelock import FileLock

from ..exceptions import StateConflictError, StateCorruptionError
from ..models import TaskLock
from .io import atomic_write_json, read_json
from .paths import get_task_lock_path


class TaskStore:
    """通过文件锁和 revision compare-and-swap 管理 TaskLock。"""

    def __init__(self, project_root: Path):
        self.path = get_task_lock_path(project_root)
        self.guard = FileLock(str(self.path) + ".guard")

    def _read_unlocked(self) -> TaskLock | None:
        if not self.path.exists():
            return None
        try:
            data = read_json(self.path)
            if not isinstance(data, dict):
                raise TypeError("根节点必须是对象")
            value = TaskLock(**data)
            # 旧 schema 的默认 task_id 每次解析都会变化，必须在首次受锁
            # 读取时物化，否则后续 CAS 会把同一任务误判成不同任务。
            if data.get("schema_version", 1) < 2 or not data.get("task_id") or "revision" not in data:
                atomic_write_json(self.path, value.model_dump())
            return value
        except Exception as exc:
            raise StateCorruptionError(f"任务状态损坏: {self.path}") from exc

    def read(self) -> TaskLock | None:
        with self.guard:
            return self._read_unlocked()

    def create(self, value: TaskLock) -> TaskLock:
        with self.guard:
            if self.path.exists():
                # 即使文件损坏也不得覆盖。
                self._read_unlocked()
                raise StateConflictError("任务状态已存在")
            saved = value.model_copy(update={"revision": 0})
            atomic_write_json(self.path, saved.model_dump())
            return saved

    def compare_and_write(self, expected: TaskLock, updated: TaskLock) -> TaskLock:
        with self.guard:
            current = self._read_unlocked()
            if current is None:
                if expected.revision != 0:
                    raise StateConflictError("任务状态已被删除")
                saved = updated.model_copy(update={"revision": 0})
            else:
                if current.task_id != expected.task_id or current.revision != expected.revision:
                    raise StateConflictError("任务状态 revision 冲突")
                saved = updated.model_copy(update={"revision": current.revision + 1})
            atomic_write_json(self.path, saved.model_dump())
            return saved

    def acquire(self, value: TaskLock) -> TaskLock:
        """仅当不存在活动任务时原子获取任务锁。"""
        with self.guard:
            current = self._read_unlocked()
            if current is not None and current.status.is_active():
                raise StateConflictError(f"任务状态已被占用: {current.agent}")
            revision = current.revision + 1 if current is not None else 0
            saved = value.model_copy(update={"revision": revision})
            atomic_write_json(self.path, saved.model_dump())
            return saved

    def delete(self) -> None:
        with self.guard:
            # 先解析，避免把损坏的事故现场当作可安全删除状态。
            if self.path.exists():
                self._read_unlocked()
                self.path.unlink()
