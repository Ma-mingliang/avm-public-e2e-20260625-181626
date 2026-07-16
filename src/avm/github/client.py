"""AVM GitHub API 客户端"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from ..exceptions import GitHubError


class GitHubClient:
    """GitHub API 客户端

    使用 gh CLI 工具与 GitHub API 交互。
    """

    def __init__(
        self,
        repo_owner: str | None = None,
        repo_name: str | None = None,
        project_root: Path | None = None,
    ):
        """初始化客户端

        Args:
            repo_owner: 仓库所有者（可选，自动检测）
            repo_name: 仓库名称（可选，自动检测）
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.project_root = project_root.resolve() if project_root is not None else None
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
                cwd=self.project_root,
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
                cwd=self.project_root,
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

        try:
            result = self._run_gh(args)
            pr_info = self.get_pull_request(result.stdout.strip())
            return self._normalize_pull_request(pr_info)
        except GitHubError:
            return self._create_pull_request_rest(title, body, head, base, draft)

    def _create_pull_request_rest(self, title: str, body: str, head: str, base: str, draft: bool) -> dict[str, Any]:
        """使用已登录 gh 的 token 创建或复用开放 PR。"""
        if not self.repo_owner or not self.repo_name:
            raise GitHubError("GitHub REST 回退失败: 未检测到仓库信息")
        try:
            token = self._run_gh(["auth", "token"]).stdout.strip()
            if not token:
                raise GitHubError("未获取到 GitHub token")
            repo_path = f"repos/{self.repo_owner}/{self.repo_name}/pulls"
            head_query = parse.urlencode({"state": "open", "head": f"{self.repo_owner}:{head}"})
            existing = self._run_rest("GET", f"{repo_path}?{head_query}", token)
            if isinstance(existing, list):
                for pr in existing:
                    if pr.get("head", {}).get("ref") == head:
                        return self._normalize_pull_request(pr)
            created = self._run_rest(
                "POST",
                repo_path,
                token,
                {"title": title, "body": body, "head": head, "base": base, "draft": draft},
            )
            return self._normalize_pull_request(created)
        except GitHubError as exc:
            raise GitHubError(f"GitHub REST 回退失败: {exc}") from exc

    def _run_rest(self, method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> Any:
        """调用 GitHub REST API；调用方不得记录 token。"""
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        api_request = request.Request(
            f"https://api.github.com/{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(api_request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, OSError, json.JSONDecodeError) as exc:
            raise GitHubError(f"GitHub REST 请求失败: {exc}") from exc

    @staticmethod
    def _normalize_pull_request(pr: dict[str, Any]) -> dict[str, Any]:
        """将 gh GraphQL 和 REST 响应统一为 PR 命令使用的字段。"""
        number = pr.get("number")
        url = pr.get("html_url") or pr.get("url")
        if isinstance(number, bool) or not isinstance(number, int) or not isinstance(url, str) or not url:
            raise GitHubError("GitHub PR 响应缺少有效编号或 URL")
        normalized = dict(pr)
        normalized["number"] = number
        normalized["html_url"] = url
        return normalized

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
            合并结果，含 merge_commit_sha
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

        # 获取 merge commit SHA
        merge_sha = self._get_merge_commit_sha(pr_number)

        return {"merged": True, "method": merge_method, "merge_commit_sha": merge_sha}

    def _get_merge_commit_sha(self, pr_number: int) -> str:
        """获取 PR 的 merge commit SHA

        Args:
            pr_number: PR 编号

        Returns:
            merge commit SHA，获取失败返回空字符串
        """
        try:
            result = self._run_gh(
                ["pr", "view", str(pr_number), "--json", "mergeCommit"],
                check=False,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                merge_commit = data.get("mergeCommit")
                if merge_commit:
                    return merge_commit.get("oid", "")
        except Exception:
            pass
        return ""

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

    def get_commit_sha(self, sha: str) -> str | None:
        """验证远程 commit 是否存在

        Args:
            sha: commit SHA

        Returns:
            验证后的 SHA，不存在返回 None
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/commits/{sha}"]
        try:
            result = self._run_gh(args, check=False)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("sha")
            return None
        except Exception:
            return None

    def is_commit_on_branch(self, sha: str, branch: str) -> bool:
        """验证 commit 是目标分支当前提交的祖先。"""
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/compare/{sha}...{branch}"]
        try:
            result = self._run_gh(args, check=False)
            if result.returncode != 0:
                return False
            status = json.loads(result.stdout).get("status")
            return status in ("ahead", "identical")
        except Exception:
            return False

    def tag_exists(self, tag_name: str) -> bool:
        """检查远程 tag 是否存在

        Args:
            tag_name: tag 名称

        Returns:
            tag 是否存在
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/ref/tags/{tag_name}"]
        try:
            result = self._run_gh(args, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def get_tag_target(self, tag_name: str) -> str | None:
        """返回轻量或注释标签最终指向的 commit SHA。"""
        result = self._run_gh(
            ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/ref/tags/{tag_name}"],
            check=False,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        obj = data.get("object", {})
        sha = obj.get("sha")
        if obj.get("type") == "tag" and sha:
            tag_result = self._run_gh(
                ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/tags/{sha}"],
                check=False,
            )
            if tag_result.returncode != 0:
                return None
            return json.loads(tag_result.stdout).get("object", {}).get("sha")
        return sha

    def release_exists(self, tag_name: str) -> bool:
        """检查 release 是否存在

        Args:
            tag_name: tag 名称

        Returns:
            release 是否存在
        """
        args = ["release", "view", tag_name]
        try:
            result = self._run_gh(args, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def get_release(self, tag_name: str) -> dict[str, Any] | None:
        result = self._run_gh(
            ["release", "view", tag_name, "--json", "tagName,body,url"],
            check=False,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)

    def delete_branch(self, branch_name: str) -> bool:
        """删除远程分支

        Args:
            branch_name: 分支名称

        Returns:
            是否成功删除
        """
        args = ["api", f"repos/{self.repo_owner}/{self.repo_name}/git/refs/heads/{branch_name}", "-X", "DELETE"]
        try:
            result = self._run_gh(args, check=False)
            return result.returncode == 0
        except Exception:
            return False

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
