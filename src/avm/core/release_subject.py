"""不可变发布审批主体。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import PROJECT_CONFIG_DIR
from ..git.ops import GitOps
from ..models import TaskLock
from .hashing import compute_file_sha256


class ReleaseSubject(BaseModel):
    repository: str
    base_sha: str
    head_sha: str
    tree_sha: str
    changed_files: list[dict[str, str]] = Field(default_factory=list)
    config_hash: str = ""
    version: str
    target_branch: str
    pr_number: int | None = None

    @property
    def subject_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude_none=False),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_release_subject(project_root: Path, task_lock: TaskLock) -> ReleaseSubject:
    """从当前 Git HEAD 构造可复现的审批主体。"""
    git = GitOps(project_root)
    head_sha = git.get_head_sha()
    config_hash = ""
    for config_path in (
        project_root / PROJECT_CONFIG_DIR / "配置.yaml",
        project_root / ".claude" / "avm.json",
    ):
        if config_path.is_file():
            config_hash = compute_file_sha256(config_path)
            break
    return ReleaseSubject(
        repository=git.get_remote_url() or str(project_root.resolve()),
        base_sha=task_lock.base_commit,
        head_sha=head_sha,
        tree_sha=git.get_tree_sha(head_sha),
        changed_files=git.get_commit_manifest(task_lock.base_commit, head_sha),
        config_hash=config_hash,
        version=task_lock.version,
        target_branch=git.get_default_branch(),
        pr_number=task_lock.pr_number,
    )
