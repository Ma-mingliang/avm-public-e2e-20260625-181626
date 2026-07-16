"""不可变发布主体测试。"""

import subprocess

from avm.core.release_subject import build_release_subject
from avm.models import AgentType, TaskLock


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


def test_subject_changes_when_head_changes(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "payload.txt").write_text("safe", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    lock = TaskLock(version="v1", agent=AgentType.CODEX, base_commit=base)
    first = build_release_subject(tmp_path, lock)

    (tmp_path / "payload.txt").write_text("changed", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "payload")
    second = build_release_subject(tmp_path, lock)

    assert first.head_sha != second.head_sha
    assert first.tree_sha != second.tree_sha
    assert first.subject_hash != second.subject_hash
