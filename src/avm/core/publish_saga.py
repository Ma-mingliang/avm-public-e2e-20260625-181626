"""幂等发布事实对账。"""

from __future__ import annotations

import re

from ..exceptions import PublishConflictError, PublishError
from ..git.ops import GitOps
from ..github.client import GitHubClient


def extract_manifest_hash(body: str) -> str:
    match = re.search(r'"manifest_hash"\s*:\s*"([0-9a-f]{64})"', body)
    return match.group(1) if match else ""


class PublishSaga:
    def __init__(self, github: GitHubClient, git: GitOps):
        self.github = github
        self.git = git

    def ensure_tag(self, tag: str, merge_sha: str) -> None:
        observed = self.github.get_tag_target(tag)
        if observed is not None and not isinstance(observed, str):
            observed = None
        if observed:
            if observed != merge_sha:
                raise PublishConflictError(f"标签 {tag} 指向不同提交")
            return
        if not self.git.create_annotated_tag(tag, f"Release {tag}", merge_sha):
            # 本地标签可能来自上次部分成功，远端仍应继续对账。
            local = self.git._run_git(["rev-list", "-n", "1", tag], check=False)
            if local.returncode != 0 or local.stdout.strip() != merge_sha:
                raise PublishError("创建本地标签失败")
        if not self.git.push_tag(tag):
            observed = self.github.get_tag_target(tag)
            if observed != merge_sha:
                raise PublishError("推送标签失败且远端事实不一致")

    def ensure_release(self, tag: str, title: str, body: str, manifest_hash: str) -> str:
        existing = self.github.get_release(tag)
        if existing is not None and not isinstance(existing, dict):
            existing = None
        if existing:
            if extract_manifest_hash(str(existing.get("body", ""))) != manifest_hash:
                raise PublishConflictError("现有 Release manifest 冲突")
            return str(existing.get("url", ""))
        created = self.github.create_release(
            tag_name=tag,
            title=title,
            body=body,
            draft=False,
            prerelease=False,
        )
        if not isinstance(created, dict):
            raise PublishError("GitHub Release 响应格式无效")
        return str(created.get("url", created.get("html_url", "")))
