"""AVM 文档备份管理"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..exceptions import BackupError
from .hashing import compute_file_sha256
from .io import atomic_write_json, read_json
from .paths import get_version_dir


class BackupManager:
    """文档备份管理器

    管理文档版本的 SHA-256 备份，支持备份列表和恢复。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.version_dir = get_version_dir(project_root)
        self.backup_dir = self.version_dir / "backups"
        self.backup_index_path = self.backup_dir / "index.json"

    def ensure_dirs(self) -> None:
        """确保备份目录存在"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _copy_file(src: str | Path, dst: str | Path) -> None:
        """复制文件（避免权限问题）"""
        with open(src, "rb") as f:
            content = f.read()
        with open(dst, "wb") as f:
            f.write(content)

    @staticmethod
    def _restore_file(source: str | Path, target: str | Path) -> None:
        """恢复单个文件（使用原子替换）"""
        import tempfile

        target_path = Path(target)
        fd, tmp_path = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
        try:
            with open(source, "rb") as src_f:
                content = src_f.read()
            with os.fdopen(fd, "wb") as tmp_f:
                tmp_f.write(content)
            os.replace(tmp_path, str(target_path))
        except:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def create_backup(
        self,
        source_path: Path,
        version: str,
        description: str = "",
    ) -> dict[str, Any]:
        """创建备份

        Args:
            source_path: 源文件或目录路径
            version: 版本号
            description: 备份描述

        Returns:
            备份记录

        Raises:
            BackupError: 如果备份失败
        """
        self.ensure_dirs()

        source = Path(source_path)
        if not source.exists():
            raise BackupError(f"源路径不存在: {source}")

        # 创建版本备份目录
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{version}_{timestamp}"
        backup_path = self.backup_dir / backup_name

        try:
            if source.is_file():
                backup_path.mkdir(parents=True, exist_ok=True)
                dest = backup_path / source.name
                self._copy_file(source, dest)
                sha256 = compute_file_sha256(dest)
                files = [{"path": source.name, "sha256": sha256}]
            else:
                # 目录备份
                shutil.copytree(source, backup_path, dirs_exist_ok=True, copy_function=self._copy_file)
                files = []
                for f in backup_path.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(backup_path)
                        sha256 = compute_file_sha256(f)
                        files.append({"path": str(rel.as_posix()), "sha256": sha256})
        except Exception as e:
            raise BackupError(f"备份失败: {e}") from e

        # 创建备份记录
        record = {
            "backup_name": backup_name,
            "version": version,
            "source_path": str(source),
            "backup_path": str(backup_path),
            "timestamp": timestamp,
            "description": description,
            "files": files,
        }

        # 更新索引
        self._update_index(record)
        return record

    def list_backups(self, version: str | None = None) -> list[dict[str, Any]]:
        """列出备份

        Args:
            version: 可选的版本过滤

        Returns:
            备份记录列表
        """
        index = self._load_index()
        backups = index.get("backups", [])

        if version:
            backups = [b for b in backups if b.get("version") == version]

        return backups

    def restore_backup(
        self,
        backup_name: str,
        target_path: Path | None = None,
    ) -> Path:
        """恢复备份

        恢复流程：先验证备份完整性 → 恢复到临时位置 → 校验 SHA-256 → 原子替换目标。
        任何步骤失败都保证原目标文件字节不变。

        Args:
            backup_name: 备份名称
            target_path: 目标路径（默认恢复到原位置）

        Returns:
            恢复路径

        Raises:
            BackupError: 如果恢复失败
        """
        index = self._load_index()
        backups = index.get("backups", [])

        record = None
        for b in backups:
            if b.get("backup_name") == backup_name:
                record = b
                break

        if record is None:
            raise BackupError(f"备份不存在: {backup_name}")

        source_path = Path(record["backup_path"])
        if not source_path.exists():
            raise BackupError(f"备份文件已丢失: {source_path}")

        target = Path(target_path) if target_path else Path(record["source_path"])

        # 1. 先验证备份本身完整性
        if not self.verify_backup(backup_name):
            raise BackupError(f"备份完整性校验失败: {backup_name}")

        import tempfile

        # 2. 恢复到临时目录
        tmp_dir = Path(tempfile.mkdtemp(prefix="avm_restore_"))
        try:
            if source_path.is_dir():
                files = record.get("files", [])
                if len(files) == 1:
                    # 单文件备份
                    source_file = source_path / files[0]["path"]
                    tmp_target = tmp_dir / "restored"
                    self._restore_file(source_file, tmp_target)
                    # 3. 校验临时文件 SHA-256
                    self._verify_restore(record, tmp_target)
                    # 4. 原子替换目标
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(str(tmp_target), str(target))
                else:
                    # 多文件备份
                    tmp_target = tmp_dir / "restored"
                    shutil.copytree(source_path, tmp_target, copy_function=self._copy_file)
                    # 3. 校验临时目录 SHA-256
                    self._verify_restore(record, tmp_target)
                    # 4. 原子替换目标
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.move(str(tmp_target), str(target))
            elif source_path.is_file():
                # 兼容旧格式（单文件备份）
                tmp_target = tmp_dir / "restored"
                self._restore_file(source_path, tmp_target)
                self._verify_restore(record, tmp_target)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(str(tmp_target), str(target))
        except BackupError:
            raise
        except Exception as e:
            raise BackupError(f"恢复失败: {e}") from e
        finally:
            # 清理临时目录
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return target

    def verify_backup(self, backup_name: str) -> bool:
        """验证备份完整性

        Args:
            backup_name: 备份名称

        Returns:
            是否完整

        Raises:
            BackupError: 如果验证失败
        """
        index = self._load_index()
        backups = index.get("backups", [])

        record = None
        for b in backups:
            if b.get("backup_name") == backup_name:
                record = b
                break

        if record is None:
            raise BackupError(f"备份不存在: {backup_name}")

        backup_path = Path(record["backup_path"])
        if not backup_path.exists():
            return False

        # 验证每个文件的 SHA-256
        for file_info in record.get("files", []):
            file_path = backup_path / file_info["path"]
            if not file_path.exists():
                return False
            current_hash = compute_file_sha256(file_path)
            if current_hash != file_info["sha256"]:
                return False

        return True

    def delete_backup(self, backup_name: str) -> bool:
        """删除备份

        Args:
            backup_name: 备份名称

        Returns:
            是否成功删除
        """
        index = self._load_index()
        backups = index.get("backups", [])

        record = None
        for i, b in enumerate(backups):
            if b.get("backup_name") == backup_name:
                record = backups.pop(i)
                break

        if record is None:
            return False

        # 删除备份文件
        backup_path = Path(record["backup_path"])
        if backup_path.exists():
            if backup_path.is_file():
                backup_path.unlink()
            else:
                shutil.rmtree(backup_path)

        # 更新索引
        atomic_write_json(self.backup_index_path, index)
        return True

    def _verify_restore(self, record: dict[str, Any], target: Path) -> None:
        """验证恢复后的文件"""
        if target.is_file():
            expected = record["files"][0]["sha256"] if record["files"] else None
            if expected:
                actual = compute_file_sha256(target)
                if actual != expected:
                    raise BackupError("恢复验证失败: SHA-256 不匹配")
        else:
            for file_info in record.get("files", []):
                file_path = target / file_info["path"]
                if file_path.exists():
                    actual = compute_file_sha256(file_path)
                    if actual != file_info["sha256"]:
                        raise BackupError(f"恢复验证失败: {file_info['path']} SHA-256 不匹配")

    def _load_index(self) -> dict[str, Any]:
        """加载备份索引"""
        if not self.backup_index_path.exists():
            return {"backups": []}
        try:
            return read_json(self.backup_index_path)
        except Exception:
            return {"backups": []}

    def _update_index(self, record: dict[str, Any]) -> None:
        """更新备份索引"""
        self.ensure_dirs()
        index = self._load_index()
        index.setdefault("backups", []).append(record)
        atomic_write_json(self.backup_index_path, index)
