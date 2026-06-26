"""AVM 安装器测试"""

import json
from unittest.mock import patch

import pytest

from avm.update.installer import Installer


@pytest.fixture
def temp_install_dir(tmp_path):
    """创建临时安装目录"""
    return tmp_path / "install"


class TestInstaller:
    """安装器测试"""

    def test_get_current_version_not_installed(self, temp_install_dir):
        """测试获取未安装版本"""
        installer = Installer(temp_install_dir)
        assert installer.get_current_version() == "not installed"

    def test_get_current_version_installed(self, temp_install_dir):
        """测试获取已安装版本"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        assert installer.get_current_version() == "1.0.0"

    def test_save_version(self, temp_install_dir):
        """测试保存版本"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("2.0.0")

        version_file = temp_install_dir / "version.json"
        assert version_file.exists()

        data = json.loads(version_file.read_text(encoding="utf-8"))
        assert data["version"] == "2.0.0"

    def test_backup_current(self, temp_install_dir):
        """测试备份当前版本"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        backup_path = installer._backup_current()
        assert backup_path.exists()
        assert (backup_path / "version.json").exists()

    def test_list_backups_empty(self, temp_install_dir):
        """测试列出空备份"""
        installer = Installer(temp_install_dir)
        assert installer._list_backups() == []

    def test_list_backups(self, temp_install_dir):
        """测试列出备份"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()

        backups = installer._list_backups()
        assert len(backups) == 1
        assert backups[0]["name"].startswith("backup_1.0.0_")

    def test_rollback_no_backup(self, temp_install_dir):
        """测试无备份回滚"""
        installer = Installer(temp_install_dir)
        result = installer.rollback()

        assert not result["success"]
        assert any(s["status"] == "error" for s in result["steps"])

    def test_rollback_with_backup(self, temp_install_dir):
        """测试有备份回滚"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()

        result = installer.rollback()
        assert result["success"]

    def test_get_current_version_corrupted(self, temp_install_dir):
        """测试损坏的版本文件"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        (temp_install_dir / "version.json").write_text("not json", encoding="utf-8")

        assert installer.get_current_version() == "unknown"

    def test_install_already_installed(self, temp_install_dir):
        """测试已安装时触发更新"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        # 应该走 update 路径
        result = installer.install()
        assert result["action"] == "update"

    def test_backup_with_config_dir(self, temp_install_dir):
        """测试备份包含配置目录"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        config_dir = temp_install_dir / "config"
        config_dir.mkdir()
        (config_dir / "test.yaml").write_text("key: value", encoding="utf-8")

        backup_path = installer._backup_current()
        assert (backup_path / "config" / "test.yaml").exists()

    def test_rollback_restores_version(self, temp_install_dir):
        """测试回滚恢复版本文件"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()

        # 修改版本
        installer._save_version("2.0.0")
        assert installer.get_current_version() == "2.0.0"

        # 回滚
        result = installer.rollback()
        assert result["success"]

    def test_list_backups_multiple(self, temp_install_dir):
        """测试多个备份"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()
        installer._save_version("2.0.0")
        installer._backup_current()

        backups = installer._list_backups()
        assert len(backups) == 2

    def test_update_success(self, temp_install_dir):
        """测试更新成功流程"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        with patch.object(installer, "_install_from_pypi"):
            result = installer.update()

        assert result["success"]
        assert result["action"] == "update"
        assert any(s["step"] == "backup" for s in result["steps"])

    def test_update_with_source(self, temp_install_dir):
        """测试从源更新"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        with patch.object(installer, "_install_from_source") as mock_install:
            result = installer.update(source=temp_install_dir)

        assert result["success"]
        mock_install.assert_called_once()

    def test_update_failure_triggers_rollback(self, temp_install_dir):
        """测试更新失败触发回滚"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()

        with patch.object(installer, "_install_from_pypi", side_effect=RuntimeError("install failed")):
            result = installer.update()

        assert not result["success"]
        assert any(s["step"] == "rollback" for s in result["steps"])

    def test_update_failure_rollback_also_fails(self, temp_install_dir):
        """测试更新失败且回滚也失败"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")

        with (
            patch.object(installer, "_install_from_pypi", side_effect=RuntimeError("install failed")),
            patch.object(installer, "_backup_current", side_effect=RuntimeError("backup failed")),
        ):
            result = installer.update()

        assert not result["success"]

    def test_install_from_source(self, temp_install_dir):
        """测试从本地源安装"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)

        with patch("avm.update.installer.subprocess.run") as mock_run:
            mock_run.return_value = None
            installer._install_from_source(temp_install_dir)
            mock_run.assert_called_once()

    def test_install_from_pypi(self, temp_install_dir):
        """测试从 PyPI 安装"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)

        with patch("avm.update.installer.subprocess.run") as mock_run:
            mock_run.return_value = None
            installer._install_from_pypi()
            mock_run.assert_called_once()

    def test_install_success(self, temp_install_dir):
        """测试全新安装成功"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(installer, "_install_from_pypi"):
            result = installer.install()

        assert result["success"]
        assert result["action"] == "install"
        assert installer.get_current_version() == "1.0.0"

    def test_install_failure(self, temp_install_dir):
        """测试安装失败"""
        installer = Installer(temp_install_dir)

        with patch.object(installer, "_install_from_pypi", side_effect=RuntimeError("fail")):
            result = installer.install()

        assert not result["success"]
        assert any(s["status"] == "error" for s in result["steps"])

    def test_rollback_restore_error(self, temp_install_dir):
        """测试回滚恢复失败"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)
        installer._save_version("1.0.0")
        installer._backup_current()

        backups = installer._list_backups()
        with (
            patch("avm.update.installer.shutil.copy2", side_effect=RuntimeError("fail")),
            pytest.raises(RuntimeError),
        ):
            installer._restore_backup(backups[0])

    def test_backup_no_version_file(self, temp_install_dir):
        """测试无版本文件时备份"""
        installer = Installer(temp_install_dir)
        temp_install_dir.mkdir(parents=True)

        backup_path = installer._backup_current()
        assert backup_path.exists()
        assert not (backup_path / "version.json").exists()
