"""AVM GitHub API 客户端"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from ..exceptions import GitHubError


class GitHubClient:
    """GitHub API 客户端

    使用 gh CLI 工具与 GitHub API 交互。
    """

    def __init__(self, repo_owner: str | None = None, repo_name: str | None = None):
        """初始化客户端

        Args:
            repo_owner: 仓库所有者（可选，自动检测）
            repo_name: 仓库名称（可选，自动检测）
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self._detect_repo()

    def _detect_repo(self) -> None:
        """检测当前仓库信息"""
        if self.repo_owner and self.repo_name:
            return

        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "owner,name"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                self.repo_owner = self.repo_owner or data.get("owner", {}).get("login")
                self.repo_name = self.repo_name or data.get("name")
        except Exception:
            pass

    def _run_gh(self, args: list[str], check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        """运行 gh 命令

        Args:
            args: 命令参数
            check: 是否检查返回码
            timeout: 超时时间（秒）

        Returns:
            命令结果
        """
        cmd = ["gh"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if check and result.returncode != 0:
                raise GitHubError(f"gh 命令失败: {result.stderr}")
            return result
        except subprocess.TimeoutExpired as e:
            raise GitHubError(f"gh 命令超时: {' '.join(cmd)}") from e
        except FileNotFoundError as e:
            raise GitHubError("gh CLI 未安装或不在 PATH 中") from e

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> dict[str, Any]:
        """创建 Pull Request

        Args:
            title: PR 标题
            body: PR 描述
            head: 源分支
            base: 目标分支
            draft: 是否为草稿

        Returns:
            PR 信息
        """
        args = [
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--head",
            head,
            "--base",
            base,
        ]
        if draft:
            args.append("--draft")

        result = self._run_gh(args)

        # 解析 PR URL
        pr_url = result.stdout.strip()

        # 获取 PR 详情
        pr_info = self.get_pull_request(pr_url)
        return pr_info

    def get_pull_request(self, pr_url: str) -> dict[str, Any]:
        """获取 PR 信息

        Args:
            pr_url: PR URL 或编号

        Returns:
            PR 信息
        """
        args = ["pr", "view", pr_url, "--json", "number,title,state,url,headRefName,baseRefName"]
        result = self._run_gh(args)
        return json.loads(result.stdout)

    def merge_pull_request(
        self,
        pr_number: int,
        merge_method: str = "squash",
        delete_branch: bool = True,
    ) -> dict[str, Any]:
        """合并 Pull Request

        Args:
            pr_number: PR 编号
            merge_method: 合并方法（squash, merge, rebase）
            delete_branch: 是否删除源分支

        Returns:
            合并结果
        """
        args = [
            "pr",
            "merge",
            str(pr_number),
            f"--{merge_method}",
        ]
        if delete_branch:
            args.append("--delete-branch")

        self._run_gh(args)
        return {"merged": True, "method": merge_method}

    def create_tag(self, tag_name: str, message: str, target: str = "HEAD") -> dict[str, Any]:
        """创建标签

        Args:
            tag_name: 标签名称
            message: 标签消息
            target: 目标提交

        Returns:
            标签信息
        """
        # 本地创建标签
        args = ["tag", "-a", tag_name, "-m", message, target]
        self._run_gh(args)

        # 推送标签
        push_args = ["push", "origin", tag_name]
        self._run_gh(push_args)

        return {"tag": tag_name, "message": message}

    def create_release(
        self,
        tag_name: str,
        title: str,
        body: str,
        draft: bool = False,
        prerelease: bool = False,
    ) -> dict[str, Any]:
        """创建发布

        Args:
            tag_name: 标签名称
            title: 发布标题
            body: 发布描述
            draft: 是否为草稿
            prerelease: 是否为预发布

        Returns:
            发布信息
        """
        args = [
            "release",
            "create",
            tag_name,
            "--title",
            title,
            "--notes",
            body,
        ]
        if draft:
            args.append("--draft")
        if prerelease:
            args.append("--prerelease")

        result = self._run_gh(args)

        return {
            "tag": tag_name,
            "title": title,
            "url": result.stdout.strip(),
        }

    def create_reference(self, ref: str, sha: str) -> bool:
        """创建引用（用于远程锁）

        Args:
            ref: 引用路径（如 refs/heads/avm/system-lock）
            sha: 提交 SHA

        Returns:
            是否成功创建
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/refs", "-f", f"ref={ref}", "-f", f"sha={sha}"]
        try:
            result = self._run_gh(args, check=False)
            if result.returncode == 0:
                return True
            # 422 表示引用已存在
            if "422" in result.stderr or "Reference already exists" in result.stderr:
                return False
            raise GitHubError(f"创建引用失败: {result.stderr}")
        except Exception as e:
            if isinstance(e, GitHubError):
                raise
            raise GitHubError(f"创建引用失败: {e}") from e

    def delete_reference(self, ref: str) -> bool:
        """删除引用

        Args:
            ref: 引用路径

        Returns:
            是否成功删除
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/refs/{ref}", "-X", "DELETE"]
        try:
            result = self._run_gh(args, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def get_reference(self, ref: str) -> str | None:
        """获取引用

        Args:
            ref: 引用路径

        Returns:
            引用的 SHA，如果不存在返回 None
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/ref/{ref}"]
        try:
            result = self._run_gh(args, check=False)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("object", {}).get("sha")
            return None
        except Exception:
            return None

    def list_workflow_runs(self, workflow: str, branch: str | None = None) -> list[dict[str, Any]]:
        """列出工作流运行

        Args:
            workflow: 工作流文件名
            branch: 分支过滤

        Returns:
            运行列表
        """
        args = ["run", "list", "--workflow", workflow, "--json", "status,conclusion,headBranch,createdAt"]
        if branch:
            args.extend(["--branch", branch])

        result = self._run_gh(args)
        return json.loads(result.stdout)

    def wait_workflow_run(self, run_id: int, timeout: int = 600) -> dict[str, Any]:
        """等待工作流完成

        Args:
            run_id: 运行 ID
            timeout: 超时时间（秒）

        Returns:
            运行结果
        """
        args = ["run", "watch", str(run_id), "--exit-status"]
        try:
            result = self._run_gh(args, timeout=timeout)
            return {"completed": True, "success": result.returncode == 0}
        except GitHubError:
            return {"completed": False, "success": False}

    def get_repo_info(self) -> dict[str, Any]:
        """获取仓库信息

        Returns:
            仓库信息
        """
        args = ["repo", "view", "--json", "name,owner,description,defaultBranchRef,isPrivate"]
        result = self._run_gh(args)
        return json.loads(result.stdout)
