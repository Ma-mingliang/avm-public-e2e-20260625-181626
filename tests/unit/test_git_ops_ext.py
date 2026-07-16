"""AVM Git 操作扩展测试 - 覆盖远程操作和边界情况"""

import subprocess
from unittest.mock import patch

import pytest

from avm.exceptions import GitError
from avm.git.ops import GitOps


@pytest.fixture
def git_repo(tmp_path):
    """创建临时 Git 仓库"""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (repo / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


class TestRemoteUrl:
    """远程 URL 测试"""

    def test_get_remote_url(self, git_repo):
        """测试获取远程 URL（无远程时返回 None）"""
        ops = GitOps(git_repo)
        assert ops.get_remote_url() is None

    def test_get_remote_url_with_remote(self, git_repo):
        """测试有远程时获取 URL"""
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=git_repo,
            capture_output=True,
        )
        ops = GitOps(git_repo)
        url = ops.get_remote_url()
        assert url == "https://github.com/test/repo.git"


class TestDefaultBranch:
    """默认分支测试"""

    def test_get_default_branch_local(self, git_repo):
        """测试获取本地默认分支"""
        ops = GitOps(git_repo)
        branch = ops.get_default_branch()
        assert branch in ["main", "master"]


class TestMaxVersionTagRemote:
    """远程标签版本号测试"""

    def test_get_max_version_tag_remote_no_remote(self, git_repo):
        """测试无远程时返回 0"""
        ops = GitOps(git_repo)
        result = ops.get_max_version_tag_remote()
        assert result == 0


class TestMaxVersionBranch:
    """远程分支版本号测试"""

    def test_get_max_version_branch_no_remote(self, git_repo):
        """测试无远程分支时返回 0"""
        ops = GitOps(git_repo)
        result = ops.get_max_version_branch()
        assert result == 0


class TestPush:
    """推送测试"""

    def test_push_no_remote(self, git_repo):
        """测试无远程时推送失败"""
        ops = GitOps(git_repo)
        assert ops.push() is False

    def test_push_tag_no_remote(self, git_repo):
        """测试无远程时推送标签失败"""
        ops = GitOps(git_repo)
        ops.create_annotated_tag("v1", "test")
        assert ops.push_tag("v1") is False


class TestCheckout:
    """分支切换测试"""

    def test_checkout_nonexistent_branch(self, git_repo):
        """测试切换到不存在的分支"""
        ops = GitOps(git_repo)
        assert ops.checkout("nonexistent-branch") is False


class TestDeleteBranchRemote:
    """远程分支删除测试"""

    def test_delete_remote_branch_no_remote(self, git_repo):
        """测试无远程时删除远程分支（check=False 不抛异常，返回 True）"""
        ops = GitOps(git_repo)
        # check=False 所以不会抛异常，返回 True
        result = ops.delete_branch("nonexistent", remote=True)
        assert result is True


class TestStageEmptyFiles:
    """暂存空文件列表测试"""

    def test_stage_empty_files(self, git_repo):
        """测试暂存空文件列表"""
        ops = GitOps(git_repo)
        assert ops.stage_files([]) is True


class TestCommitAllowEmpty:
    """空提交测试"""

    def test_commit_allow_empty(self, git_repo):
        """测试允许空提交"""
        ops = GitOps(git_repo)
        sha = ops.commit("empty commit", allow_empty=True)
        assert len(sha) == 40


class TestDiffSummary:
    """差异摘要测试"""

    def test_get_diff_summary_no_changes(self, git_repo):
        """测试无差异时返回空列表"""
        ops = GitOps(git_repo)
        diff = ops.get_diff_summary(staged=True)
        assert diff == []

    def test_get_diff_summary_unstaged(self, git_repo):
        """测试未暂存差异"""
        ops = GitOps(git_repo)
        (git_repo / "README.md").write_text("# Modified", encoding="utf-8")
        diff = ops.get_diff_summary(staged=False)
        assert len(diff) > 0


class TestGetStatusEdgeCases:
    """状态获取边界测试"""

    def test_get_status_with_untracked(self, git_repo):
        """测试有未跟踪文件的状态"""
        ops = GitOps(git_repo)
        (git_repo / "untracked.txt").write_text("new", encoding="utf-8")
        status = ops.get_status()
        assert "untracked.txt" in status["untracked"]

    def test_get_status_with_deleted(self, git_repo):
        """测试有删除文件的状态"""
        ops = GitOps(git_repo)
        (git_repo / "README.md").unlink()
        status = ops.get_status()
        # 删除文件应该出现在某个列表中
        assert "README.md" in str(status)


class TestGitErrorHandling:
    """Git 错误处理测试"""

    def test_run_git_timeout(self, tmp_path):
        """测试 Git 命令超时"""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)

        ops = GitOps(repo)
        with pytest.raises(GitError, match="超时"):
            ops._run_git(["log", "--all"], timeout=0)

    def test_run_git_not_found(self, tmp_path):
        """测试 Git 未安装"""
        repo = tmp_path / "repo"
        repo.mkdir()

        ops = GitOps(repo)
        with patch("avm.git.ops.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitError, match="未安装"):
                ops._run_git(["status"])

    def test_run_git_command_error(self, git_repo):
        """测试 Git 命令执行错误"""
        ops = GitOps(git_repo)
        with pytest.raises(GitError, match="Git 命令失败"):
            ops._run_git(["checkout", "nonexistent"], check=True)

    def test_run_git_no_check(self, git_repo):
        """测试不检查返回码"""
        ops = GitOps(git_repo)
        result = ops._run_git(["checkout", "nonexistent"], check=False)
        assert result.returncode != 0


class TestGetUncommittedChanges:
    """未提交修改测试"""

    def test_uncommitted_with_staged(self, git_repo):
        """测试有暂存文件时"""
        ops = GitOps(git_repo)
        (git_repo / "new.txt").write_text("new", encoding="utf-8")
        ops.stage_files(["new.txt"])
        changes = ops.get_uncommitted_changes()
        assert changes["has_changes"] is True


class TestNulSafeChinesePath:
    """NUL 安全的中文路径测试

    验证 get_status 和 get_diff_summary 使用 -z 标志后，
    中文路径不会被 C-style 转义，能正确返回原始 UTF-8 路径。
    """

    def test_get_status_chinese_untracked(self, git_repo):
        """测试 get_status 正确返回中文未跟踪文件路径"""
        ops = GitOps(git_repo)
        # 创建中文命名的文件
        (git_repo / "测试文件.txt").write_text("test", encoding="utf-8")

        status = ops.get_status()
        assert "测试文件.txt" in status["untracked"]

    def test_get_status_chinese_modified(self, git_repo):
        """测试 get_status 正确返回中文已修改文件路径"""
        ops = GitOps(git_repo)
        # 创建中文文件并提交
        (git_repo / "修改测试.txt").write_text("initial", encoding="utf-8")
        ops.stage_files(["修改测试.txt"])
        ops.commit("add chinese file")

        # 修改文件
        (git_repo / "修改测试.txt").write_text("modified", encoding="utf-8")
        status = ops.get_status()
        assert "修改测试.txt" in status["modified"]

    def test_get_status_chinese_dir_untracked(self, git_repo):
        """测试 get_status 正确返回中文目录下的未跟踪文件路径"""
        ops = GitOps(git_repo)
        # 创建中文目录和文件
        version_dir = git_repo / "版本管理"
        version_dir.mkdir()
        (version_dir / "config.txt").write_text("data", encoding="utf-8")

        status = ops.get_status()
        # 文件应该以中文目录路径出现
        untracked = status["untracked"]
        assert any("版本管理" in p for p in untracked)

    def test_get_status_space_in_path(self, git_repo):
        """测试 get_status 正确处理路径中有空格的文件"""
        ops = GitOps(git_repo)
        (git_repo / "file with spaces.txt").write_text("test", encoding="utf-8")

        status = ops.get_status()
        assert "file with spaces.txt" in status["untracked"]

    def test_get_status_preserves_tracked_space_path(self, git_repo):
        ops = GitOps(git_repo)
        path = git_repo / "my secret.txt"
        path.write_text("safe", encoding="utf-8")
        ops.stage_files([path.name])
        ops.commit("add spaced file")
        path.write_text("changed", encoding="utf-8")

        assert "my secret.txt" in ops.get_status()["modified"]

    def test_diff_summary_chinese_path(self, git_repo):
        """测试 get_diff_summary 正确返回中文文件路径"""
        ops = GitOps(git_repo)
        # 创建中文文件并提交
        (git_repo / "差异测试.txt").write_text("initial", encoding="utf-8")
        ops.stage_files(["差异测试.txt"])
        ops.commit("add file")

        # 修改文件
        (git_repo / "差异测试.txt").write_text("modified", encoding="utf-8")
        diff = ops.get_diff_summary(staged=False)
        assert len(diff) > 0
        assert any(d["path"] == "差异测试.txt" for d in diff)

    def test_diff_summary_staged_chinese_path(self, git_repo):
        """测试 get_diff_summary staged 模式正确返回中文文件路径"""
        ops = GitOps(git_repo)
        # 创建中文文件并提交（使其成为 tracked）
        (git_repo / "暂存测试.txt").write_text("initial", encoding="utf-8")
        ops.stage_files(["暂存测试.txt"])
        ops.commit("add file")

        # 修改 tracked 文件并暂存
        (git_repo / "暂存测试.txt").write_text("modified", encoding="utf-8")
        ops.stage_files(["暂存测试.txt"])

        diff = ops.get_diff_summary(staged=True)
        assert len(diff) > 0
        assert any(d["path"] == "暂存测试.txt" for d in diff)

    def test_get_status_no_c_style_quoting(self, git_repo):
        """验证 -z 模式下路径不包含 C-style 转义字符"""
        ops = GitOps(git_repo)
        (git_repo / "测试文件.txt").write_text("test", encoding="utf-8")

        status = ops.get_status()
        for path in status["untracked"]:
            # 路径不应包含反斜杠转义序列（如 æ）
            assert "\\" not in path, f"Path contains C-style escaping: {path}"

    def test_get_status_chinese_path_is_actual_utf8(self, git_repo):
        """验证返回的中文路径是正确的 UTF-8 字符串"""
        ops = GitOps(git_repo)
        chinese_name = "中文文件名测试.txt"
        (git_repo / chinese_name).write_text("test", encoding="utf-8")

        status = ops.get_status()
        assert chinese_name in status["untracked"]
        # 验证是正确的 Unicode 字符，不是字节序列
        for path in status["untracked"]:
            assert isinstance(path, str)
            # 中文字符的 ord 值应该在 CJK 范围内
            for char in path:
                if ord(char) > 127:
                    assert 0x4E00 <= ord(char) <= 0x9FFF or 0x3000 <= ord(char) <= 0x303F, (
                        f"Unexpected non-ASCII char: {char!r} (U+{ord(char):04X})"
                    )
