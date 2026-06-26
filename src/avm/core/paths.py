"""AVM 路径工具"""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(path: Path | str) -> Path:
    """规范化路径，处理Windows长路径"""
    p = Path(path).resolve()
    # Windows长路径支持
    if os.name == "nt" and len(str(p)) > 260:
        return Path(f"\\\\?\\{p}")
    return p


def safe_join(base: Path, *parts: str | Path) -> Path:
    """安全拼接路径，防止路径遍历"""
    result = base
    for part in parts:
        p = Path(part)
        # 检查是否为绝对路径或包含 ..
        if p.is_absolute():
            raise ValueError(f"不允许绝对路径: {part}")
        if ".." in p.parts:
            raise ValueError(f"不允许路径遍历: {part}")
        result = result / p
    return normalize_path(result)


def get_version_dir(project_root: Path) -> Path:
    """获取版本管理目录"""
    return project_root / "版本管理"


def get_config_dir(project_root: Path) -> Path:
    """获取项目配置目录"""
    return project_root / ".claude"


def get_codex_config_dir(project_root: Path) -> Path:
    """获取Codex配置目录"""
    return project_root / ".codex"


def get_task_lock_path(project_root: Path) -> Path:
    """获取任务锁文件路径"""
    return get_version_dir(project_root) / "当前任务.json"


def get_version_index_md_path(project_root: Path) -> Path:
    """获取版本索引Markdown路径"""
    return get_version_dir(project_root) / "版本索引.md"


def get_version_index_json_path(project_root: Path) -> Path:
    """获取版本索引JSON路径"""
    return get_version_dir(project_root) / "版本索引.json"


def get_handover_report_path(project_root: Path) -> Path:
    """获取最新接手报告路径"""
    return get_version_dir(project_root) / "最新接手项目审查报告.md"


def get_formal_version_dir(project_root: Path, version: str) -> Path:
    """获取正式版本目录"""
    return get_version_dir(project_root) / "正式版本" / version


def get_document_version_dir(project_root: Path, version: str) -> Path:
    """获取文档版本目录"""
    return get_version_dir(project_root) / "文档版本" / version


def get_abandoned_dir(project_root: Path) -> Path:
    """获取废弃版本目录"""
    return get_version_dir(project_root) / "废弃版本"


def get_interrupt_dir(project_root: Path) -> Path:
    """获取中断任务目录"""
    return get_version_dir(project_root) / "中断任务"


def get_pending_archive_dir(project_root: Path) -> Path:
    """获取待归档目录"""
    return get_version_dir(project_root) / "待归档文档记录"


def get_approval_path(project_root: Path, version: str) -> Path:
    """获取审批记录路径"""
    return get_formal_version_dir(project_root, version) / "approval.json"


def get_metadata_path(project_root: Path, version: str) -> Path:
    """获取版本元数据路径"""
    return get_formal_version_dir(project_root, version) / "metadata.json"


def get_context_path(project_root: Path) -> Path:
    """获取AVM上下文文件路径"""
    return get_version_dir(project_root) / ".avm-context.json"


def get_backup_dir(project_root: Path, doc_version: str) -> Path:
    """获取文档备份目录"""
    return get_document_version_dir(project_root, doc_version) / "修改前备份"


def is_windows_long_path(path: Path | str) -> bool:
    """检查路径是否需要Windows长路径前缀"""
    if os.name != "nt":
        return False
    return len(str(path)) > 260


def get_git_hooks_dir(project_root: Path) -> Path:
    """获取Git Hooks目录"""
    return project_root / ".git" / "hooks"
