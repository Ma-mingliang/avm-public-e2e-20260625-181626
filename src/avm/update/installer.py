"""AVM 安装和更新管理"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.hashing import compute_file_sha256
from ..core.io import atomic_write_json, read_json


class Installer:
    """AVM 安装器

    管理 AVM 的安装、更新和回滚。
    """

    def __init__(self, install_dir: Path | None = None):
        """初始化安装器

        Args:
            install_dir: 安装目录（默认 AVM_HOME 或 ~/.agent-version-manager）
        """
        import os

        self.install_dir = install_dir or Path(os.environ.get("AVM_HOME", str(Path.home() / ".agent-version-manager")))
        self.backup_dir = self.install_dir / "backups"
        self.version_file = self.install_dir / "version.json"

    def get_current_version(self) -> str:
        """获取当前版本

        Returns:
            版本字符串
        """
        if self.version_file.exists():
            try:
                data = json.loads(self.version_file.read_text(encoding="utf-8"))
                return data.get("version", "unknown")
            except Exception:
                return "unknown"
        return "not installed"

    def get_latest_version(self) -> str:
        """从 PyPI 查询实际最新版本；查询失败由调用方显式处理。"""
        import urllib.request

        with urllib.request.urlopen("https://pypi.org/pypi/agent-version-manager/json", timeout=10) as response:
            data = json.load(response)
        version = data.get("info", {}).get("version")
        if not isinstance(version, str) or not version:
            raise RuntimeError("PyPI 响应缺少版本")
        return version

    def install(self, source: Path | None = None) -> dict[str, Any]:
        """安装 AVM

        Args:
            source: 安装源（默认从 PyPI）

        Returns:
            安装结果
        """
        result = {
            "success": True,
            "action": "install",
            "steps": [],
        }

        # 1. 检查是否已安装
        if self.version_file.exists():
            result["steps"].append(
                {
                    "step": "check_existing",
                    "status": "warn",
                    "message": "AVM 已安装，将执行更新",
                }
            )
            return self.update(source)

        # 2. 安装
        try:
            if source:
                # 从本地源安装
                self._install_from_source(source)
            else:
                # 从 PyPI 安装
                self._install_from_pypi()

            result["steps"].append(
                {
                    "step": "install",
                    "status": "ok",
                    "message": "安装成功",
                }
            )
        except Exception as e:
            result["steps"].append(
                {
                    "step": "install",
                    "status": "error",
                    "message": f"安装失败: {e}",
                }
            )
            result["success"] = False
            return result

        # 3. 记录版本
        self._save_version("1.0.0")

        return result

    def update(self, source: Path | None = None) -> dict[str, Any]:
        """更新 AVM

        Args:
            source: 更新源

        Returns:
            更新结果
        """
        result = {
            "success": True,
            "action": "update",
            "steps": [],
        }

        # 1. 备份当前版本
        try:
            backup_path = self._backup_current()
            result["steps"].append(
                {
                    "step": "backup",
                    "status": "ok",
                    "message": f"备份完成: {backup_path}",
                }
            )
        except Exception as e:
            result["steps"].append(
                {
                    "step": "backup",
                    "status": "warn",
                    "message": f"备份失败: {e}",
                }
            )

        # 2. 更新
        try:
            if source:
                self._install_from_source(source)
            else:
                self._install_from_pypi()

            result["steps"].append(
                {
                    "step": "update",
                    "status": "ok",
                    "message": "更新成功",
                }
            )
        except Exception as e:
            result["steps"].append(
                {
                    "step": "update",
                    "status": "error",
                    "message": f"更新失败: {e}",
                }
            )
            result["success"] = False

            # 尝试回滚
            try:
                self.rollback()
                result["steps"].append(
                    {
                        "step": "rollback",
                        "status": "ok",
                        "message": "已回滚到上一版本",
                    }
                )
            except Exception as rollback_error:
                result["steps"].append(
                    {
                        "step": "rollback",
                        "status": "error",
                        "message": f"回滚失败: {rollback_error}",
                    }
                )

            return result

        return result

    def rollback(self) -> dict[str, Any]:
        """回滚到上一版本

        Returns:
            回滚结果
        """
        result = {
            "success": True,
            "action": "rollback",
            "steps": [],
        }

        # 1. 查找最近的备份
        backups = self._list_backups()
        if not backups:
            result["steps"].append(
                {
                    "step": "find_backup",
                    "status": "error",
                    "message": "没有可用的备份",
                }
            )
            result["success"] = False
            return result

        latest_backup = backups[-1]

        # 2. 只有可验证、可重新安装的制品才构成代码回滚。
        try:
            artifact_record_path = Path(latest_backup["path"]) / "artifact.json"
            if not artifact_record_path.exists():
                result["steps"].append(
                    {
                        "step": "restore",
                        "status": "error",
                        "message": "旧备份不包含可重新安装的制品，不能证明代码已回滚",
                    }
                )
                result["success"] = False
                return result
            artifact_record = read_json(artifact_record_path)
            artifact = Path(artifact_record["artifact_path"]).resolve()
            backup_root = Path(latest_backup["path"]).resolve()
            if backup_root not in artifact.parents:
                raise RuntimeError("回滚制品路径超出备份目录")
            if not artifact.is_file() or compute_file_sha256(artifact) != artifact_record.get("sha256"):
                raise RuntimeError("回滚制品完整性校验失败")
            self._pip_install(artifact)
            self._restore_backup(latest_backup)
            result["steps"].append(
                {
                    "step": "restore",
                    "status": "ok",
                    "message": f"已恢复到备份: {latest_backup['name']}",
                }
            )
        except Exception as e:
            result["steps"].append(
                {
                    "step": "restore",
                    "status": "error",
                    "message": f"恢复失败: {e}",
                }
            )
            result["success"] = False

        return result

    def _install_from_pypi(self) -> None:
        """从 PyPI 安装"""
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "agent-version-manager"],
            check=True,
            capture_output=True,
            text=True,
        )

    def _install_from_source(self, source: Path) -> None:
        """从本地源安装"""
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", str(source)],
            check=True,
            capture_output=True,
            text=True,
        )

    def _pip_install(self, artifact: Path) -> None:
        """重新安装已校验的本地制品。"""
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--force-reinstall", str(artifact)],
            check=True,
            capture_output=True,
            text=True,
        )

    def _record_artifact_backup(self, artifact: Path, version: str) -> dict[str, str]:
        """把可重新安装制品复制到独立备份并记录哈希。"""
        backup_path = self._backup_current()
        target = backup_path / artifact.name
        shutil.copy2(artifact, target)
        record = {
            "version": version,
            "artifact_path": str(target),
            "sha256": compute_file_sha256(target),
        }
        atomic_write_json(backup_path / "artifact.json", record)
        return record

    def _backup_current(self) -> Path:
        """备份当前版本"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        version = self.get_current_version()
        backup_name = f"backup_{version}_{timestamp}"
        backup_path = self.backup_dir / backup_name

        # 备份关键文件
        backup_path.mkdir(parents=True, exist_ok=True)

        # 备份版本文件
        if self.version_file.exists():
            shutil.copy2(self.version_file, backup_path / "version.json")

        # 备份配置
        config_dir = self.install_dir / "config"
        if config_dir.exists():
            shutil.copytree(config_dir, backup_path / "config", dirs_exist_ok=True)

        return backup_path

    def _restore_backup(self, backup: dict[str, Any]) -> None:
        """恢复备份"""
        backup_path = Path(backup["path"])

        # 恢复版本文件
        version_backup = backup_path / "version.json"
        if version_backup.exists():
            shutil.copy2(version_backup, self.version_file)

    def _list_backups(self) -> list:
        """列出备份"""
        if not self.backup_dir.exists():
            return []

        backups = []
        for item in sorted(self.backup_dir.iterdir()):
            if item.is_dir() and item.name.startswith("backup_"):
                backups.append(
                    {
                        "name": item.name,
                        "path": str(item),
                    }
                )

        return backups

    def _save_version(self, version: str) -> None:
        """保存版本信息"""
        data = {
            "version": version,
            "installed_at": datetime.now(UTC).isoformat(),
            "python": sys.version,
        }
        self.version_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
