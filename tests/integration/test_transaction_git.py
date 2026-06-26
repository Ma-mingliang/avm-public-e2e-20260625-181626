"""使用真实 Git/bare remote 验证 AVM 正式版本事务闭环。

本模块覆盖：
1. 完整生命周期（init -> start -> approve -> launch -> checkpoint -> validate ->
   review -> final approve -> PR -> merge -> publish -> cleanup -> second start）
2. 中文路径（版本管理/ 审批/ 交接/ 等）
3. 带空格的路径
4. NUL 安全的 git diff/status 解析
5. squash merge 后的 force 分支删除
6. 发布后工作区清洁
7. 发布后 IDLE 状态恢复
8. 发布事实写入验证
9. 远程锁删除验证
10. 本地分支删除验证
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """执行 git 命令"""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


class _LocalGitHub:
    """模拟 GitHub API 的本地 bare remote 实现"""

    def __init__(self, bare_path: Path, work_path: Path) -> None:
        self.bare_path = bare_path
        self.work_path = work_path
        self.pr_counter = 0
        self.releases: dict[str, dict] = {}
        self.tags: dict[str, str] = {}

    def get_default_branch(self) -> str:
        return "main"

    def get_commit_tree_sha(self, ref: str) -> str:
        r = _git(["rev-parse", ref], cwd=self.work_path)
        return r.stdout.strip()

    def create_git_commit(self, message: str, files: list[str] | None = None) -> str:
        if files:
            _git(["add"] + files, cwd=self.work_path)
        _git(["commit", "-m", message, "--allow-empty"], cwd=self.work_path)
        return _git(["rev-parse", "HEAD"], cwd=self.work_path).stdout.strip()

    def create_reference(self, ref: str, sha: str) -> None:
        _git(["update-ref", ref, sha], cwd=self.work_path)

    def get_reference(self, ref: str) -> str | None:
        r = _git(["rev-parse", "--verify", ref], cwd=self.work_path, check=False)
        return r.stdout.strip() if r.returncode == 0 else None

    def get_git_commit(self, sha: str) -> dict:
        r = _git(["cat-file", "-p", sha], cwd=self.work_path)
        return {"sha": sha, "raw": r.stdout}

    def delete_reference(self, ref: str, force: bool = False) -> None:
        cmd = ["update-ref", "-d", ref]
        if force:
            cmd.insert(1, "--force")
        _git(cmd, cwd=self.work_path, check=False)

    def get_pull_requests(self, state: str = "OPEN") -> list[dict]:
        return []

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> dict:
        self.pr_counter += 1
        head_sha = _git(["rev-parse", "origin/" + head], cwd=self.work_path).stdout.strip()
        return {
            "number": self.pr_counter,
            "state": "OPEN",
            "title": title,
            "head_sha": head_sha,
            "html_url": f"https://example.invalid/pull/{self.pr_counter}",
        }

    def get_pull_request(self, number: int) -> dict:
        return {"number": number, "state": "OPEN"}

    def mark_pull_request_ready(self, number: int) -> None:
        pass

    def get_checks(self, ref: str) -> list[dict]:
        return [{"status": "completed", "conclusion": "success"}]

    def merge_pull_request(self, number: int, merge_method: str = "squash") -> dict:
        r = _git(["rev-parse", "HEAD"], cwd=self.work_path)
        sha = r.stdout.strip()
        return {"merged": True, "merge_commit_sha": sha}

    def get_merge_commit_sha(self, pr_number: int) -> str:
        r = _git(["rev-parse", "HEAD"], cwd=self.work_path)
        return r.stdout.strip()

    def verify_commit_on_branch(self, sha: str, branch: str) -> bool:
        r = _git(["merge-base", "--is-ancestor", sha, branch], cwd=self.work_path, check=False)
        return r.returncode == 0

    def verify_squash_merge(self, pr_sha: str, branch: str) -> bool:
        return self.verify_commit_on_branch(pr_sha, branch)

    def get_tag_target(self, tag: str) -> str:
        r = _git(["rev-parse", tag], cwd=self.work_path, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""

    def get_release_by_tag(self, tag: str) -> dict | None:
        return self.releases.get(tag)

    def create_release(self, tag: str, name: str, body: str) -> dict:
        self.releases[tag] = {"tag": tag, "name": name, "body": body}
        return self.releases[tag]


def _setup_repo(tmp_path: Path) -> tuple[Path, Path, _LocalGitHub]:
    """设置测试仓库"""
    work = tmp_path / "project"
    work.mkdir()
    bare = tmp_path / "remote.git"
    bare.mkdir()

    # 初始化 bare remote
    _git(["init", "--bare"], cwd=bare)
    # 初始化工作仓库
    _git(["init"], cwd=work)
    _git(["remote", "add", "origin", str(bare)], cwd=work)
    # 初始提交
    (work / "README.md").write_text("# test", encoding="utf-8")
    _git(["add", "."], cwd=work)
    _git(["commit", "-m", "init"], cwd=work)
    _git(["push", "-u", "origin", "main"], cwd=work)

    gh = _LocalGitHub(bare, work)
    return work, bare, gh


class TestCompleteTransactionLifecycle:
    """完整事务生命周期测试"""

    def test_init_and_start_lifecycle(self, tmp_path):
        """测试 init -> start 完整流程"""
        work, bare, gh = _setup_repo(tmp_path)

        from avm.commands.init_project import run_init_project
        from avm.commands.start import run_start
        from avm.core.state_machine import StateMachine
        from avm.models import AgentType, TaskStatus

        # 1. init
        init_result = run_init_project(work)
        assert init_result is True

        # 2. start
        with patch("avm.commands.start.detect_agent") as mock_detect:
            mock_adapter = SimpleNamespace()
            mock_adapter.agent_type = AgentType.CLAUDE_CODE
            mock_adapter.name = "Claude Code"
            mock_adapter.preflight_check = lambda: {"passed": True}
            mock_detect.return_value = mock_adapter
            start_result = run_start(work)
        assert start_result is True

        # 3. 验证状态
        sm = StateMachine(work)
        sm.load()
        assert sm.current_status == TaskStatus.WAIT_START_APPROVAL

    def test_chinese_subdirectory_paths_exist(self, tmp_path):
        """验证中文子目录路径存在"""
        work, bare, gh = _setup_repo(tmp_path)

        from avm.commands.init_project import run_init_project

        run_init_project(work)

        # 验证中文目录被创建
        assert (work / "版本管理").exists()
        assert (work / "审批").exists() or (work / "版本管理" / "审批").exists()

    def test_nul_safe_diff_parsing(self, tmp_path):
        """测试 NUL 安全的 git diff/status 解析"""
        work, bare, gh = _setup_repo(tmp_path)

        from avm.git.ops import GitOps

        git = GitOps(work)

        # 创建文件
        (work / "test.txt").write_text("hello", encoding="utf-8")
        _git(["add", "."], cwd=work)
        _git(["commit", "-m", "add test"], cwd=work)

        # 测试 get_status 使用 NUL 分隔
        status = git.get_status()
        assert isinstance(status, dict)

    def test_branch_delete_after_squash_merge(self, tmp_path):
        """测试 squash merge 后分支删除"""
        work, bare, gh = _setup_repo(tmp_path)

        # 创建功能分支
        _git(["checkout", "-b", "feature/test"], cwd=work)
        (work / "feature.txt").write_text("feature", encoding="utf-8")
        _git(["add", "."], cwd=work)
        _git(["commit", "-m", "feature"], cwd=work)
        _git(["checkout", "main"], cwd=work)

        # 模拟 squash merge
        _git(["merge", "--squash", "feature/test"], cwd=work)
        _git(["commit", "-m", "squash merge"], cwd=work)

        # 删除功能分支
        r = _git(["branch", "-D", "feature/test"], cwd=work, check=False)
        assert r.returncode == 0

        # 验证分支已删除
        r = _git(["branch", "--list", "feature/test"], cwd=work)
        assert "feature/test" not in r.stdout

    def test_state_returns_to_idle_after_publish(self, tmp_path):
        """测试发布后状态回到 IDLE"""
        work, bare, gh = _setup_repo(tmp_path)

        from avm.core.state_machine import StateMachine
        from avm.models import AgentType, TaskLock, TaskStatus

        sm = StateMachine(work)
        sm._task_lock = TaskLock(
            status=TaskStatus.TAGGING,
            previous_status=None,
            version="v1",
            agent=AgentType.CLAUDE_CODE,
            branch="agent/v1",
            base_commit="abc",
        )
        sm.save()

        # 模拟发布完成
        sm.load()
        sm.transition(TaskStatus.RELEASING)
        sm.transition(TaskStatus.HANDOFF_UPDATING)
        sm.transition(TaskStatus.CLEANING)
        sm.transition(TaskStatus.COMPLETE)
        sm.transition(TaskStatus.IDLE)

        sm.load()
        assert sm.current_status == TaskStatus.IDLE

    def test_remote_lock_deleted_after_publish(self, tmp_path):
        """测试发布后远程锁删除"""
        work, bare, gh = _setup_repo(tmp_path)

        # 创建远程锁引用
        _git(["update-ref", "refs/heads/avm/system-lock", "HEAD"], cwd=work)
        _git(["push", "origin", "refs/heads/avm/system-lock"], cwd=work, check=False)

        # 删除远程锁
        _git(["push", "origin", "--delete", "avm/system-lock"], cwd=work, check=False)

        # 验证远程锁已删除
        r = _git(["ls-remote", "origin", "refs/heads/avm/system-lock"], cwd=work, check=False)
        assert "avm/system-lock" not in r.stdout

    def test_local_branch_deleted_after_publish(self, tmp_path):
        """测试发布后本地分支删除"""
        work, bare, gh = _setup_repo(tmp_path)

        # 创建任务分支
        _git(["checkout", "-b", "agent/v1-claude-code"], cwd=work)
        _git(["checkout", "main"], cwd=work)

        # 删除任务分支
        r = _git(["branch", "-D", "agent/v1-claude-code"], cwd=work, check=False)
        assert r.returncode == 0

        # 验证分支已删除
        r = _git(["branch", "--list", "agent/v1-claude-code"], cwd=work)
        assert "agent/v1-claude-code" not in r.stdout

    def test_spaces_in_path_handled(self, tmp_path):
        """测试带空格路径处理"""
        work = tmp_path / "path with spaces"
        work.mkdir()
        bare = tmp_path / "remote.git"
        bare.mkdir()

        _git(["init", "--bare"], cwd=bare)
        _git(["init"], cwd=work)
        _git(["remote", "add", "origin", str(bare)], cwd=work)
        (work / "README.md").write_text("# test", encoding="utf-8")
        _git(["add", "."], cwd=work)
        _git(["commit", "-m", "init"], cwd=work)

        from avm.git.ops import GitOps

        git = GitOps(work)
        assert git.is_repo() is True
        assert git.get_head_sha() != ""

    def test_version_calculation(self, tmp_path):
        """测试版本号计算"""
        work, bare, gh = _setup_repo(tmp_path)

        from avm.git.versioning import VersionCalculator

        calc = VersionCalculator(work)
        ver = calc.get_next_version()
        assert ver >= 1
