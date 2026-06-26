"""AVM document 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.document import run_archive_pending_docs, run_document_complete, run_document_start
from avm.core.io import atomic_write_json
from avm.core.paths import get_pending_archive_dir, get_version_index_json_path


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestRunDocumentStart:
    """document-start 命令测试"""

    @patch("avm.commands.document.VersionCalculator")
    def test_document_start_success(self, mock_calc_cls, project_dir):
        """测试开始文档任务成功"""
        mock_calc = MagicMock()
        mock_calc.get_doc_version.return_value = 1
        mock_calc_cls.return_value = mock_calc

        # 创建实际文件
        (project_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
        (project_dir / "doc2.md").write_text("# Doc 2", encoding="utf-8")

        result = run_document_start(project_dir, ["doc1.md", "doc2.md"])
        assert result is True

        # 验证文档版本目录被创建
        doc_dir = project_dir / "版本管理" / "文档版本" / "doc-v1"
        assert doc_dir.exists()

    @patch("avm.commands.document.VersionCalculator")
    def test_document_start_json(self, mock_calc_cls, project_dir, capsys):
        """测试 JSON 输出"""
        mock_calc = MagicMock()
        mock_calc.get_doc_version.return_value = 1
        mock_calc_cls.return_value = mock_calc

        # 创建实际文件
        (project_dir / "readme.md").write_text("# Readme", encoding="utf-8")

        result = run_document_start(project_dir, ["readme.md"], json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["doc_version"] == "doc-v1"

    def test_document_start_wrong_state(self, project_dir):
        """测试错误状态"""
        # 写入一个活动状态的任务锁
        from avm.core.paths import get_task_lock_path

        lock_path = get_task_lock_path(project_dir)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            lock_path,
            {
                "schema_version": 1,
                "status": "RESERVED",
                "version": "v1",
                "agent": "claude-code",
                "branch": "agent/v1",
                "base_commit": "abc123",
                "started_at": "2024-01-01T00:00:00+00:00",
                "expected_files": [],
            },
        )

        result = run_document_start(project_dir, ["doc.md"])
        assert result is False

    @patch("avm.commands.document.VersionCalculator")
    def test_document_start_index_update(self, mock_calc_cls, project_dir):
        """测试版本索引被更新"""
        mock_calc = MagicMock()
        mock_calc.get_doc_version.return_value = 2
        mock_calc_cls.return_value = mock_calc

        # 创建实际文件
        (project_dir / "guide.md").write_text("# Guide", encoding="utf-8")

        run_document_start(project_dir, ["guide.md"])

        index_path = get_version_index_json_path(project_dir)
        assert index_path.exists()
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["document_versions"]) == 1
        assert index["document_versions"][0]["version"] == "doc-v2"


class TestRunDocumentComplete:
    """document-complete 命令测试"""

    def test_document_complete_success(self, project_dir):
        """测试完成文档任务成功"""
        # 创建版本索引，包含进行中的文档版本
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [
                    {
                        "version": "doc-v1",
                        "files": ["doc.md"],
                        "status": "in_progress",
                        "started_at": "2024-01-01T00:00:00+00:00",
                    },
                ],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        result = run_document_complete(project_dir)
        assert result is True

        # 验证状态已更新
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["document_versions"][0]["status"] == "completed"

    def test_document_complete_no_active(self, project_dir):
        """测试没有进行中的文档版本"""
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        result = run_document_complete(project_dir)
        assert result is False

    def test_document_complete_no_index(self, project_dir):
        """测试版本索引不存在"""
        result = run_document_complete(project_dir)
        assert result is False

    def test_document_complete_json(self, project_dir, capsys):
        """测试 JSON 输出"""
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [
                    {
                        "version": "doc-v1",
                        "files": [],
                        "status": "in_progress",
                        "started_at": "2024-01-01T00:00:00+00:00",
                    },
                ],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        result = run_document_complete(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True


class TestRunArchivePendingDocs:
    """archive-pending-docs 命令测试"""

    def test_archive_no_pending_dir(self, project_dir):
        """测试没有待归档目录"""
        result = run_archive_pending_docs(project_dir)
        assert result is True

    def test_archive_empty_pending_dir(self, project_dir):
        """测试空的待归档目录"""
        pending_dir = get_pending_archive_dir(project_dir)
        pending_dir.mkdir(parents=True)

        result = run_archive_pending_docs(project_dir)
        assert result is True

    def test_archive_with_files(self, project_dir):
        """测试归档文件"""
        pending_dir = get_pending_archive_dir(project_dir)
        pending_dir.mkdir(parents=True)
        (pending_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
        (pending_dir / "doc2.md").write_text("# Doc 2", encoding="utf-8")

        result = run_archive_pending_docs(project_dir)
        assert result is True

        # 验证索引被更新
        index_path = get_version_index_json_path(project_dir)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["pending_archives"]) == 1
        assert len(index["pending_archives"][0]["files"]) == 2

    def test_archive_json(self, project_dir, capsys):
        """测试 JSON 输出"""
        pending_dir = get_pending_archive_dir(project_dir)
        pending_dir.mkdir(parents=True)
        (pending_dir / "test.md").write_text("test", encoding="utf-8")

        result = run_archive_pending_docs(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["archived_count"] == 1
