"""AVM 数据模型测试"""

from avm.models import (
    AgentType,
    ApprovalRecord,
    ApprovalType,
    ProjectConfig,
    ProjectInfo,
    TaskLock,
    TaskStatus,
    TaskType,
    VersioningConfig,
)


class TestTaskStatus:
    """任务状态测试"""

    def test_terminal_states(self):
        """测试终态"""
        assert TaskStatus.COMPLETE.is_terminal()
        assert TaskStatus.ABANDONED.is_terminal()
        assert not TaskStatus.IDLE.is_terminal()
        assert not TaskStatus.MODIFYING.is_terminal()

    def test_error_states(self):
        """测试错误状态"""
        assert TaskStatus.INTERRUPTED.is_error()
        assert TaskStatus.AUTH_BLOCKED.is_error()
        assert TaskStatus.NETWORK_BLOCKED.is_error()
        assert TaskStatus.SECURITY_BLOCKED.is_error()
        assert TaskStatus.APPROVAL_INVALIDATED.is_error()
        assert TaskStatus.PUBLISH_INCOMPLETE.is_error()
        assert not TaskStatus.IDLE.is_error()
        assert not TaskStatus.COMPLETE.is_error()

    def test_active_states(self):
        """测试活动状态"""
        assert TaskStatus.MODIFYING.is_active()
        assert TaskStatus.VALIDATING.is_active()
        assert not TaskStatus.IDLE.is_active()
        assert not TaskStatus.COMPLETE.is_active()
        assert not TaskStatus.ABANDONED.is_active()

    def test_string_value(self):
        """测试字符串值"""
        assert TaskStatus.IDLE.value == "IDLE"
        assert TaskStatus.MODIFYING.value == "MODIFYING"


class TestTaskType:
    """任务类型测试"""

    def test_values(self):
        """测试枚举值"""
        assert TaskType.MANDATORY_PROJECT_VERSION.value == "MANDATORY_PROJECT_VERSION"
        assert TaskType.OPTIONAL_DOCUMENT_VERSION.value == "OPTIONAL_DOCUMENT_VERSION"
        assert TaskType.READ_ONLY.value == "READ_ONLY"
        assert TaskType.BLOCKED_UNCLEAR.value == "BLOCKED_UNCLEAR"


class TestProjectConfig:
    """项目配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = ProjectConfig(project=ProjectInfo(name="test"))
        assert config.schema_version == 1
        assert config.project.name == "test"
        assert config.project.default_branch == "main"
        assert config.versioning.formal_prefix == "v"
        assert config.versioning.document_prefix == "doc-v"
        assert config.versioning.merge_strategy == "squash"
        assert config.language.user_facing == "zh-CN"

    def test_custom_config(self):
        """测试自定义配置"""
        config = ProjectConfig(
            project=ProjectInfo(name="myproject", github_repo="user/repo", default_branch="master"),
            versioning=VersioningConfig(formal_prefix="ver"),
        )
        assert config.project.github_repo == "user/repo"
        assert config.project.default_branch == "master"
        assert config.versioning.formal_prefix == "ver"


class TestTaskLock:
    """任务锁测试"""

    def test_default_lock(self):
        """测试默认锁"""
        lock = TaskLock()
        assert lock.schema_version == 1
        assert lock.status == TaskStatus.IDLE
        assert lock.task_id  # UUID should be generated

    def test_lock_with_values(self):
        """测试带值的锁"""
        lock = TaskLock(
            status=TaskStatus.MODIFYING,
            version="v8",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v8-test",
            base_commit="abc123",
        )
        assert lock.status == TaskStatus.MODIFYING
        assert lock.version == "v8"
        assert lock.agent == AgentType.CLAUDE_CODE
        assert lock.branch == "agent/v8-test"


class TestApprovalRecord:
    """审批记录测试"""

    def test_approval_record(self):
        """测试审批记录"""
        record = ApprovalRecord(
            approval_type=ApprovalType.START,
            version="v8",
            task_id="test-task-id",
            approver="test-user",
            signature="hmac-sha256-signature",
            scope_files=["src/main.py"],
            notes="Auto-approved",
        )
        assert record.approval_id  # UUID should be generated
        assert record.approval_type == ApprovalType.START
        assert record.approver == "test-user"
        assert record.signature == "hmac-sha256-signature"
        assert record.scope_files == ["src/main.py"]


class TestAgentType:
    """Agent类型测试"""

    def test_values(self):
        """测试枚举值"""
        assert AgentType.CLAUDE_CODE.value == "claude-code"
        assert AgentType.HERMES.value == "hermes"
        assert AgentType.CODEX.value == "codex"
