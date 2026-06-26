"""AVM config 命令测试"""

import json
from unittest.mock import MagicMock, patch

from avm.commands.config import run_config_backup_list, run_config_restore


class TestRunConfigBackupList:
    """config-backup-list 命令测试"""

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_backup_list_success(self, mock_get_mgr):
        """测试列出配置备份成功"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = [
            {
                "backup_name": "config-001",
                "version": "v1",
                "timestamp": "20240101_000000",
                "files": [{"path": "config.yaml"}],
            },
        ]
        mock_get_mgr.return_value = mock_mgr

        result = run_config_backup_list()
        assert result is True

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_backup_list_empty(self, mock_get_mgr):
        """测试空备份列表"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = []
        mock_get_mgr.return_value = mock_mgr

        result = run_config_backup_list()
        assert result is True

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_backup_list_json(self, mock_get_mgr, capsys):
        """测试 JSON 输出"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.return_value = [
            {"backup_name": "config-001", "version": "v1", "timestamp": "20240101_000000", "files": []},
        ]
        mock_get_mgr.return_value = mock_mgr

        result = run_config_backup_list(json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert len(data["backups"]) == 1

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_backup_list_error(self, mock_get_mgr):
        """测试列出备份失败"""
        mock_mgr = MagicMock()
        mock_mgr.list_backups.side_effect = Exception("IO error")
        mock_get_mgr.return_value = mock_mgr

        result = run_config_backup_list()
        assert result is False


class TestRunConfigRestore:
    """config-restore 命令测试"""

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_restore_success(self, mock_get_mgr):
        """测试恢复配置成功"""
        mock_mgr = MagicMock()
        mock_get_mgr.return_value = mock_mgr

        result = run_config_restore("config-001")
        assert result is True
        mock_mgr.restore_backup.assert_called_once_with("config-001")

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_restore_failure(self, mock_get_mgr):
        """测试恢复配置失败"""
        mock_mgr = MagicMock()
        mock_mgr.restore_backup.side_effect = Exception("备份不存在")
        mock_get_mgr.return_value = mock_mgr

        result = run_config_restore("config-999")
        assert result is False

    def test_restore_empty_id(self):
        """测试空备份 ID"""
        result = run_config_restore("")
        assert result is False

    @patch("avm.commands.config._get_global_backup_mgr")
    def test_restore_json(self, mock_get_mgr, capsys):
        """测试 JSON 输出"""
        mock_mgr = MagicMock()
        mock_get_mgr.return_value = mock_mgr

        result = run_config_restore("config-001", json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
