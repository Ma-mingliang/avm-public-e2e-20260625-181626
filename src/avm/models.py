"""AVM 数据模型定义"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    """任务状态枚举"""

    # 正常流程
    IDLE = "IDLE"
    PREFLIGHT = "PREFLIGHT"
    WAIT_START_APPROVAL = "WAIT_START_APPROVAL"
    RESERVED = "RESERVED"
    LOCKED = "LOCKED"
    BRANCH_READY = "BRANCH_READY"
    MODIFYING = "MODIFYING"
    VALIDATING = "VALIDATING"
    DRAFT_PR = "DRAFT_PR"
    FIXING = "FIXING"
    REVIEW_MATERIAL_READY = "REVIEW_MATERIAL_READY"
    WAIT_FINAL_APPROVAL = "WAIT_FINAL_APPROVAL"
    PR_READY = "PR_READY"
    MERGING = "MERGING"
    TAGGING = "TAGGING"
    RELEASING = "RELEASING"
    HANDOFF_UPDATING = "HANDOFF_UPDATING"
    CLEANING = "CLEANING"
    COMPLETE = "COMPLETE"

    # 异常状态
    INTERRUPTED = "INTERRUPTED"
    ABANDONED = "ABANDONED"
    PUBLISH_INCOMPLETE = "PUBLISH_INCOMPLETE"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    NETWORK_BLOCKED = "NETWORK_BLOCKED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    APPROVAL_INVALIDATED = "APPROVAL_INVALIDATED"

    def is_terminal(self) -> bool:
        """是否为终态"""
        return self in (
            TaskStatus.COMPLETE,
            TaskStatus.ABANDONED,
        )

    def is_error(self) -> bool:
        """是否为错误状态"""
        return self in (
            TaskStatus.INTERRUPTED,
            TaskStatus.AUTH_BLOCKED,
            TaskStatus.NETWORK_BLOCKED,
            TaskStatus.SECURITY_BLOCKED,
            TaskStatus.APPROVAL_INVALIDATED,
            TaskStatus.PUBLISH_INCOMPLETE,
        )

    def is_active(self) -> bool:
        """是否为活动状态（需要接管）"""
        return not self.is_terminal() and self != TaskStatus.IDLE


class TaskType(StrEnum):
    """任务类型枚举"""

    MANDATORY_PROJECT_VERSION = "MANDATORY_PROJECT_VERSION"
    OPTIONAL_DOCUMENT_VERSION = "OPTIONAL_DOCUMENT_VERSION"
    READ_ONLY = "READ_ONLY"
    BLOCKED_UNCLEAR = "BLOCKED_UNCLEAR"


class ApprovalType(StrEnum):
    """审批类型枚举"""

    START = "START"
    SCOPE_EXPANSION = "SCOPE_EXPANSION"
    FINAL_RELEASE = "FINAL_RELEASE"
    RELEASE_ASSET = "RELEASE_ASSET"
    INTERRUPT_TAKEOVER = "INTERRUPT_TAKEOVER"
    CLEANUP = "CLEANUP"
    TOOL_UPGRADE = "TOOL_UPGRADE"


class AgentType(StrEnum):
    """Agent类型枚举"""

    CLAUDE_CODE = "claude-code"
    HERMES = "hermes"
    CODEX = "codex"


class ProjectInfo(BaseModel):
    """项目信息"""

    name: str
    root: str = "."
    github_repo: str | None = None
    default_branch: str = "main"


class VersioningConfig(BaseModel):
    """版本配置"""

    formal_prefix: str = "v"
    document_prefix: str = "doc-v"
    never_reuse_reserved: bool = True
    one_active_task: bool = True
    merge_strategy: str = "squash"


class LanguageConfig(BaseModel):
    """语言配置"""

    user_facing: str = "zh-CN"
    machine_identifiers: str = "ascii"


class ValidationCommand(BaseModel):
    """验证命令"""

    name: str
    command: list[str]


class ValidationConfig(BaseModel):
    """验证配置"""

    commands: list[ValidationCommand] = Field(default_factory=list)


class RiskConfig(BaseModel):
    """风险配置"""

    extra_file_limit: int = 5
    expansion_ratio: float = 0.5
    sensitive_patterns: list[str] = Field(default_factory=list)
    high_risk_paths: list[str] = Field(default_factory=list)


class LfsConfig(BaseModel):
    """Git LFS配置"""

    enabled: bool = False
    patterns: list[str] = Field(default_factory=list)


class AgentAdaptersConfig(BaseModel):
    """Agent适配器配置"""

    claude_code: bool = True
    hermes: bool = True
    codex: bool = True


class ProjectConfig(BaseModel):
    """项目配置"""

    schema_version: int = 1
    project: ProjectInfo
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    lfs: LfsConfig = Field(default_factory=LfsConfig)
    agent_adapters: AgentAdaptersConfig = Field(default_factory=AgentAdaptersConfig)


class TaskLock(BaseModel):
    """任务锁"""

    schema_version: int = 1
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.IDLE
    previous_status: TaskStatus | None = None  # 进入错误状态前的状态
    version: str = ""
    agent: AgentType = AgentType.CLAUDE_CODE
    branch: str = ""
    base_commit: str = ""
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expected_files: list[str] = Field(default_factory=list)
    remote_lock_ref: str | None = "refs/heads/avm/system-lock"
    approval_id: str | None = None


class ApprovalRecord(BaseModel):
    """审批记录"""

    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    version: str
    approval_type: ApprovalType
    approver: str
    signature: str = ""  # HMAC-SHA256
    scope_files: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = ""
    content_hash: str = ""  # 绑定文件内容、base_commit、配置等的哈希

    def is_expired(self) -> bool:
        """检查是否过期"""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.now()
            return now > expires
        except (ValueError, TypeError):
            return True


class VersionIndex(BaseModel):
    """版本索引"""

    schema_version: int = 1
    formal_versions: list[dict[str, Any]] = Field(default_factory=list)
    document_versions: list[dict[str, Any]] = Field(default_factory=list)
    abandoned_versions: list[dict[str, Any]] = Field(default_factory=list)
    pending_archives: list[dict[str, Any]] = Field(default_factory=list)


class HandoverReport(BaseModel):
    """接手项目审查报告"""

    report_version: str = ""
    formal_version: str = ""
    formal_branch: str = ""
    base_commit: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    generated_agent: str = ""
    project_goal: str = ""
    architecture: str = ""
    build_test_commands: str = ""
    recent_changes: str = ""
    current_config: str = ""
    current_risks: str = ""
    legacy_issues: str = ""
    pending_tasks: str = ""
    pending_doc_archives: str = ""
    history_index: str = ""
    when_to_review_history: str = ""
