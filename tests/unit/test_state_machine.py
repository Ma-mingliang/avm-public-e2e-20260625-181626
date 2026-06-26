"""AVM 状态机测试"""

import pytest

from avm.core.state_machine import UNIVERSAL_ERROR_TARGETS, VALID_TRANSITIONS, StateMachine
from avm.exceptions import AVMError
from avm.models import TaskStatus


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestStateMachine:
    """状态机测试"""

    def test_initial_state(self, temp_project):
        """测试初始状态"""
        sm = StateMachine(temp_project)
        assert sm.current_status == TaskStatus.IDLE
        assert sm.is_idle()

    def test_valid_transition(self, temp_project):
        """测试合法状态转换"""
        sm = StateMachine(temp_project)
        assert sm.transition(TaskStatus.PREFLIGHT)
        assert sm.current_status == TaskStatus.PREFLIGHT

    def test_invalid_transition(self, temp_project):
        """测试非法状态转换"""
        sm = StateMachine(temp_project)
        with pytest.raises(AVMError) as exc_info:
            sm.transition(TaskStatus.MODIFYING)
        assert "非法状态转换" in str(exc_info.value)

    def test_idle_to_preflight(self, temp_project):
        """测试IDLE -> PREFLIGHT"""
        sm = StateMachine(temp_project)
        sm.transition(TaskStatus.PREFLIGHT)
        assert sm.current_status == TaskStatus.PREFLIGHT

    def test_preflight_to_wait_approval(self, temp_project):
        """测试PREFLIGHT -> WAIT_START_APPROVAL"""
        sm = StateMachine(temp_project)
        sm.transition(TaskStatus.PREFLIGHT)
        sm.transition(TaskStatus.WAIT_START_APPROVAL)
        assert sm.current_status == TaskStatus.WAIT_START_APPROVAL

    def test_full_flow(self, temp_project):
        """测试完整流程"""
        sm = StateMachine(temp_project)

        # IDLE -> PREFLIGHT -> WAIT_START_APPROVAL -> RESERVED -> LOCKED -> BRANCH_READY -> MODIFYING
        sm.transition(TaskStatus.PREFLIGHT)
        sm.transition(TaskStatus.WAIT_START_APPROVAL)
        sm.transition(TaskStatus.RESERVED)
        sm.transition(TaskStatus.LOCKED)
        sm.transition(TaskStatus.BRANCH_READY)
        sm.transition(TaskStatus.MODIFYING)

        assert sm.current_status == TaskStatus.MODIFYING

    def test_error_transition(self, temp_project):
        """测试错误状态转换"""
        sm = StateMachine(temp_project)
        sm.transition(TaskStatus.PREFLIGHT)

        # 任何状态都可以转换到 INTERRUPTED
        sm.transition(TaskStatus.INTERRUPTED)
        assert sm.current_status == TaskStatus.INTERRUPTED
        assert sm.is_error()

    def test_validation_flow(self, temp_project):
        """测试验证流程"""
        sm = StateMachine(temp_project)

        # 到达VALIDATING
        sm.transition(TaskStatus.PREFLIGHT)
        sm.transition(TaskStatus.WAIT_START_APPROVAL)
        sm.transition(TaskStatus.RESERVED)
        sm.transition(TaskStatus.LOCKED)
        sm.transition(TaskStatus.BRANCH_READY)
        sm.transition(TaskStatus.MODIFYING)
        sm.transition(TaskStatus.VALIDATING)

        # 验证失败 -> FIXING
        sm.transition(TaskStatus.FIXING)
        assert sm.current_status == TaskStatus.FIXING

        # FIXING -> VALIDATING
        sm.transition(TaskStatus.VALIDATING)
        assert sm.current_status == TaskStatus.VALIDATING

        # 验证通过 -> REVIEW_MATERIAL_READY
        sm.transition(TaskStatus.REVIEW_MATERIAL_READY)
        assert sm.current_status == TaskStatus.REVIEW_MATERIAL_READY

    def test_complete_flow(self, temp_project):
        """测试完整发布流程"""
        sm = StateMachine(temp_project)

        # 完整流程
        states = [
            TaskStatus.PREFLIGHT,
            TaskStatus.WAIT_START_APPROVAL,
            TaskStatus.RESERVED,
            TaskStatus.LOCKED,
            TaskStatus.BRANCH_READY,
            TaskStatus.MODIFYING,
            TaskStatus.VALIDATING,
            TaskStatus.REVIEW_MATERIAL_READY,
            TaskStatus.WAIT_FINAL_APPROVAL,
            TaskStatus.PR_READY,
            TaskStatus.MERGING,
            TaskStatus.TAGGING,
            TaskStatus.RELEASING,
            TaskStatus.HANDOFF_UPDATING,
            TaskStatus.CLEANING,
            TaskStatus.COMPLETE,
        ]

        for state in states:
            sm.transition(state)

        assert sm.current_status == TaskStatus.COMPLETE
        assert sm.is_terminal()

    def test_get_valid_transitions(self, temp_project):
        """测试获取合法转换列表"""
        sm = StateMachine(temp_project)
        transitions = sm.get_valid_transitions()

        # IDLE 只能转换到 PREFLIGHT
        assert TaskStatus.PREFLIGHT in transitions

        # 所有状态都可以转换到通用异常状态
        for error_status in UNIVERSAL_ERROR_TARGETS:
            assert error_status in transitions

    def test_persist_state(self, temp_project):
        """测试状态持久化"""
        sm1 = StateMachine(temp_project)
        sm1.transition(TaskStatus.PREFLIGHT)

        # 创建新的状态机实例，应该加载保存的状态
        sm2 = StateMachine(temp_project)
        assert sm2.current_status == TaskStatus.PREFLIGHT

    def test_create_task(self, temp_project):
        """测试创建任务"""
        sm = StateMachine(temp_project)
        lock = sm.create_task(
            version="v8",
            agent="claude-code",
            branch="agent/v8-test",
            base_commit="abc123",
            expected_files=["src/main.py"],
        )

        assert lock.version == "v8"
        assert lock.agent == "claude-code"
        assert lock.branch == "agent/v8-test"
        assert sm.current_status == TaskStatus.RESERVED

    def test_reset(self, temp_project):
        """测试重置"""
        sm = StateMachine(temp_project)
        sm.transition(TaskStatus.PREFLIGHT)
        sm.transition(TaskStatus.WAIT_START_APPROVAL)

        sm.reset()
        assert sm.current_status == TaskStatus.IDLE

    def test_error_states_from_any(self, temp_project):
        """测试从任意状态转换到错误状态（ABANDONED 只能从 INTERRUPTED 进入）"""
        error_states = [
            TaskStatus.INTERRUPTED,
            TaskStatus.AUTH_BLOCKED,
            TaskStatus.NETWORK_BLOCKED,
            TaskStatus.SECURITY_BLOCKED,
            TaskStatus.APPROVAL_INVALIDATED,
        ]

        for error_state in error_states:
            # 每次循环创建新的状态机并重置
            sm = StateMachine(temp_project)
            sm.reset()
            sm.transition(TaskStatus.PREFLIGHT)
            sm.transition(TaskStatus.WAIT_START_APPROVAL)
            sm.transition(TaskStatus.RESERVED)
            sm.transition(TaskStatus.LOCKED)

            assert sm.validate_transition(error_state), f"应该可以从 LOCKED 转换到 {error_state}"


class TestTransitionMatrix:
    """转换矩阵测试"""

    def test_all_states_have_transitions(self):
        """测试所有状态都有转换定义"""
        for status in TaskStatus:
            if status == TaskStatus.IDLE:
                continue
            # 每个非IDLE状态都应该有转换目标（或者可以转换到错误状态）
            has_target = status in VALID_TRANSITIONS or any(status in targets for targets in VALID_TRANSITIONS.values())
            # 或者是错误状态本身
            is_error = status in UNIVERSAL_ERROR_TARGETS
            assert has_target or is_error, f"状态 {status} 没有转换定义"

    def test_terminal_states_no_outgoing(self):
        """测试终态没有外出转换（除了回到IDLE）"""
        for status in TaskStatus:
            if status.is_terminal():
                if status in VALID_TRANSITIONS:
                    # 终态只能转换到IDLE
                    assert VALID_TRANSITIONS[status] == {TaskStatus.IDLE} or not VALID_TRANSITIONS[status]
