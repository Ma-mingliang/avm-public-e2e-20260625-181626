"""AVM Agent 适配器工厂"""

from __future__ import annotations

from pathlib import Path

from ..models import AgentType
from .base import AgentAdapter
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .hermes import HermesAdapter

# 适配器注册表
_ADAPTERS: dict[AgentType, type[AgentAdapter]] = {
    AgentType.CLAUDE_CODE: ClaudeCodeAdapter,
    AgentType.HERMES: HermesAdapter,
    AgentType.CODEX: CodexAdapter,
}


def get_adapter(agent_type: AgentType, project_root: Path) -> AgentAdapter:
    """获取适配器实例

    Args:
        agent_type: Agent 类型
        project_root: 项目根目录

    Returns:
        适配器实例

    Raises:
        ValueError: 如果 Agent 类型不支持
    """
    adapter_class = _ADAPTERS.get(agent_type)
    if adapter_class is None:
        raise ValueError(f"不支持的 Agent 类型: {agent_type}")
    return adapter_class(project_root)


def get_all_adapters(project_root: Path) -> list[AgentAdapter]:
    """获取所有适配器实例

    Args:
        project_root: 项目根目录

    Returns:
        适配器实例列表
    """
    return [adapter_class(project_root) for adapter_class in _ADAPTERS.values()]


def get_available_adapters(project_root: Path) -> list[AgentAdapter]:
    """获取所有可用的适配器实例

    Args:
        project_root: 项目根目录

    Returns:
        可用的适配器实例列表
    """
    return [a for a in get_all_adapters(project_root) if a.is_available()]


def detect_agent(project_root: Path) -> AgentAdapter | None:
    """自动检测当前 Agent

    Args:
        project_root: 项目根目录

    Returns:
        检测到的适配器，如果没有检测到返回 None
    """
    # 优先级：Claude Code > Hermes > Codex
    for agent_type in [AgentType.CLAUDE_CODE, AgentType.HERMES, AgentType.CODEX]:
        adapter = get_adapter(agent_type, project_root)
        if adapter.is_available():
            return adapter
    return None
