"""AVM Git 操作测试"""

import subprocess

import pytest

from avm.git.ops import GitOps


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


class TestGitOps:
    """Git 操作测试"""

    def test_detect_repo(self, git_repo):
        """测试仓库检测"""
        ops = GitOps(git_repo)
        assert ops.detect_repo()

    def test_detect_not_repo(self, tmp_path):
        """测试非仓库检测"""
        ops = GitOps(tmp_path)
        assert not ops.detect_repo()

    def test_get_current_branch(self, git_repo):
        """测试获取当前分支"""
        ops = GitOps(git_repo)
        branch = ops.get_current_branch()
        assert branch in ["main", "master"]

    def test_get_head_sha(self, git_repo):
        """测试获取 HEAD SHA"""
        ops = GitOps(git_repo)
        sha = ops.get_head_sha()
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_create_branch(self, git_repo):
        """测试创建分支"""
        ops = GitOps(git_repo)
        assert ops.create_branch("test-branch")
        assert ops.checkout("test-branch")
        assert ops.get_current_branch() == "test-branch"

    def test_delete_branch(self, git_repo):
        """测试删除分支"""
        ops = GitOps(git_repo)
        ops.create_branch("test-branch")
        assert ops.delete_branch("test-branch")

    def test_stage_and_commit(self, git_repo):
        """测试暂存和提交"""
        ops = GitOps(git_repo)

        # 创建新文件
        (git_repo / "new_file.txt").write_text("new content", encoding="utf-8")

        assert ops.stage_files(["new_file.txt"])
        sha = ops.commit("测试提交")
        assert len(sha) == 40

    def test_create_annotated_tag(self, git_repo):
        """测试创建注释标签"""
        ops = GitOps(git_repo)
        assert ops.create_annotated_tag("v1", "版本1")
        assert ops.get_max_version_tag() == 1

    def test_get_max_version_tag(self, git_repo):
        """测试获取最大版本标签"""
        ops = GitOps(git_repo)

        ops.create_annotated_tag("v1", "版本1")
        ops.create_annotated_tag("v3", "版本3")
        ops.create_annotated_tag("v2", "版本2")

        assert ops.get_max_version_tag() == 3

    def test_get_max_version_tag_ignores_semver(self, git_repo):
        """测试忽略语义化版本"""
        ops = GitOps(git_repo)

        ops.create_annotated_tag("v1", "版本1")
        ops.create_annotated_tag("v1.0.0", "语义化版本")
        ops.create_annotated_tag("v2.0.0-beta", "预发布版本")

        assert ops.get_max_version_tag() == 1

    def test_get_status(self, git_repo):
        """测试获取状态"""
        ops = GitOps(git_repo)
        status = ops.get_status()

        assert "branch" in status
        assert "modified" in status
        assert "untracked" in status

    def test_get_diff_summary(self, git_repo):
        """测试获取差异摘要"""
        ops = GitOps(git_repo)

        # 创建新文件并暂存
        (git_repo / "new.txt").write_text("new", encoding="utf-8")
        ops.stage_files(["new.txt"])

        diff = ops.get_diff_summary(staged=True)
        assert len(diff) > 0
        assert diff[0]["path"] == "new.txt"

    def test_install_hooks(self, git_repo):
        """测试安装 Hooks"""
        ops = GitOps(git_repo)
        assert ops.install_hooks()

        hooks = ops.check_hooks()
        assert hooks["pre-commit"]
        assert hooks["commit-msg"]
        assert hooks["pre-push"]

    def test_check_hooks_not_installed(self, git_repo):
        """测试检查未安装的 Hooks"""
        ops = GitOps(git_repo)
        hooks = ops.check_hooks()

        assert not hooks["pre-commit"]
        assert not hooks["commit-msg"]
        assert not hooks["pre-push"]

    def test_get_uncommitted_changes(self, git_repo):
        """测试获取未提交修改"""
        ops = GitOps(git_repo)

        # 无修改时
        changes = ops.get_uncommitted_changes()
        assert not changes["has_changes"]

        # 有修改时
        (git_repo / "new.txt").write_text("new", encoding="utf-8")
        changes = ops.get_uncommitted_changes()
        assert changes["has_changes"]

    def test_is_repo_alias(self, git_repo):
        """测试 is_repo 是 detect_repo 的别名"""
        ops = GitOps(git_repo)
        assert ops.is_repo() is True
        assert ops.is_repo() == ops.detect_repo()

    def test_is_repo_not_repo(self, tmp_path):
        """测试非仓库 is_repo 返回 False"""
        ops = GitOps(tmp_path)
        assert ops.is_repo() is False

    def test_get_current_branch_unborn(self, tmp_path):
        """测试空仓库（unborn branch）获取分支名"""
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
        ops = GitOps(repo)
        branch = ops.get_current_branch()
        assert branch in ["main", "master"]
