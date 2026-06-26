"""AVM install 命令测试"""

import json
from unittest.mock import MagicMock, patch

import pytest

from avm.commands.install import run_install
from avm.commands.update import run_rollback, run_update, run_update_check


@pytest.fixture
def install_dir(tmp_path):
    """创建临时安装目录"""
    return tmp_path / "avm_install"


class TestRunInstall:
    """install 命令测试"""

    @patch("avm.commands.install.Installer")
    def test_install_success(self, mock_installer_cls, install_dir):
        """测试安装成功"""
        mock_installer = MagicMock()
        mock_installer.install.return_value = {
            "success": True,
            "action": "install",
            "steps": [{"step": "install", "status": "ok", "message": "安装成功"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_install(install_dir)
        assert result is True

    @patch("avm.commands.install.Installer")
    def test_install_failure(self, mock_installer_cls, install_dir):
        """测试安装失败"""
        mock_installer = MagicMock()
        mock_installer.install.return_value = {
            "success": False,
            "action": "install",
            "steps": [{"step": "install", "status": "error", "message": "安装失败"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_install(install_dir)
        assert result is False

    @patch("avm.commands.install.Installer")
    def test_install_json_output(self, mock_installer_cls, install_dir, capsys):
        """测试 JSON 输出"""
        mock_installer = MagicMock()
        mock_installer.install.return_value = {
            "success": True,
            "action": "install",
            "steps": [],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_install(install_dir, json_output=True)
        assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True


class TestRunUpdateCheck:
    """update_check 命令测试"""

    @patch("avm.commands.update.Installer")
    def test_update_check_not_installed(self, mock_installer_cls):
        """测试未安装时检查更新"""
        mock_installer = MagicMock()
        mock_installer.get_current_version.return_value = "not installed"
        mock_installer_cls.return_value = mock_installer

        result = run_update_check()
        assert result is False

    @patch("avm.commands.update.Installer")
    def test_update_check_json(self, mock_installer_cls, capsys):
        """测试 JSON 输出"""
        mock_installer = MagicMock()
        mock_installer.get_current_version.return_value = "0.9.0"
        mock_installer_cls.return_value = mock_installer

        run_update_check(json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "current_version" in data


class TestRunUpdate:
    """update 命令测试"""

    @patch("avm.commands.update.Installer")
    def test_update_success(self, mock_installer_cls):
        """测试更新成功"""
        mock_installer = MagicMock()
        mock_installer.update.return_value = {
            "success": True,
            "action": "update",
            "steps": [{"step": "update", "status": "ok", "message": "更新成功"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_update()
        assert result is True

    @patch("avm.commands.update.Installer")
    def test_update_failure(self, mock_installer_cls):
        """测试更新失败"""
        mock_installer = MagicMock()
        mock_installer.update.return_value = {
            "success": False,
            "action": "update",
            "steps": [{"step": "update", "status": "error", "message": "更新失败"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_update()
        assert result is False


class TestRunRollback:
    """rollback 命令测试"""

    @patch("avm.commands.update.Installer")
    def test_rollback_success(self, mock_installer_cls):
        """测试回滚成功"""
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = {
            "success": True,
            "action": "rollback",
            "steps": [{"step": "restore", "status": "ok", "message": "已恢复"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_rollback()
        assert result is True

    @patch("avm.commands.update.Installer")
    def test_rollback_failure(self, mock_installer_cls):
        """测试回滚失败"""
        mock_installer = MagicMock()
        mock_installer.rollback.return_value = {
            "success": False,
            "action": "rollback",
            "steps": [{"step": "find_backup", "status": "error", "message": "无备份"}],
        }
        mock_installer_cls.return_value = mock_installer

        result = run_rollback()
        assert result is False
