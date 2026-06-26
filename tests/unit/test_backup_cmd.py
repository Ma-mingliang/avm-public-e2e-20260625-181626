"""AVM backup 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.backup import run_backup_list, run_backup_restore


@pytest.fixture
def project_dir(tmp_path):
    """创建项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


class TestRunBackupList:
    """backup list 命令测试"""

    @patch("avm.commands.backup.BackupManager")
    def test_backup_list_success(self, mock_cls, project_dir):
        """测试列出备份成功"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = [
            {"version": "v1", "created_at": "2024-01-01", "file_count": 5, "total_size": 1024},
        ]
        mock_cls.return_value = mock_mgr

        result = run_backup_list(project_dir)
        assert result is True

    @patch("avm.commands.backup.BackupManager")
    def test_backup_list_empty(self, mock_cls, project_dir):
        """测试空备份列表"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = []
        mock_cls.return_value = mock_mgr

        result = run_backup_list(project_dir)
        assert result is True

    @patch("avm.commands.backup.BackupManager")
    def test_backup_list_json(self, mock_cls, project_dir, capsys):
        """测试 JSON 输出"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = [
            {"version": "v1", "created_at": "2024-01-01", "file_count": 5, "total_size": 1024},
        ]
        mock_cls.return_value = mock_mgr

        result = run_backup_list(project_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data["backups"]) == 1

    @patch("avm.commands.backup.BackupManager")
    def test_backup_list_with_version(self, mock_cls, project_dir):
        """测试按版本过滤"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = []
        mock_cls.return_value = mock_mgr

        result = run_backup_list(project_dir, version="v1")
        assert result is True
        mock_mgr.list_backups.assert_called_with(version="v1")


class TestRunBackupRestore:
    """backup restore 命令测试"""

    @patch("avm.commands.backup.BackupManager")
    def test_backup_restore_success(self, mock_cls, project_dir):
        """测试恢复备份成功"""
        mock_mgr = MagicMock()
        mock_mgr.restore_backup.return_value = ["file1.txt", "file2.txt"]
        mock_cls.return_value = mock_mgr

        result = run_backup_restore(project_dir, "backup-001")
        assert result is True

    @patch("avm.commands.backup.BackupManager")
    def test_backup_restore_failure(self, mock_cls, project_dir):
        """测试恢复备份失败"""
        mock_mgr = MagicMock()
        mock_mgr.restore_backup.side_effect = Exception("备份不存在")
        mock_cls.return_value = mock_mgr

        result = run_backup_restore(project_dir, "backup-999")
        assert result is False

    @patch("avm.commands.backup.BackupManager")
    def test_backup_restore_json(self, mock_cls, project_dir, capsys):
        """测试 JSON 输出"""
        mock_mgr = MagicMock()
        mock_mgr.restore_backup.return_value = ["file1.txt"]
        mock_cls.return_value = mock_mgr

        result = run_backup_restore(project_dir, "backup-001", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert "file1.txt" in data["restored_files"]

    @patch("avm.commands.backup.BackupManager")
    def test_backup_restore_with_target(self, mock_cls, project_dir, tmp_path):
        """测试指定目标目录恢复"""
        mock_mgr = MagicMock()
        mock_mgr.restore_backup.return_value = ["file1.txt"]
        mock_cls.return_value = mock_mgr

        target = str(tmp_path / "restore_target")
        result = run_backup_restore(project_dir, "backup-001", target_dir=target)
        assert result is True
