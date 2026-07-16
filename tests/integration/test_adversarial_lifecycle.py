"""跨组件对抗性完整性回归。"""

import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from avm.commands.approve import _compute_content_hash
from avm.commands.hook import run_hook_pre_commit
from avm.core.backup import BackupManager
from avm.core.manifest import generate_release_manifest
from avm.core.state_machine import StateMachine
from avm.core.task_store import TaskStore
from avm.exceptions import AVMError, StateConflictError
from avm.models import AgentType, TaskLock, TaskStatus


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "payload.txt").write_text("safe", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def test_corrupt_state_never_becomes_idle(tmp_path):
    path = TaskStore(tmp_path).path
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(AVMError, match="任务状态损坏"):
        StateMachine(tmp_path).load()


def test_approval_subject_changes_after_committed_payload(git_repo):
    base = _git(git_repo, "rev-parse", "HEAD")
    lock = TaskLock(version="v1", base_commit=base, agent=AgentType.CODEX)
    approved = _compute_content_hash(git_repo, lock)
    (git_repo / "payload.txt").write_text("malicious", encoding="utf-8")
    _git(git_repo, "add", ".")
    _git(git_repo, "commit", "-m", "payload")
    assert _compute_content_hash(git_repo, lock) != approved


def test_staged_secret_cannot_be_hidden_by_worktree(git_repo):
    path = git_repo / "payload.txt"
    path.write_text("api_key=ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", encoding="utf-8")
    _git(git_repo, "add", "payload.txt")
    path.write_text("safe worktree", encoding="utf-8")
    assert run_hook_pre_commit(git_repo) is False


def test_concurrent_task_acquire_has_one_winner(tmp_path):
    def acquire(index):
        try:
            TaskStore(tmp_path).acquire(TaskLock(status=TaskStatus.RESERVED, version=f"v{index}"))
            return True
        except StateConflictError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, range(8)))
    assert results.count(True) == 1


def test_single_file_directory_round_trip(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "only.txt").write_text("payload", encoding="utf-8")
    manager = BackupManager(tmp_path)
    record = manager.create_backup(source, "v1")
    target = manager.restore_backup(record["backup_name"], tmp_path / "restored")
    assert target.is_dir()
    assert (target / "only.txt").read_text(encoding="utf-8") == "payload"


def test_release_url_does_not_change_manifest_hash():
    lock = TaskLock(version="v1", base_commit="base", agent=AgentType.CODEX)
    before = generate_release_manifest(lock, "merge", release_url="")
    after = generate_release_manifest(lock, "merge", release_url="https://example.invalid/v1")
    # published_at differs, so compare by freezing it to the published value.
    after["published_at"] = before["published_at"]
    from avm.core.manifest import _compute_manifest_hash

    after["manifest_hash"] = _compute_manifest_hash(after)
    assert before["manifest_hash"] == after["manifest_hash"]
