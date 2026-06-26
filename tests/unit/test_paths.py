"""AVM 路径工具测试"""

import os
from pathlib import Path

import pytest

from avm.core.paths import (
    get_abandoned_dir,
    get_approval_path,
    get_backup_dir,
    get_codex_config_dir,
    get_config_dir,
    get_context_path,
    get_document_version_dir,
    get_formal_version_dir,
    get_git_hooks_dir,
    get_handover_report_path,
    get_interrupt_dir,
    get_metadata_path,
    get_pending_archive_dir,
    get_task_lock_path,
    get_version_dir,
    get_version_index_json_path,
    get_version_index_md_path,
    is_windows_long_path,
    normalize_path,
    safe_join,
)


class TestNormalizePath:
    """路径规范化测试"""

    def test_normalize_relative_path(self, tmp_path):
        """测试相对路径规范化"""
        p = tmp_path / "test"
        result = normalize_path(p)
        assert result.is_absolute()

    def test_normalize_absolute_path(self, tmp_path):
        """测试绝对路径规范化"""
        result = normalize_path(tmp_path)
        assert result == tmp_path.resolve()


class TestSafeJoin:
    """安全路径拼接测试"""

    def test_safe_join_basic(self, tmp_path):
        """测试基本路径拼接"""
        result = safe_join(tmp_path, "subdir", "file.txt")
        assert result == normalize_path(tmp_path / "subdir" / "file.txt")

    def test_safe_join_rejects_absolute(self, tmp_path):
        """测试拒绝绝对路径"""
        abs_path = str(Path("/etc/passwd")) if os.name != "nt" else "C:\\Windows\\system32\\cmd.exe"
        with pytest.raises(ValueError, match="不允许绝对路径"):
            safe_join(tmp_path, abs_path)

    def test_safe_join_rejects_traversal(self, tmp_path):
        """测试拒绝路径遍历"""
        with pytest.raises(ValueError, match="不允许路径遍历"):
            safe_join(tmp_path, "../etc/passwd")

    def test_safe_join_with_path_object(self, tmp_path):
        """测试 Path 对象拼接"""
        result = safe_join(tmp_path, Path("sub") / "file.txt")
        assert "sub" in str(result)


class TestPathGetters:
    """路径获取函数测试"""

    def test_get_version_dir(self, tmp_path):
        """测试版本管理目录"""
        result = get_version_dir(tmp_path)
        assert result.name == "版本管理"

    def test_get_config_dir(self, tmp_path):
        """测试配置目录"""
        result = get_config_dir(tmp_path)
        assert result.name == ".claude"

    def test_get_codex_config_dir(self, tmp_path):
        """测试 Codex 配置目录"""
        result = get_codex_config_dir(tmp_path)
        assert result.name == ".codex"

    def test_get_task_lock_path(self, tmp_path):
        """测试任务锁路径"""
        result = get_task_lock_path(tmp_path)
        assert result.name == "当前任务.json"
        assert "版本管理" in str(result)

    def test_get_version_index_md_path(self, tmp_path):
        """测试版本索引 MD 路径"""
        result = get_version_index_md_path(tmp_path)
        assert result.name == "版本索引.md"

    def test_get_version_index_json_path(self, tmp_path):
        """测试版本索引 JSON 路径"""
        result = get_version_index_json_path(tmp_path)
        assert result.name == "版本索引.json"

    def test_get_handover_report_path(self, tmp_path):
        """测试接手报告路径"""
        result = get_handover_report_path(tmp_path)
        assert result.name == "最新接手项目审查报告.md"

    def test_get_formal_version_dir(self, tmp_path):
        """测试正式版本目录"""
        result = get_formal_version_dir(tmp_path, "v1")
        assert result.name == "v1"
        assert "正式版本" in str(result)

    def test_get_document_version_dir(self, tmp_path):
        """测试文档版本目录"""
        result = get_document_version_dir(tmp_path, "doc-v1")
        assert result.name == "doc-v1"
        assert "文档版本" in str(result)

    def test_get_abandoned_dir(self, tmp_path):
        """测试废弃版本目录"""
        result = get_abandoned_dir(tmp_path)
        assert result.name == "废弃版本"

    def test_get_interrupt_dir(self, tmp_path):
        """测试中断任务目录"""
        result = get_interrupt_dir(tmp_path)
        assert result.name == "中断任务"

    def test_get_pending_archive_dir(self, tmp_path):
        """测试待归档目录"""
        result = get_pending_archive_dir(tmp_path)
        assert result.name == "待归档文档记录"

    def test_get_approval_path(self, tmp_path):
        """测试审批记录路径"""
        result = get_approval_path(tmp_path, "v1")
        assert result.name == "approval.json"
        assert "v1" in str(result)

    def test_get_metadata_path(self, tmp_path):
        """测试版本元数据路径"""
        result = get_metadata_path(tmp_path, "v1")
        assert result.name == "metadata.json"

    def test_get_context_path(self, tmp_path):
        """测试 AVM 上下文路径"""
        result = get_context_path(tmp_path)
        assert result.name == ".avm-context.json"

    def test_get_backup_dir(self, tmp_path):
        """测试文档备份目录"""
        result = get_backup_dir(tmp_path, "doc-v1")
        assert result.name == "修改前备份"
        assert "doc-v1" in str(result)

    def test_get_git_hooks_dir(self, tmp_path):
        """测试 Git Hooks 目录"""
        result = get_git_hooks_dir(tmp_path)
        assert result.name == "hooks"
        assert ".git" in str(result)


class TestIsWindowsLongPath:
    """Windows 长路径检测测试"""

    def test_short_path(self, tmp_path):
        """测试短路径"""
        result = is_windows_long_path(tmp_path / "short")
        assert result is False

    def test_long_path(self):
        """测试长路径"""
        long_path = "C:\\" + "a" * 300
        result = is_windows_long_path(long_path)
        if os.name == "nt":
            assert result is True
        else:
            assert result is False
