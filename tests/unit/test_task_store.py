"""可信任务状态存储测试。"""

import pytest

from avm.core.task_store import TaskStore
from avm.exceptions import StateConflictError, StateCorruptionError
from avm.models import TaskLock, TaskStatus


def test_corrupt_task_lock_raises_state_error(tmp_path):
    store = TaskStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(StateCorruptionError, match="任务状态损坏"):
        store.read()


def test_compare_and_write_rejects_stale_revision(tmp_path):
    store = TaskStore(tmp_path)
    first = store.create(TaskLock(status=TaskStatus.PREFLIGHT))
    current = store.compare_and_write(
        first,
        first.model_copy(update={"status": TaskStatus.WAIT_START_APPROVAL}),
    )

    with pytest.raises(StateConflictError, match="revision 冲突"):
        store.compare_and_write(first, first.model_copy(update={"status": TaskStatus.IDLE}))

    assert current.revision == 1


def test_acquire_allows_only_one_active_task(tmp_path):
    store = TaskStore(tmp_path)
    first = store.acquire(TaskLock(status=TaskStatus.RESERVED, version="v1"))

    with pytest.raises(StateConflictError, match="已被占用"):
        store.acquire(TaskLock(status=TaskStatus.RESERVED, version="v2"))

    assert store.read() == first
