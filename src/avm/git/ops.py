"""AVM Git 操作封装"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ..exceptions import GitError


class GitOps:
    """Git 操作封装

    所有 Git 命令通过参数数组调用，不拼接字符串。
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def _run_git(self, args: list[str], check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        """运行 Git 命令

        Args:
            args: Git 命令参数列表
            check: 是否检查返回码
            timeout: 超时秒数

        Returns:
            命令执行结果
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
            )
            if check and result.returncode != 0:
                raise GitError(f"Git 命令失败: {' '.join(cmd)}\n{result.stderr}")
            return result
        except subprocess.TimeoutExpired as e:
            raise GitError(f"Git 命令超时: {' '.join(cmd)}") from e
        except FileNotFoundError as e:
            raise GitError("Git 未安装或不在 PATH 中") from e

    def detect_repo(self) -> bool:
        """检测是否为 Git 仓库"""
        try:
            result = self._run_git(["rev-parse", "--git-dir"], check=False)
            return result.returncode == 0
        except GitError:
            return False

    def is_repo(self) -> bool:
        """检测是否为 Git 仓库（detect_repo 的别名）"""
        return self.detect_repo()

    def get_current_branch(self) -> str:
        """获取当前分支名

        支持 unborn branch（空仓库无提交时使用 symbolic-ref）。
        """
        # 先尝试 rev-parse（有提交时正常工作）
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != "HEAD":
                return branch
        # fallback: symbolic-ref 支持 unborn branch
        result = self._run_git(["symbolic-ref", "--short", "HEAD"], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        raise GitError("无法获取当前分支名")

    def get_head_sha(self) -> str:
        """获取 HEAD 提交 SHA"""
        result = self._run_git(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def get_remote_url(self, remote: str = "origin") -> str | None:
        """获取远程仓库 URL"""
        try:
            result = self._run_git(["remote", "get-url", remote], check=False)
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except GitError:
            return None

    def get_default_branch(self) -> str:
        """获取默认分支名

        优先检查 main，然后 master。
        """
        # 检查远程默认分支
        result = self._run_git(["symbolic-ref", "refs/remotes/origin/HEAD", "--short"], check=False)
        if result.returncode == 0:
            branch = result.stdout.strip().replace("origin/", "")
            return branch

        # 检查本地分支
        for branch in ["main", "master"]:
            result = self._run_git(["rev-parse", "--verify", branch], check=False)
            if result.returncode == 0:
                return branch

        # 返回当前分支
        return self.get_current_branch()

    def get_max_version_tag(self) -> int:
        """获取最大版本标签号

        只匹配 v1, v2, v3... 格式，忽略 v1.0.0 等语义化版本。
        """
        result = self._run_git(["tag", "-l", "v[0-9]*"], check=False)
        if result.returncode != 0:
            return 0

        max_version = 0
        for tag in result.stdout.strip().split("\n"):
            tag = tag.strip()
            if not tag:
                continue
            # 严格匹配 v + 纯数字
            match = re.match(r"^v(\d+)$", tag)
            if match:
                version_num = int(match.group(1))
                max_version = max(max_version, version_num)

        return max_version

    def get_max_version_tag_remote(self) -> int | None:
        """从远程获取最大版本标签号

        Returns:
            最大版本号，无远程或无标签返回 0，查询失败返回 None
        """
        # 检查是否有远程仓库
        remote_url = self.get_remote_url("origin")
        if remote_url is None:
            return 0

        result = self._run_git(["ls-remote", "--tags", "origin"], check=False)
        if result.returncode != 0:
            return None

        max_version = 0
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            ref = parts[1]
            # 匹配 refs/tags/vN
            match = re.match(r"^refs/tags/v(\d+)$", ref)
            if match:
                version_num = int(match.group(1))
                max_version = max(max_version, version_num)

        return max_version

    def get_max_version_branch(self) -> int | None:
        """从远程分支名获取最大版本号

        匹配 agent/vN-* 格式的分支。

        Returns:
            最大版本号，无远程或无分支返回 0，查询失败返回 None
        """
        # 检查是否有远程仓库
        remote_url = self.get_remote_url("origin")
        if remote_url is None:
            return 0

        result = self._run_git(["branch", "-r", "--list", "origin/agent/v*"], check=False)
        if result.returncode != 0:
            return None

        max_version = 0
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 匹配 origin/agent/vN-slug
            match = re.match(r"origin/agent/v(\d+)-", line)
            if match:
                version_num = int(match.group(1))
                max_version = max(max_version, version_num)

        return max_version

    def create_branch(self, branch_name: str, from_ref: str = "HEAD") -> bool:
        """创建分支"""
        try:
            self._run_git(["branch", branch_name, from_ref])
            return True
        except GitError:
            return False

    def delete_branch(self, branch_name: str, remote: bool = False) -> bool:
        """删除分支"""
        try:
            if remote:
                self._run_git(["push", "origin", "--delete", branch_name], check=False)
            else:
                self._run_git(["branch", "-d", branch_name])
            return True
        except GitError:
            return False

    def checkout(self, branch_name: str) -> bool:
        """切换分支"""
        try:
            self._run_git(["checkout", branch_name])
            return True
        except GitError:
            return False

    def stage_files(self, files: list[str]) -> bool:
        """暂存文件"""
        if not files:
            return True
        try:
            self._run_git(["add"] + files)
            return True
        except GitError:
            return False

    def commit(self, message: str, allow_empty: bool = False) -> str:
        """提交

        Returns:
            提交 SHA
        """
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        self._run_git(args)
        return self.get_head_sha()

    def create_annotated_tag(self, tag_name: str, message: str, commit_sha: str = "HEAD") -> bool:
        """创建注释标签"""
        try:
            self._run_git(["tag", "-a", tag_name, "-m", message, commit_sha])
            return True
        except GitError:
            return False

    def push(self, remote: str = "origin", refspec: str = "") -> bool:
        """推送"""
        args = ["push", remote]
        if refspec:
            args.append(refspec)
        try:
            self._run_git(args, timeout=120)
            return True
        except GitError:
            return False

    def push_tag(self, tag_name: str, remote: str = "origin") -> bool:
        """推送标签"""
        return self.push(remote, f"refs/tags/{tag_name}")

    def get_status(self) -> dict[str, Any]:
        """获取仓库状态"""
        result = self._run_git(["status", "--porcelain=v2", "--branch"])

        # 解析状态
        status = {
            "branch": "",
            "ahead": 0,
            "behind": 0,
            "modified": [],
            "added": [],
            "deleted": [],
            "untracked": [],
        }

        for line in result.stdout.strip().split("\n"):
            if line.startswith("# branch.head"):
                status["branch"] = line.split("\t")[1] if "\t" in line else ""
            elif line.startswith("# branch.ab"):
                # 解析 ahead/behind
                parts = line.split("\t")[1] if "\t" in line else ""
                for part in parts.split():
                    if part.startswith("+"):
                        status["ahead"] = int(part[1:])
                    elif part.startswith("-"):
                        status["behind"] = int(part[1:])
            elif line.startswith("1 ") or line.startswith("2 "):
                # 修改的文件
                parts = line.split()
                if len(parts) >= 9:
                    status["modified"].append(parts[8])
            elif line.startswith("? "):
                # 未跟踪的文件
                parts = line.split()
                if len(parts) >= 2:
                    status["untracked"].append(parts[1])

        return status

    def get_diff_summary(self, staged: bool = False) -> list[dict[str, str]]:
        """获取差异摘要"""
        args = ["diff", "--name-status"]
        if staged:
            args.append("--staged")

        result = self._run_git(args, check=False)
        if result.returncode != 0:
            return []

        files = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                files.append(
                    {
                        "status": parts[0],
                        "path": parts[1],
                    }
                )

        return files

    def install_hooks(self) -> bool:
        """安装 Git Hooks"""
        hooks_dir = self.repo_root / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # pre-commit hook
        pre_commit = hooks_dir / "pre-commit"
        pre_commit.write_text(
            "#!/bin/sh\n# AVM pre-commit hook\navm hook pre-commit\n",
            encoding="utf-8",
        )
        pre_commit.chmod(0o755)

        # commit-msg hook
        commit_msg = hooks_dir / "commit-msg"
        commit_msg.write_text(
            '#!/bin/sh\n# AVM commit-msg hook\navm hook commit-msg "$1"\n',
            encoding="utf-8",
        )
        commit_msg.chmod(0o755)

        # pre-push hook
        pre_push = hooks_dir / "pre-push"
        pre_push.write_text(
            "#!/bin/sh\n# AVM pre-push hook\navm hook pre-push\n",
            encoding="utf-8",
        )
        pre_push.chmod(0o755)

        return True

    def check_hooks(self) -> dict[str, bool]:
        """检查 Hooks 状态"""
        hooks_dir = self.repo_root / ".git" / "hooks"

        hooks = {
            "pre-commit": False,
            "commit-msg": False,
            "pre-push": False,
        }

        for hook_name in hooks:
            hook_file = hooks_dir / hook_name
            if hook_file.exists():
                content = hook_file.read_text(encoding="utf-8")
                hooks[hook_name] = "avm" in content

        return hooks

    def get_uncommitted_changes(self) -> dict[str, Any]:
        """获取未提交修改"""
        status = self.get_status()

        # 检查是否有未提交修改
        has_changes = bool(status["modified"] or status["added"] or status["deleted"] or status["untracked"])

        return {
            "has_changes": has_changes,
            "status": status,
            "diff": self.get_diff_summary(staged=True),
        }
