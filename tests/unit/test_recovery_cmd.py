"""AVM recovery 命令测试"""

import json
from pathlib import Path

import pytest

from avm.commands.recovery import run_abandon, run_recover, run_resume
from avm.core.io import atomic_write_json
from avm.core.paths import get_task_lock_path


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


def _create_lock(project_dir: Path, status: str) -> None:
    """创建任务锁"""
    lock_path = get_task_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        lock_path,
        {
            "schema_version": 1,
            "status": status,
            "version": "v1",
            "agent": "claude-code",
            "branch": "agent/v1",
            "base_commit": "abc123",
            "started_at": "2024-01-01T00:00:00+00:00",
            "expected_files": [],
        },
    )


class TestRunResume:
    """resume 命令测试"""

    def test_resume_from_interrupted(self, project_dir):
        """测试从中断状态恢复"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_resume(project_dir)
        assert result is True

        # 验证状态已恢复到 RESERVED
        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "RESERVED"

    def test_resume_from_auth_blocked(self, project_dir):
        """测试从认证阻塞恢复"""
        _create_lock(project_dir, "AUTH_BLOCKED")

        result = run_resume(project_dir)
        assert result is True

        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "PREFLIGHT"

    def test_resume_from_network_blocked(self, project_dir):
        """测试从网络阻塞恢复"""
        _create_lock(project_dir, "NETWORK_BLOCKED")

        result = run_resume(project_dir)
        assert result is True

        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "PREFLIGHT"

    def test_resume_not_error_state(self, project_dir):
        """测试非错误状态不能恢复"""
        _create_lock(project_dir, "RESERVED")

        result = run_resume(project_dir)
        assert result is False

    def test_resume_json(self, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_resume(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["from_status"] == "INTERRUPTED"


class TestRunAbandon:
    """abandon 命令测试"""

    def test_abandon_from_reserved(self, project_dir):
        """测试从 RESERVED 不能废弃（非错误状态）"""
        _create_lock(project_dir, "RESERVED")

        result = run_abandon(project_dir)
        assert result is False

    def test_abandon_from_modifying(self, project_dir):
        """测试从 MODIFYING 不能废弃（非错误状态）"""
        _create_lock(project_dir, "MODIFYING")

        result = run_abandon(project_dir)
        assert result is False

    def test_abandon_from_interrupted(self, project_dir):
        """测试从 INTERRUPTED 废弃"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_abandon(project_dir)
        assert result is True

    def test_abandon_when_idle(self, project_dir):
        """测试空闲时废弃"""
        _create_lock(project_dir, "IDLE")

        result = run_abandon(project_dir)
        assert result is False

    def test_abandon_when_complete(self, project_dir):
        """测试完成后废弃"""
        _create_lock(project_dir, "COMPLETE")

        result = run_abandon(project_dir)
        assert result is False

    def test_abandon_json(self, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_abandon(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True


class TestRunRecover:
    """recover 命令测试"""

    def test_recover_publish_incomplete(self, project_dir):
        """测试从发布不完整恢复"""
        _create_lock(project_dir, "PUBLISH_INCOMPLETE")

        result = run_recover(project_dir)
        assert result is True

        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "TAGGING"

    def test_recover_approval_invalidated(self, project_dir):
        """测试从审批失效恢复"""
        _create_lock(project_dir, "APPROVAL_INVALIDATED")

        result = run_recover(project_dir)
        assert result is True

        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "WAIT_FINAL_APPROVAL"

    def test_recover_interrupted_delegates_to_resume(self, project_dir):
        """测试 INTERRUPTED 委托给 resume"""
        _create_lock(project_dir, "INTERRUPTED")

        result = run_recover(project_dir)
        assert result is True

        lock_path = get_task_lock_path(project_dir)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["status"] == "RESERVED"

    def test_recover_normal_state(self, project_dir):
        """测试正常状态不能恢复"""
        _create_lock(project_dir, "RESERVED")

        result = run_recover(project_dir)
        assert result is False

    def test_recover_json(self, project_dir, capsys):
        """测试 JSON 输出"""
        _create_lock(project_dir, "PUBLISH_INCOMPLETE")

        result = run_recover(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
