"""AVM 版本号计算测试"""

import subprocess

import pytest

from avm.git.ops import GitOps
from avm.git.versioning import VersionCalculator


@pytest.fixture
def git_repo(tmp_path):
    """创建临时 Git 仓库"""
    repo = tmp_path / "repo"
    repo.mkdir()

    # 初始化 Git 仓库
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)

    # 创建初始提交
    (repo / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "初始提交"], cwd=repo, capture_output=True)

    return repo


class TestVersionCalculator:
    """版本号计算测试"""

    def test_get_next_version_no_tags(self, git_repo):
        """测试无标签时获取版本号"""
        calc = VersionCalculator(git_repo)
        assert calc.get_next_version() == 1

    def test_get_next_version_with_tags(self, git_repo):
        """测试有标签时获取版本号"""
        git = GitOps(git_repo)

        git.create_annotated_tag("v1", "版本1")
        git.create_annotated_tag("v2", "版本2")

        calc = VersionCalculator(git_repo)
        assert calc.get_next_version() == 3

    def test_get_next_version_gap(self, git_repo):
        """测试版本号间隙"""
        git = GitOps(git_repo)

        git.create_annotated_tag("v1", "版本1")
        git.create_annotated_tag("v5", "版本5")

        calc = VersionCalculator(git_repo)
        assert calc.get_next_version() == 6

    def test_validate_version_available(self, git_repo):
        """测试验证版本号可用"""
        git = GitOps(git_repo)
        git.create_annotated_tag("v1", "版本1")

        calc = VersionCalculator(git_repo)
        assert calc.validate_version_available(2)
        assert not calc.validate_version_available(1)

    def test_format_version(self, git_repo):
        """测试格式化版本号"""
        calc = VersionCalculator(git_repo)
        assert calc.format_version(1) == "v1"
        assert calc.format_version(10) == "v10"
        assert calc.format_version(1, prefix="doc-v") == "doc-v1"

    def test_get_doc_version(self, git_repo):
        """测试获取文档版本号"""
        calc = VersionCalculator(git_repo)
        assert calc.get_doc_version() == 1
