"""AVM 版本号计算"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.io import atomic_write_json, read_json
from ..core.paths import get_version_index_json_path
from ..exceptions import VersionError
from .ops import GitOps


class VersionCalculator:
    """版本号计算器

    从多个来源收集版本号，任何来源查询失败必须阻塞。
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.git = GitOps(project_root)

    def get_next_version(self) -> int:
        """获取下一个版本号

        Returns:
            下一个永不复用的版本号

        Raises:
            VersionError: 如果任何来源查询失败
        """
        versions = set()

        # 1. 本地标签
        local_tags = self._get_local_tag_versions()
        versions.update(local_tags)

        # 2. 远程标签
        remote_tags = self._get_remote_tag_versions()
        versions.update(remote_tags)

        # 3. 远程分支
        branch_versions = self._get_branch_versions()
        versions.update(branch_versions)

        # 4. 版本索引
        index_versions = self._get_index_versions()
        versions.update(index_versions)

        if not versions:
            return 1

        return max(versions) + 1

    def _get_local_tag_versions(self) -> set[int]:
        """获取本地标签版本号"""
        max_ver = self.git.get_max_version_tag()
        if max_ver == 0:
            return set()
        return set(range(1, max_ver + 1))

    def _get_remote_tag_versions(self) -> set[int]:
        """获取远程标签版本号

        Raises:
            VersionError: 如果远程查询失败
        """
        try:
            max_ver = self.git.get_max_version_tag_remote()
            if max_ver is None:
                raise VersionError("远程标签查询失败（网络或认证问题）")
            if max_ver == 0:
                return set()
            return set(range(1, max_ver + 1))
        except VersionError:
            raise
        except Exception as e:
            raise VersionError(f"无法获取远程标签: {e}") from e

    def _get_branch_versions(self) -> set[int]:
        """获取远程分支版本号

        Raises:
            VersionError: 如果远程查询失败
        """
        try:
            max_ver = self.git.get_max_version_branch()
            if max_ver is None:
                raise VersionError("远程分支查询失败（网络或认证问题）")
            if max_ver == 0:
                return set()
            return set(range(1, max_ver + 1))
        except VersionError:
            raise
        except Exception as e:
            raise VersionError(f"无法获取远程分支: {e}") from e

    def _get_index_versions(self) -> set[int]:
        """获取版本索引中的版本号

        Raises:
            VersionError: 如果索引损坏无法解析
        """
        index_path = get_version_index_json_path(self.project_root)
        if not index_path.exists():
            return set()

        try:
            index = read_json(index_path)
        except Exception as e:
            raise VersionError(f"版本索引损坏: {e}") from e

        if not isinstance(index, dict):
            raise VersionError("版本索引格式错误: 预期为字典")

        versions = set()

        # 正式版本
        for v in index.get("formal_versions", []):
            if "version" in v:
                ver = self._parse_version(v["version"])
                if ver is not None:
                    versions.add(ver)

        # 废弃版本
        for v in index.get("abandoned_versions", []):
            if "version" in v:
                ver = self._parse_version(v["version"])
                if ver is not None:
                    versions.add(ver)

        return versions

    def _parse_version(self, version_str: str) -> int | None:
        """解析版本号

        只匹配 v1, v2, v3... 格式。
        """
        match = re.match(r"^v(\d+)$", version_str)
        if match:
            return int(match.group(1))
        return None

    def validate_version_available(self, version: int) -> bool:
        """验证版本号是否可用"""
        all_versions = set()

        # 收集所有已知版本
        all_versions.update(self._get_local_tag_versions())
        all_versions.update(self._get_remote_tag_versions())
        all_versions.update(self._get_branch_versions())
        all_versions.update(self._get_index_versions())

        return version not in all_versions

    def reserve_version(self, version: int) -> bool:
        """预留版本号

        将版本号写入版本索引。
        """
        index_path = get_version_index_json_path(self.project_root)

        if index_path.exists():
            index = read_json(index_path)
        else:
            index = {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [],
                "abandoned_versions": [],
                "pending_archives": [],
            }

        # 检查是否已存在
        for v in index.get("formal_versions", []):
            if v.get("version") == f"v{version}":
                return True

        # 添加预留记录
        index["formal_versions"].append(
            {
                "version": f"v{version}",
                "status": "reserved",
                "reserved_at": None,  # 由调用方填充
            }
        )

        atomic_write_json(index_path, index)
        return True

    def get_doc_version(self) -> int:
        """获取下一个文档版本号

        Raises:
            VersionError: 如果索引损坏无法解析
        """
        index_path = get_version_index_json_path(self.project_root)

        if not index_path.exists():
            return 1

        try:
            index = read_json(index_path)
        except Exception as e:
            raise VersionError(f"版本索引损坏: {e}") from e

        if not isinstance(index, dict):
            raise VersionError("版本索引格式错误: 预期为字典")

        max_ver = 0
        for v in index.get("document_versions", []):
            if "version" in v:
                ver = self._parse_doc_version(v["version"])
                if ver is not None:
                    max_ver = max(max_ver, ver)

        return max_ver + 1

    def _parse_doc_version(self, version_str: str) -> int | None:
        """解析文档版本号"""
        match = re.match(r"^doc-v(\d+)$", version_str)
        if match:
            return int(match.group(1))
        return None

    def format_version(self, version: int, prefix: str = "v") -> str:
        """格式化版本号"""
        return f"{prefix}{version}"
