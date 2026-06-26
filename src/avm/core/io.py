"""AVM 原子文件写入"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from ..exceptions import AVMError


def atomic_write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """原子写入文本文件

    使用临时文件 + rename 实现原子写入。
    Windows上 os.replace() 是原子覆盖。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # 写入临时文件
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp", prefix=".avm_")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # 原子替换
        os.replace(tmp_path, target)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path | str, data: Any, encoding: str = "utf-8", indent: int = 2) -> None:
    """原子写入JSON文件"""
    content = json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    atomic_write_text(path, content, encoding)


def atomic_write_yaml(path: Path | str, data: Any, encoding: str = "utf-8") -> None:
    """原子写入YAML文件"""
    content = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    atomic_write_text(path, content, encoding)


def read_json(path: Path | str) -> Any:
    """读取JSON文件"""
    target = Path(path)
    if not target.exists():
        raise AVMError(f"文件不存在: {target}")
    try:
        with open(target, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise AVMError(f"JSON格式错误: {target}: {e}") from e
    except OSError as e:
        raise AVMError(f"无法读取文件: {target}: {e}") from e


def read_yaml(path: Path | str) -> Any:
    """读取YAML文件"""
    target = Path(path)
    if not target.exists():
        raise AVMError(f"文件不存在: {target}")
    try:
        with open(target, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise AVMError(f"YAML格式错误: {target}: {e}") from e
    except OSError as e:
        raise AVMError(f"无法读取文件: {target}: {e}") from e


def read_text(path: Path | str, encoding: str = "utf-8") -> str:
    """读取文本文件"""
    target = Path(path)
    if not target.exists():
        raise AVMError(f"文件不存在: {target}")
    try:
        with open(target, encoding=encoding) as f:
            return f.read()
    except OSError as e:
        raise AVMError(f"无法读取文件: {target}: {e}") from e
