"""AVM 配置管理测试"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from avm.config import (
    _parse_config,
    create_default_config,
    get_global_dir,
    get_project_config_path,
    load_project_config,
    save_project_config,
)
from avm.exceptions import ConfigError


class TestGetGlobalDir:
    """全局目录测试"""

    def test_env_var_override(self, tmp_path):
        """测试环境变量覆盖"""
        with patch.dict(os.environ, {"AVM_HOME": str(tmp_path)}):
            result = get_global_dir()
            assert result == tmp_path

    def test_default_dir(self, tmp_path):
        """测试默认目录"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("avm.config.DEFAULT_GLOBAL_DIR", tmp_path):
                result = get_global_dir()
                assert result == tmp_path

    def test_fallback_to_home(self):
        """测试回退到用户目录"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("avm.config.DEFAULT_GLOBAL_DIR", Path("/nonexistent")):
                try:
                    result = get_global_dir()
                    assert result == Path.home() / ".agent-version-manager"
                except RuntimeError:
                    # Path.home() may fail in some CI environments
                    pytest.skip("Cannot determine home directory in this environment")


class TestGetProjectConfigPath:
    """项目配置路径测试"""

    def test_config_path(self, tmp_path):
        """测试配置文件路径"""
        result = get_project_config_path(tmp_path)
        assert result.name == "配置.yaml"
        assert "版本管理" in str(result)


class TestLoadProjectConfig:
    """加载项目配置测试"""

    def test_load_existing_config(self, tmp_path):
        """测试加载已有配置"""
        config_dir = tmp_path / "版本管理"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "配置.yaml"
        config_data = {
            "schema_version": 1,
            "project": {"name": "test", "root": str(tmp_path)},
        }
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_project_config(tmp_path)
        assert result.project.name == "test"
        assert result.schema_version == 1

    def test_load_nonexistent_config(self, tmp_path):
        """测试加载不存在的配置"""
        with pytest.raises(ConfigError, match="配置文件不存在"):
            load_project_config(tmp_path)

    def test_load_invalid_yaml(self, tmp_path):
        """测试加载无效 YAML"""
        config_dir = tmp_path / "版本管理"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "配置.yaml"
        config_file.write_text("invalid: yaml: [", encoding="utf-8")

        with pytest.raises(ConfigError, match="配置文件格式错误"):
            load_project_config(tmp_path)

    def test_load_non_dict_yaml(self, tmp_path):
        """测试加载非字典 YAML"""
        config_dir = tmp_path / "版本管理"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "配置.yaml"
        config_file.write_text("- item1\n- item2", encoding="utf-8")

        with pytest.raises(ConfigError, match="配置文件必须是YAML字典"):
            load_project_config(tmp_path)

    def test_load_unsupported_schema_version(self, tmp_path):
        """测试不支持的 schema 版本"""
        config_dir = tmp_path / "版本管理"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "配置.yaml"
        config_data = {"schema_version": 99, "project": {"name": "test"}}
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(ConfigError, match="不支持的配置schema版本"):
            load_project_config(tmp_path)


class TestParseConfig:
    """配置解析测试"""

    def test_parse_minimal_config(self, tmp_path):
        """测试最小配置"""
        data = {"schema_version": 1, "project": {"name": "test"}}
        result = _parse_config(data, tmp_path)
        assert result.project.name == "test"
        assert result.versioning.formal_prefix == "v"

    def test_parse_full_config(self, tmp_path):
        """测试完整配置"""
        data = {
            "schema_version": 1,
            "project": {
                "name": "myproject",
                "github_repo": "user/repo",
                "default_branch": "develop",
            },
            "versioning": {
                "formal_prefix": "release-",
                "document_prefix": "doc-",
                "never_reuse_reserved": False,
                "one_active_task": False,
                "merge_strategy": "merge",
            },
            "language": {
                "user_facing": "en-US",
                "machine_identifiers": "ascii",
            },
            "validation": {
                "commands": [{"name": "test", "command": ["pytest"]}],
            },
            "risk": {
                "extra_file_limit": 10,
                "expansion_ratio": 0.3,
                "sensitive_patterns": ["*.key"],
                "high_risk_paths": ["secrets/"],
            },
            "lfs": {
                "enabled": True,
                "patterns": ["*.bin"],
            },
            "agent_adapters": {
                "claude_code": True,
                "hermes": False,
                "codex": True,
            },
        }
        result = _parse_config(data, tmp_path)
        assert result.project.github_repo == "user/repo"
        assert result.versioning.formal_prefix == "release-"
        assert result.risk.extra_file_limit == 10
        assert result.lfs.enabled is True
        assert result.agent_adapters.hermes is False


class TestCreateDefaultConfig:
    """创建默认配置测试"""

    def test_create_default(self, tmp_path):
        """测试创建默认配置"""
        result = create_default_config(tmp_path, "myproject")
        assert result.schema_version == 1
        assert result.project.name == "myproject"
        assert result.project.default_branch == "main"

    def test_create_with_github_repo(self, tmp_path):
        """测试带 GitHub 仓库的配置"""
        result = create_default_config(tmp_path, "myproject", "user/repo")
        assert result.project.github_repo == "user/repo"


class TestSaveProjectConfig:
    """保存项目配置测试"""

    def test_save_and_load(self, tmp_path):
        """测试保存并加载"""
        config = create_default_config(tmp_path, "testproject")
        save_project_config(config, tmp_path)

        loaded = load_project_config(tmp_path)
        assert loaded.project.name == "testproject"

    def test_save_creates_directory(self, tmp_path):
        """测试保存时创建目录"""
        config = create_default_config(tmp_path, "testproject")
        save_project_config(config, tmp_path)

        config_path = get_project_config_path(tmp_path)
        assert config_path.exists()
