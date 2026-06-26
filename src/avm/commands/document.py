"""AVM document 命令 - 文档版本管理"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from ..core.hashing import compute_file_sha256
from ..core.io import atomic_write_json, read_json
from ..core.paths import (
    get_document_version_dir,
    get_pending_archive_dir,
    get_version_index_json_path,
)
from ..core.state_machine import StateMachine
from ..git.versioning import VersionCalculator

console = Console()


def run_document_start(
    project_path: Path,
    files: list[str],
    json_output: bool = False,
) -> bool:
    """开始文档版本任务

    创建一个新的文档版本目录，记录需要修改的文件列表。

    Args:
        project_path: 项目路径
        files: 文档文件列表
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "doc_version": None,
        "files": files,
        "steps": [],
    }

    # 检查状态机
    sm = StateMachine(project_path)
    sm.load()

    if not sm.is_idle():
        current = sm.current_status.value
        result["steps"].append(
            {
                "step": "check_state",
                "status": "error",
                "message": f"当前状态为 {current}，无法开始文档任务",
            }
        )
        _output(result, json_output)
        return False

    # 计算文档版本号
    calc = VersionCalculator(project_path)
    try:
        doc_ver_num = calc.get_doc_version()
        doc_ver = f"doc-v{doc_ver_num}"
    except Exception as e:
        result["steps"].append(
            {
                "step": "calculate_version",
                "status": "error",
                "message": f"文档版本号计算失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    result["doc_version"] = doc_ver

    # 创建文档版本目录
    doc_dir = get_document_version_dir(project_path, doc_ver)
    doc_dir.mkdir(parents=True, exist_ok=True)

    # 检查文件是否存在（规范化路径）
    missing_files = []
    normalized_files: list[str] = []
    for f in files:
        file_path = Path(f)
        if file_path.is_absolute():
            # 绝对路径：尝试转为相对路径
            try:
                rel = file_path.resolve().relative_to(project_path.resolve())
                normalized_files.append(rel.as_posix())
            except ValueError:
                # 文件在项目外部，使用文件名+短哈希
                from ..core.hashing import compute_string_sha256, short_hash

                safe_name = f"{file_path.stem}_{short_hash(compute_string_sha256(str(file_path)))}{file_path.suffix}"
                normalized_files.append(safe_name)
        else:
            normalized_files.append(f)
        file_path_resolved = project_path / f if not Path(f).is_absolute() else Path(f)
        if not file_path_resolved.exists():
            missing_files.append(f)
    if missing_files:
        result["steps"].append(
            {
                "step": "check_files",
                "status": "error",
                "message": f"以下文件不存在: {', '.join(missing_files)}",
            }
        )
        _output(result, json_output)
        return False

    # 创建修改前备份
    backup_dir = doc_dir / "修改前备份"
    backup_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    backup_ok = True
    for orig_f, norm_f in zip(files, normalized_files, strict=True):
        src = Path(orig_f) if Path(orig_f).is_absolute() else project_path / orig_f
        dest = backup_dir / norm_f
        # 安全检查：源和目标不能是同一文件
        if src.resolve() == dest.resolve():
            backup_ok = False
            result["steps"].append(
                {
                    "step": "backup",
                    "status": "error",
                    "message": f"文件 {orig_f} 备份路径与源文件相同，拒绝覆盖",
                }
            )
            break
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            # 复制文件
            with open(src, "rb") as rf:
                content = rf.read()
            with open(dest, "wb") as wf:
                wf.write(content)
                wf.flush()
                os.fsync(wf.fileno())
            # 二次校验 SHA-256
            src_hash = compute_file_sha256(src)
            dest_hash = compute_file_sha256(dest)
            if src_hash != dest_hash:
                backup_ok = False
                result["steps"].append(
                    {
                        "step": "backup_verify",
                        "status": "error",
                        "message": f"文件 {orig_f} 备份 SHA-256 校验失败",
                    }
                )
                break
            manifest_entries.append(
                {
                    "path": orig_f,
                    "normalized_path": norm_f,
                    "sha256": src_hash,
                    "size": len(content),
                    "backup_at": datetime.now(UTC).isoformat(),
                }
            )
        except Exception as e:
            backup_ok = False
            result["steps"].append(
                {
                    "step": "backup",
                    "status": "error",
                    "message": f"备份文件 {orig_f} 失败: {e}",
                }
            )
            break

    if not backup_ok:
        _output(result, json_output)
        return False

    # 写入备份清单
    manifest = {
        "doc_version": doc_ver,
        "created_at": datetime.now(UTC).isoformat(),
        "files": manifest_entries,
    }
    atomic_write_json(backup_dir / "manifest.json", manifest)

    # 写入中文清单
    manifest_md = f"# 备份清单 - {doc_ver}\n\n"
    manifest_md += f"创建时间: {datetime.now(UTC).isoformat()}\n\n"
    manifest_md += "| 文件路径 | SHA-256 | 大小 |\n|---|---|---|\n"
    for entry in manifest_entries:
        manifest_md += f"| {entry['path']} | {entry['sha256'][:16]}... | {entry['size']} 字节 |\n"
    (backup_dir / "备份清单.md").write_text(manifest_md, encoding="utf-8")

    result["steps"].append(
        {
            "step": "backup",
            "status": "ok",
            "message": f"已备份 {len(manifest_entries)} 个文件",
        }
    )

    # 写入文档任务元数据
    metadata = {
        "version": doc_ver,
        "files": files,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "in_progress",
        "backup_dir": str(backup_dir),
        "backup_manifest": str(backup_dir / "manifest.json"),
    }
    atomic_write_json(doc_dir / "metadata.json", metadata)

    # 更新版本索引
    _add_doc_version_to_index(project_path, doc_ver, files)

    result["success"] = True
    result["steps"].append(
        {
            "step": "create_doc_version",
            "status": "ok",
            "message": f"文档版本 {doc_ver} 已创建",
        }
    )

    _output(result, json_output)
    return True


def run_document_complete(project_path: Path, json_output: bool = False) -> bool:
    """完成文档版本任务

    将当前文档版本标记为已完成。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "steps": [],
    }

    # 查找最新的进行中的文档版本
    index_path = get_version_index_json_path(project_path)
    if not index_path.exists():
        result["steps"].append(
            {
                "step": "find_doc_version",
                "status": "error",
                "message": "版本索引不存在",
            }
        )
        _output(result, json_output)
        return False

    try:
        index = read_json(index_path)
    except Exception as e:
        result["steps"].append(
            {
                "step": "find_doc_version",
                "status": "error",
                "message": f"读取版本索引失败: {e}",
            }
        )
        _output(result, json_output)
        return False

    # 查找最新进行中的文档版本
    doc_versions = index.get("document_versions", [])
    current_doc = None
    for dv in reversed(doc_versions):
        if dv.get("status") == "in_progress":
            current_doc = dv
            break

    if current_doc is None:
        result["steps"].append(
            {
                "step": "find_doc_version",
                "status": "error",
                "message": "没有进行中的文档版本",
            }
        )
        _output(result, json_output)
        return False

    # 更新状态为完成
    doc_ver = current_doc["version"]
    current_doc["status"] = "completed"
    current_doc["completed_at"] = datetime.now(UTC).isoformat()

    # 更新文档版本元数据
    doc_dir = get_document_version_dir(project_path, doc_ver)
    metadata_path = doc_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = read_json(metadata_path)
            metadata["status"] = "completed"
            metadata["completed_at"] = current_doc["completed_at"]
            atomic_write_json(metadata_path, metadata)
        except Exception:
            pass

    # 保存索引
    atomic_write_json(index_path, index)

    result["success"] = True
    result["steps"].append(
        {
            "step": "complete_doc_version",
            "status": "ok",
            "message": f"文档版本 {doc_ver} 已完成",
        }
    )

    _output(result, json_output)
    return True


def run_archive_pending_docs(project_path: Path, json_output: bool = False) -> bool:
    """归档待处理文档

    将待归档目录中的文档移动到对应的文档版本目录。

    Args:
        project_path: 项目路径
        json_output: JSON 输出格式

    Returns:
        是否成功
    """
    result = {
        "success": False,
        "archived_count": 0,
        "steps": [],
    }

    pending_dir = get_pending_archive_dir(project_path)
    if not pending_dir.exists():
        result["success"] = True
        result["steps"].append(
            {
                "step": "check_pending",
                "status": "ok",
                "message": "没有待归档文档",
            }
        )
        _output(result, json_output)
        return True

    # 列出待归档文件
    pending_files = list(pending_dir.rglob("*"))
    pending_files = [f for f in pending_files if f.is_file()]

    if not pending_files:
        result["success"] = True
        result["steps"].append(
            {
                "step": "check_pending",
                "status": "ok",
                "message": "没有待归档文档",
            }
        )
        _output(result, json_output)
        return True

    # 查找或创建归档目标
    index_path = get_version_index_json_path(project_path)
    if index_path.exists():
        try:
            index = read_json(index_path)
        except Exception:
            index = {"pending_archives": []}
    else:
        index = {"pending_archives": []}

    # 创建归档记录
    archive_entry = {
        "archived_at": datetime.now(UTC).isoformat(),
        "files": [str(f.relative_to(pending_dir).as_posix()) for f in pending_files],
        "source_dir": str(pending_dir),
    }

    index.setdefault("pending_archives", []).append(archive_entry)
    atomic_write_json(index_path, index)

    result["success"] = True
    result["archived_count"] = len(pending_files)
    result["steps"].append(
        {
            "step": "archive",
            "status": "ok",
            "message": f"已归档 {len(pending_files)} 个文档",
        }
    )

    _output(result, json_output)
    return True


def _add_doc_version_to_index(project_path: Path, doc_ver: str, files: list[str]) -> None:
    """将文档版本添加到版本索引"""
    index_path = get_version_index_json_path(project_path)

    if index_path.exists():
        try:
            index = read_json(index_path)
        except Exception:
            index = {
                "schema_version": 1,
                "formal_versions": [],
                "document_versions": [],
                "abandoned_versions": [],
                "pending_archives": [],
            }
    else:
        index = {
            "schema_version": 1,
            "formal_versions": [],
            "document_versions": [],
            "abandoned_versions": [],
            "pending_archives": [],
        }

    index.setdefault("document_versions", []).append(
        {
            "version": doc_ver,
            "files": files,
            "status": "in_progress",
            "started_at": datetime.now(UTC).isoformat(),
        }
    )

    atomic_write_json(index_path, index)


def _output(result: dict, json_output: bool) -> None:
    """输出结果"""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            console.print("[bold green]文档操作成功[/bold green]")
            if result.get("doc_version"):
                console.print(f"  版本: {result['doc_version']}")
            if result.get("archived_count"):
                console.print(f"  归档数: {result['archived_count']}")
        else:
            console.print("[bold red]文档操作失败[/bold red]")
            for step in result.get("steps", []):
                if step["status"] == "error":
                    console.print(f"  [red]✗ {step['message']}[/red]")
