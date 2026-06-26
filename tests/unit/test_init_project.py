"""AVM init-project 命令测试"""

import subprocess

import pytest

from avm.commands.init_project import _init_project, run_init_project


@pytest.fixture
def git_project(tmp_path):
    """创建临时 Git 项目"""
    repo = tmp_path / "repo"
    repo.mkdir()

    # 初始化 Git 仓库
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)

    # 创建初始提交
    (repo / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "初始提交"], cwd=repo, capture_output=True)

    return repo


class TestInitProject:
    """init-project 命令测试"""

    def test_init_project_success(self, git_project):
        """测试成功初始化项目"""
        result = _init_project(git_project, "测试项目")

        assert result["success"]
        assert result["project_path"] == str(git_project)

        # 检查目录创建
        version_dir = git_project / "版本管理"
        assert version_dir.exists()
        assert (version_dir / "正式版本").exists()
        assert (version_dir / "文档版本").exists()
        assert (version_dir / "备份").exists()
        assert (version_dir / "审批").exists()
        assert (version_dir / "交接").exists()

        # 检查配置文件
        config_path = version_dir / "配置.yaml"
        assert config_path.exists()

        # 检查版本索引
        index_path = version_dir / "版本索引.json"
        assert index_path.exists()

    def test_init_project_not_git(self, tmp_path):
        """测试非 Git 项目自动初始化"""
        result = _init_project(tmp_path, "测试项目")

        assert result["success"]

        # 检查 Git 初始化
        git_init_step = next(s for s in result["steps"] if s["step"] == "git_init")
        assert git_init_step["status"] == "ok"

        # 检查基线提交
        baseline_step = next(s for s in result["steps"] if s["step"] == "baseline_commit")
        assert baseline_step["status"] == "ok"

        # 检查 v1 标签
        tag_step = next(s for s in result["steps"] if s["step"] == "baseline_tag")
        assert tag_step["status"] == "ok"

        # 验证 Git 仓库存在
        import subprocess

        tag_result = subprocess.run(
            ["git", "tag", "-l", "v1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "v1" in tag_result.stdout

    def test_init_project_no_name(self, git_project):
        """测试不指定项目名称"""
        result = _init_project(git_project, None)

        assert result["success"]
        # 应该使用目录名作为项目名
        assert result["project_path"] == str(git_project)

    def test_init_project_idempotent(self, git_project):
        """测试幂等性（重复初始化）"""
        # 第一次初始化
        result1 = _init_project(git_project, "测试项目")
        assert result1["success"]

        # 第二次初始化
        result2 = _init_project(git_project, "测试项目")
        assert result2["success"]

        # 检查版本索引没有被覆盖
        import json

        index_path = git_project / "版本管理" / "版本索引.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["project_name"] == "测试项目"

    def test_init_project_hooks(self, git_project):
        """测试 Git Hooks 安装"""
        result = _init_project(git_project, "测试项目")

        assert result["success"]

        # 检查 Hooks 是否安装
        hooks_step = next(s for s in result["steps"] if s["step"] == "install_hooks")
        assert hooks_step["status"] in ["ok", "warn"]

    def test_init_project_json_output(self, git_project, capsys):
        """测试 JSON 输出"""
        success = run_init_project(git_project, "测试项目", json_output=True)

        assert success

        captured = capsys.readouterr()
        import json

        output = json.loads(captured.out)
        assert output["success"]

    def test_init_project_readme(self, git_project):
        """测试 README 创建"""
        _init_project(git_project, "测试项目")

        readme_path = git_project / "版本管理" / "README.md"
        assert readme_path.exists()

        content = readme_path.read_text(encoding="utf-8")
        assert "测试项目" in content
        assert "AVM" in content

    def test_init_project_gitignore(self, git_project):
        """测试 .gitignore 创建"""
        _init_project(git_project, "测试项目")

        gitignore_path = git_project / "版本管理" / ".gitignore"
        assert gitignore_path.exists()

        content = gitignore_path.read_text(encoding="utf-8")
        assert "任务锁.json" in content
