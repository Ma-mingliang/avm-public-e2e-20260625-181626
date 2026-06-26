"""AVM 文档备份测试"""

from pathlib import Path

import pytest

from avm.core.backup import BackupManager
from avm.exceptions import BackupError


@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    version_dir = tmp_path / "版本管理"
    version_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_file(tmp_path):
    """创建示例文件"""
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("这是测试内容", encoding="utf-8")
    return file_path


@pytest.fixture
def sample_dir(tmp_path):
    """创建示例目录"""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    (dir_path / "file1.txt").write_text("文件1", encoding="utf-8")
    (dir_path / "file2.txt").write_text("文件2", encoding="utf-8")
    sub = dir_path / "subdir"
    sub.mkdir()
    (sub / "file3.txt").write_text("文件3", encoding="utf-8")
    return dir_path


class TestBackupManager:
    """备份管理器测试"""

    def test_create_backup_file(self, temp_project, sample_file):
        """测试创建文件备份"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(
            source_path=sample_file,
            version="v1",
            description="测试文件备份",
        )

        assert record["version"] == "v1"
        assert len(record["files"]) == 1
        assert record["files"][0]["sha256"] is not None

    def test_create_backup_directory(self, temp_project, sample_dir):
        """测试创建目录备份"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(
            source_path=sample_dir,
            version="v2",
            description="测试目录备份",
        )

        assert record["version"] == "v2"
        assert len(record["files"]) == 3  # file1.txt, file2.txt, subdir/file3.txt

    def test_list_backups(self, temp_project, sample_file):
        """测试列出备份"""
        manager = BackupManager(temp_project)

        manager.create_backup(sample_file, "v1", "备份1")
        manager.create_backup(sample_file, "v2", "备份2")

        backups = manager.list_backups()
        assert len(backups) == 2

    def test_list_backups_filtered(self, temp_project, sample_file):
        """测试按版本过滤备份"""
        manager = BackupManager(temp_project)

        manager.create_backup(sample_file, "v1", "备份1")
        manager.create_backup(sample_file, "v2", "备份2")
        manager.create_backup(sample_file, "v1", "备份3")

        backups = manager.list_backups(version="v1")
        assert len(backups) == 2

    def test_restore_backup_file(self, temp_project, sample_file):
        """测试恢复文件备份"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(sample_file, "v1")
        backup_name = record["backup_name"]

        # 删除原文件
        sample_file.unlink()
        assert not sample_file.exists()

        # 恢复
        restored = manager.restore_backup(backup_name)
        assert restored.exists()
        assert restored.read_text(encoding="utf-8") == "这是测试内容"

    def test_restore_backup_to_target(self, temp_project, sample_file, tmp_path):
        """测试恢复到指定位置"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(sample_file, "v1")
        backup_name = record["backup_name"]

        target = tmp_path / "restored" / "file.txt"
        restored = manager.restore_backup(backup_name, target_path=target)

        assert restored.exists()
        assert restored.read_text(encoding="utf-8") == "这是测试内容"

    def test_verify_backup(self, temp_project, sample_file):
        """测试验证备份完整性"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(sample_file, "v1")
        assert manager.verify_backup(record["backup_name"])

    def test_verify_backup_corrupted(self, temp_project, sample_file):
        """测试验证损坏的备份"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(sample_file, "v1")
        backup_path = Path(record["backup_path"])

        # 损坏备份文件
        if backup_path.is_file():
            backup_path.write_text("损坏的内容", encoding="utf-8")
        else:
            for f in backup_path.rglob("*"):
                if f.is_file():
                    f.write_text("损坏的内容", encoding="utf-8")
                    break

        assert not manager.verify_backup(record["backup_name"])

    def test_delete_backup(self, temp_project, sample_file):
        """测试删除备份"""
        manager = BackupManager(temp_project)

        record = manager.create_backup(sample_file, "v1")
        assert manager.delete_backup(record["backup_name"])
        assert len(manager.list_backups()) == 0

    def test_delete_nonexistent_backup(self, temp_project):
        """测试删除不存在的备份"""
        manager = BackupManager(temp_project)
        assert not manager.delete_backup("nonexistent")

    def test_backup_not_found(self, temp_project):
        """测试恢复不存在的备份"""
        manager = BackupManager(temp_project)

        with pytest.raises(BackupError) as exc_info:
            manager.restore_backup("nonexistent")
        assert "备份不存在" in str(exc_info.value)

    def test_backup_source_not_exists(self, temp_project):
        """测试备份不存在的源"""
        manager = BackupManager(temp_project)

        with pytest.raises(BackupError) as exc_info:
            manager.create_backup(Path("不存在的路径"), "v1")
        assert "源路径不存在" in str(exc_info.value)

    def test_multiple_versions(self, temp_project, sample_file):
        """测试多版本备份"""
        manager = BackupManager(temp_project)

        manager.create_backup(sample_file, "v1")
        manager.create_backup(sample_file, "v2")
        manager.create_backup(sample_file, "v3")

        assert len(manager.list_backups()) == 3
        assert len(manager.list_backups(version="v2")) == 1
