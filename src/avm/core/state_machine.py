"""AVM 状态机"""

from __future__ import annotations

from pathlib import Path

from ..core.io import atomic_write_json, read_json
from ..core.paths import get_task_lock_path
from ..exceptions import AVMError
from ..models import TaskLock, TaskStatus

# 合法状态转换矩阵
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.IDLE: {TaskStatus.PREFLIGHT},
    TaskStatus.PREFLIGHT: {TaskStatus.WAIT_START_APPROVAL, TaskStatus.IDLE},
    TaskStatus.WAIT_START_APPROVAL: {TaskStatus.RESERVED, TaskStatus.IDLE},
    TaskStatus.RESERVED: {TaskStatus.LOCKED, TaskStatus.IDLE},
    TaskStatus.LOCKED: {TaskStatus.BRANCH_READY},
    TaskStatus.BRANCH_READY: {TaskStatus.MODIFYING},
    TaskStatus.MODIFYING: {
        TaskStatus.VALIDATING,
    },
    TaskStatus.VALIDATING: {TaskStatus.REVIEW_MATERIAL_READY, TaskStatus.FIXING, TaskStatus.DRAFT_PR},
    TaskStatus.FIXING: {TaskStatus.VALIDATING},
    TaskStatus.DRAFT_PR: {TaskStatus.VALIDATING, TaskStatus.FIXING},
    TaskStatus.REVIEW_MATERIAL_READY: {TaskStatus.WAIT_FINAL_APPROVAL},
    TaskStatus.WAIT_FINAL_APPROVAL: {TaskStatus.PR_READY, TaskStatus.IDLE},
    TaskStatus.PR_READY: {TaskStatus.MERGING},
    TaskStatus.MERGING: {TaskStatus.TAGGING, TaskStatus.PUBLISH_INCOMPLETE},
    TaskStatus.TAGGING: {TaskStatus.RELEASING, TaskStatus.PUBLISH_INCOMPLETE},
    TaskStatus.RELEASING: {TaskStatus.HANDOFF_UPDATING, TaskStatus.PUBLISH_INCOMPLETE},
    TaskStatus.HANDOFF_UPDATING: {TaskStatus.CLEANING},
    TaskStatus.CLEANING: {TaskStatus.COMPLETE},
    TaskStatus.COMPLETE: {TaskStatus.IDLE},
    TaskStatus.PUBLISH_INCOMPLETE: {TaskStatus.TAGGING, TaskStatus.RELEASING, TaskStatus.CLEANING},
    TaskStatus.INTERRUPTED: {
        TaskStatus.IDLE,
        TaskStatus.RESERVED,
        TaskStatus.LOCKED,
        TaskStatus.BRANCH_READY,
        TaskStatus.MODIFYING,
        TaskStatus.ABANDONED,
    },
    TaskStatus.ABANDONED: {TaskStatus.IDLE},
    TaskStatus.AUTH_BLOCKED: {TaskStatus.IDLE, TaskStatus.PREFLIGHT},
    TaskStatus.NETWORK_BLOCKED: {TaskStatus.IDLE, TaskStatus.PREFLIGHT},
    TaskStatus.SECURITY_BLOCKED: {TaskStatus.IDLE},
    TaskStatus.APPROVAL_INVALIDATED: {TaskStatus.WAIT_FINAL_APPROVAL, TaskStatus.IDLE},
}

# 所有状态都可以转换到的异常状态（ABANDONED 只能从 INTERRUPTED 进入）
UNIVERSAL_ERROR_TARGETS = {
    TaskStatus.INTERRUPTED,
    TaskStatus.AUTH_BLOCKED,
    TaskStatus.NETWORK_BLOCKED,
    TaskStatus.SECURITY_BLOCKED,
    TaskStatus.APPROVAL_INVALIDATED,
}

# 需要记录 previous_status 的错误状态
ERROR_STATES = {
    TaskStatus.INTERRUPTED,
    TaskStatus.AUTH_BLOCKED,
    TaskStatus.NETWORK_BLOCKED,
    TaskStatus.SECURITY_BLOCKED,
    TaskStatus.APPROVAL_INVALIDATED,
    TaskStatus.PUBLISH_INCOMPLETE,
}


class StateMachine:
    """任务状态机"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._lock_path = get_task_lock_path(project_root)
        self._task_lock: TaskLock | None = None

    def load(self) -> TaskLock:
        """加载任务锁"""
        if self._lock_path.exists():
            try:
                data = read_json(self._lock_path)
                self._task_lock = TaskLock(**data)
            except Exception:
                self._task_lock = TaskLock(status=TaskStatus.IDLE)
        else:
            self._task_lock = TaskLock(status=TaskStatus.IDLE)
        return self._task_lock

    def save(self) -> None:
        """保存任务锁"""
        if self._task_lock is None:
            return
        atomic_write_json(self._lock_path, self._task_lock.model_dump())

    @property
    def current_status(self) -> TaskStatus:
        """当前状态"""
        if self._task_lock is None:
            self.load()
        return self._task_lock.status  # type: ignore

    @property
    def task_lock(self) -> TaskLock | None:
        """当前任务锁"""
        if self._task_lock is None:
            self.load()
        return self._task_lock

    def validate_transition(self, new_status: TaskStatus) -> bool:
        """验证状态转换是否合法"""
        current = self.current_status

        # 允许转换到通用异常状态
        if new_status in UNIVERSAL_ERROR_TARGETS:
            return True

        # 检查合法转换
        allowed = VALID_TRANSITIONS.get(current, set())
        return new_status in allowed

    def transition(self, new_status: TaskStatus, context: dict | None = None) -> bool:
        """执行状态转换

        Args:
            new_status: 目标状态
            context: 上下文信息（用于更新任务锁）

        Returns:
            是否成功

        Raises:
            AVMError: 如果转换不合法
        """
        if not self.validate_transition(new_status):
            raise AVMError(
                f"非法状态转换: {self.current_status.value} -> {new_status.value}",
                exit_code=2,
            )

        if self._task_lock is None:
            self.load()

        assert self._task_lock is not None

        # 进入错误状态时记录 previous_status
        if new_status in ERROR_STATES:
            self._task_lock.previous_status = self._task_lock.status

        self._task_lock.status = new_status

        # 更新上下文
        if context:
            if "version" in context:
                self._task_lock.version = context["version"]
            if "branch" in context:
                self._task_lock.branch = context["branch"]
            if "base_commit" in context:
                self._task_lock.base_commit = context["base_commit"]
            if "agent" in context:
                from ..models import AgentType

                agent_val = context["agent"]
                self._task_lock.agent = agent_val if isinstance(agent_val, AgentType) else AgentType(agent_val)
            if "expected_files" in context:
                self._task_lock.expected_files = context["expected_files"]
            if "approval_id" in context:
                self._task_lock.approval_id = context["approval_id"]

        self.save()
        return True

    def get_valid_transitions(self) -> list[TaskStatus]:
        """获取当前状态的合法转换列表"""
        current = self.current_status
        allowed = VALID_TRANSITIONS.get(current, set())
        return sorted(list(allowed | UNIVERSAL_ERROR_TARGETS), key=lambda x: x.value)

    def is_idle(self) -> bool:
        """是否为空闲状态"""
        return self.current_status == TaskStatus.IDLE

    def is_active(self) -> bool:
        """是否为活动状态"""
        return self.current_status.is_active()

    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.current_status.is_terminal()

    def is_error(self) -> bool:
        """是否为错误状态"""
        return self.current_status.is_error()

    def reset(self) -> None:
        """重置状态机到IDLE"""
        self._task_lock = TaskLock(status=TaskStatus.IDLE)
        self.save()

    def create_task(
        self,
        version: str,
        agent: str,
        branch: str,
        base_commit: str,
        expected_files: list[str] | None = None,
    ) -> TaskLock:
        """创建新任务"""
        from ..models import AgentType

        agent_type = agent if isinstance(agent, AgentType) else AgentType(agent)
        self._task_lock = TaskLock(
            status=TaskStatus.RESERVED,
            version=version,
            agent=agent_type,
            branch=branch,
            base_commit=base_commit,
            expected_files=expected_files or [],
        )
        self.save()
        return self._task_lock
