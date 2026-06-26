"""AVM 配置加载和管理"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigError
from .models import (
    AgentAdaptersConfig,
    LfsConfig,
    ProjectConfig,
    ProjectInfo,
    RiskConfig,
    ValidationConfig,
)

# 默认全局配置目录（优先 AVM_HOME 环境变量，否则 ~/.agent-version-manager）
DEFAULT_GLOBAL_DIR = Path(os.environ.get("AVM_HOME", str(Path.home() / ".agent-version-manager")))

# 项目配置文件名
PROJECT_CONFIG_FILE = "配置.yaml"
PROJECT_CONFIG_DIR = "版本管理"


def get_global_dir() -> Path:
    """获取全局安装目录"""
    env_dir = os.environ.get("AVM_HOME")
    if env_dir:
        return Path(env_dir)
    if DEFAULT_GLOBAL_DIR.exists():
        return DEFAULT_GLOBAL_DIR
    # 回退到用户目录
    return Path.home() / ".agent-version-manager"


def get_project_config_path(project_root: Path) -> Path:
    """获取项目配置文件路径"""
    return project_root / PROJECT_CONFIG_DIR / PROJECT_CONFIG_FILE


def load_project_config(project_root: Path) -> ProjectConfig:
    """加载项目配置"""
    config_path = get_project_config_path(project_root)
    if not config_path.exists():
        raise ConfigError(f"项目配置文件不存在: {config_path}")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件格式错误: {e}") from e
    except OSError as e:
        raise ConfigError(f"无法读取配置文件: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("配置文件必须是YAML字典")

    return _parse_config(data, project_root)


def _parse_config(data: dict[str, Any], project_root: Path) -> ProjectConfig:
    """解析配置数据"""
    schema_version = data.get("schema_version", 1)
    if schema_version != 1:
        raise ConfigError(f"不支持的配置schema版本: {schema_version}")

    project_data = data.get("project", {})
    project_info = ProjectInfo(
        name=project_data.get("name", project_root.name),
        root=str(project_root),
        github_repo=project_data.get("github_repo"),
        default_branch=project_data.get("default_branch", "main"),
    )

    versioning_data = data.get("versioning", {})
    from .models import VersioningConfig

    versioning = VersioningConfig(
        formal_prefix=versioning_data.get("formal_prefix", "v"),
        document_prefix=versioning_data.get("document_prefix", "doc-v"),
        never_reuse_reserved=versioning_data.get("never_reuse_reserved", True),
        one_active_task=versioning_data.get("one_active_task", True),
        merge_strategy=versioning_data.get("merge_strategy", "squash"),
    )

    language_data = data.get("language", {})
    from .models import LanguageConfig

    language = LanguageConfig(
        user_facing=language_data.get("user_facing", "zh-CN"),
        machine_identifiers=language_data.get("machine_identifiers", "ascii"),
    )

    validation_data = data.get("validation", {})
    from .models import ValidationCommand

    validation = ValidationConfig(
        commands=[
            ValidationCommand(name=cmd.get("name", ""), command=cmd.get("command", []))
            for cmd in validation_data.get("commands", [])
        ]
    )

    risk_data = data.get("risk", {})
    risk = RiskConfig(
        extra_file_limit=risk_data.get("extra_file_limit", 5),
        expansion_ratio=risk_data.get("expansion_ratio", 0.5),
        sensitive_patterns=risk_data.get("sensitive_patterns", []),
        high_risk_paths=risk_data.get("high_risk_paths", []),
    )

    lfs_data = data.get("lfs", {})
    lfs = LfsConfig(
        enabled=lfs_data.get("enabled", False),
        patterns=lfs_data.get("patterns", []),
    )

    adapters_data = data.get("agent_adapters", {})
    adapters = AgentAdaptersConfig(
        claude_code=adapters_data.get("claude_code", True),
        hermes=adapters_data.get("hermes", True),
        codex=adapters_data.get("codex", True),
    )

    return ProjectConfig(
        schema_version=schema_version,
        project=project_info,
        versioning=versioning,
        language=language,
        validation=validation,
        risk=risk,
        lfs=lfs,
        agent_adapters=adapters,
    )


def create_default_config(project_root: Path, project_name: str, github_repo: str | None = None) -> ProjectConfig:
    """创建默认项目配置"""
    return ProjectConfig(
        schema_version=1,
        project=ProjectInfo(
            name=project_name,
            root=str(project_root),
            github_repo=github_repo,
            default_branch="main",
        ),
    )


def save_project_config(config: ProjectConfig, project_root: Path) -> None:
    """保存项目配置"""
    config_path = get_project_config_path(project_root)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "schema_version": config.schema_version,
        "project": {
            "name": config.project.name,
            "root": config.project.root,
            "github_repo": config.project.github_repo,
            "default_branch": config.project.default_branch,
        },
        "versioning": {
            "formal_prefix": config.versioning.formal_prefix,
            "document_prefix": config.versioning.document_prefix,
            "never_reuse_reserved": config.versioning.never_reuse_reserved,
            "one_active_task": config.versioning.one_active_task,
            "merge_strategy": config.versioning.merge_strategy,
        },
        "language": {
            "user_facing": config.language.user_facing,
            "machine_identifiers": config.language.machine_identifiers,
        },
        "validation": {
            "commands": [{"name": cmd.name, "command": cmd.command} for cmd in config.validation.commands],
        },
        "risk": {
            "extra_file_limit": config.risk.extra_file_limit,
            "expansion_ratio": config.risk.expansion_ratio,
            "sensitive_patterns": config.risk.sensitive_patterns,
            "high_risk_paths": config.risk.high_risk_paths,
        },
        "lfs": {
            "enabled": config.lfs.enabled,
            "patterns": config.lfs.patterns,
        },
        "agent_adapters": {
            "claude_code": config.agent_adapters.claude_code,
            "hermes": config.agent_adapters.hermes,
            "codex": config.agent_adapters.codex,
        },
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except OSError as e:
        raise ConfigError(f"无法写入配置文件: {e}") from e
