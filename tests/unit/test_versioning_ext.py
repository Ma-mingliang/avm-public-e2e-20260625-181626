"""AVM 版本号计算扩展测试 - 覆盖远程操作和文档版本"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.core.io import atomic_write_json
from avm.core.paths import get_version_index_json_path
from avm.exceptions import VersionError
from avm.git.versioning import VersionCalculator


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestRemoteTagVersions:
    """远程标签版本号测试"""

    @patch("avm.git.versioning.GitOps")
    def test_get_remote_tag_versions_none(self, mock_git_cls, project_dir):
        """测试无远程标签"""
        mock_git = MagicMock()
        mock_git.get_max_version_tag_remote.return_value = 0
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        result = calc._get_remote_tag_versions()
        assert result == set()

    @patch("avm.git.versioning.GitOps")
    def test_get_remote_tag_versions_some(self, mock_git_cls, project_dir):
        """测试有远程标签"""
        mock_git = MagicMock()
        mock_git.get_max_version_tag_remote.return_value = 3
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        result = calc._get_remote_tag_versions()
        assert result == {1, 2, 3}

    @patch("avm.git.versioning.GitOps")
    def test_get_remote_tag_versions_error(self, mock_git_cls, project_dir):
        """测试远程标签查询失败"""
        mock_git = MagicMock()
        mock_git.get_max_version_tag_remote.side_effect = Exception("network error")
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        with pytest.raises(VersionError, match="无法获取远程标签"):
            calc._get_remote_tag_versions()


class TestBranchVersions:
    """分支版本号测试"""

    @patch("avm.git.versioning.GitOps")
    def test_get_branch_versions_none(self, mock_git_cls, project_dir):
        """测试无远程分支"""
        mock_git = MagicMock()
        mock_git.get_max_version_branch.return_value = 0
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        result = calc._get_branch_versions()
        assert result == set()

    @patch("avm.git.versioning.GitOps")
    def test_get_branch_versions_some(self, mock_git_cls, project_dir):
        """测试有远程分支"""
        mock_git = MagicMock()
        mock_git.get_max_version_branch.return_value = 2
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        result = calc._get_branch_versions()
        assert result == {1, 2}

    @patch("avm.git.versioning.GitOps")
    def test_get_branch_versions_error(self, mock_git_cls, project_dir):
        """测试分支查询失败"""
        mock_git = MagicMock()
        mock_git.get_max_version_branch.side_effect = Exception("network error")
        mock_git_cls.return_value = mock_git

        calc = VersionCalculator(project_dir)
        with pytest.raises(VersionError, match="无法获取远程分支"):
            calc._get_branch_versions()


class TestIndexVersions:
    """版本索引版本号测试"""

    @patch("avm.git.versioning.GitOps")
    def test_get_index_versions_no_file(self, mock_git_cls, project_dir):
        """测试无版本索引文件"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        result = calc._get_index_versions()
        assert result == set()

    @patch("avm.git.versioning.GitOps")
    def test_get_index_versions_with_data(self, mock_git_cls, project_dir):
        """测试有版本索引数据"""
        mock_git_cls.return_value = MagicMock()
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [
                    {"version": "v1", "status": "completed"},
                    {"version": "v3", "status": "completed"},
                ],
                "document_versions": [],
                "abandoned_versions": [
                    {"version": "v2", "status": "abandoned"},
                ],
                "pending_archives": [],
            },
        )

        calc = VersionCalculator(project_dir)
        result = calc._get_index_versions()
        assert result == {1, 2, 3}

    @patch("avm.git.versioning.GitOps")
    def test_get_index_versions_invalid_format(self, mock_git_cls, project_dir):
        """测试版本索引格式异常时抛出 VersionError"""
        mock_git_cls.return_value = MagicMock()
        index_path = get_version_index_json_path(project_dir)
        index_path.write_text("not json", encoding="utf-8")

        calc = VersionCalculator(project_dir)
        with pytest.raises(VersionError, match="版本索引损坏"):
            calc._get_index_versions()


class TestParseVersion:
    """版本号解析测试"""

    @patch("avm.git.versioning.GitOps")
    def test_parse_version_valid(self, mock_git_cls, project_dir):
        """测试有效版本号"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc._parse_version("v1") == 1
        assert calc._parse_version("v42") == 42

    @patch("avm.git.versioning.GitOps")
    def test_parse_version_invalid(self, mock_git_cls, project_dir):
        """测试无效版本号"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc._parse_version("v1.0.0") is None
        assert calc._parse_version("1.0") is None
        assert calc._parse_version("abc") is None
        assert calc._parse_version("") is None


class TestDocVersion:
    """文档版本号测试"""

    @patch("avm.git.versioning.GitOps")
    def test_get_doc_version_no_index(self, mock_git_cls, project_dir):
        """测试无索引时文档版本为 1"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc.get_doc_version() == 1

    @patch("avm.git.versioning.GitOps")
    def test_get_doc_version_with_existing(self, mock_git_cls, project_dir):
        """测试有已有文档版本"""
        mock_git_cls.return_value = MagicMock()
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [
                    {"version": "doc-v1"},
                    {"version": "doc-v3"},
                ],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        calc = VersionCalculator(project_dir)
        assert calc.get_doc_version() == 4

    @patch("avm.git.versioning.GitOps")
    def test_get_doc_version_corrupted_index(self, mock_git_cls, project_dir):
        """测试索引损坏时抛出 VersionError"""
        mock_git_cls.return_value = MagicMock()
        index_path = get_version_index_json_path(project_dir)
        index_path.write_text("not json", encoding="utf-8")

        calc = VersionCalculator(project_dir)
        with pytest.raises(VersionError, match="版本索引损坏"):
            calc.get_doc_version()


class TestParseDocVersion:
    """文档版本号解析测试"""

    @patch("avm.git.versioning.GitOps")
    def test_parse_doc_version_valid(self, mock_git_cls, project_dir):
        """测试有效文档版本号"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc._parse_doc_version("doc-v1") == 1
        assert calc._parse_doc_version("doc-v10") == 10

    @patch("avm.git.versioning.GitOps")
    def test_parse_doc_version_invalid(self, mock_git_cls, project_dir):
        """测试无效文档版本号"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc._parse_doc_version("v1") is None
        assert calc._parse_doc_version("doc-1") is None
        assert calc._parse_doc_version("abc") is None


class TestReserveVersion:
    """预留版本号测试"""

    @patch("avm.git.versioning.GitOps")
    def test_reserve_version_new(self, mock_git_cls, project_dir):
        """测试预留新版本号"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        assert calc.reserve_version(5) is True

        index_path = get_version_index_json_path(project_dir)
        data = json.loads(index_path.read_text(encoding="utf-8"))
        assert any(v["version"] == "v5" for v in data["formal_versions"])

    @patch("avm.git.versioning.GitOps")
    def test_reserve_version_existing(self, mock_git_cls, project_dir):
        """测试预留已存在的版本号"""
        mock_git_cls.return_value = MagicMock()
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [{"version": "v1", "status": "completed"}],
                "document_versions": [],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        calc = VersionCalculator(project_dir)
        assert calc.reserve_version(1) is True

    @patch("avm.git.versioning.GitOps")
    def test_reserve_version_creates_index(self, mock_git_cls, project_dir):
        """测试预留版本时创建索引"""
        mock_git_cls.return_value = MagicMock()
        calc = VersionCalculator(project_dir)
        calc.reserve_version(1)

        index_path = get_version_index_json_path(project_dir)
        assert index_path.exists()


class TestGetNextVersionFull:
    """get_next_version 综合测试"""

    @patch("avm.git.versioning.GitOps")
    def test_get_next_version_all_sources(self, mock_git_cls, project_dir):
        """测试综合所有来源的版本号"""
        mock_git = MagicMock()
        mock_git.get_max_version_tag.return_value = 2
        mock_git.get_max_version_tag_remote.return_value = 3
        mock_git.get_max_version_branch.return_value = 1
        mock_git_cls.return_value = mock_git

        # 写入版本索引
        index_path = get_version_index_json_path(project_dir)
        atomic_write_json(
            index_path,
            {
                "schema_version": 1,
                "formal_versions": [{"version": "v5"}],
                "document_versions": [],
                "abandoned_versions": [],
                "pending_archives": [],
            },
        )

        calc = VersionCalculator(project_dir)
        # max of {1,2} U {1,2,3} U {1} U {5} = 5, next = 6
        assert calc.get_next_version() == 6
