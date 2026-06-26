"""AVM doctor 命令测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from avm.commands.doctor import (
    _check_gh,
    _check_git,
    _check_git_lfs,
    _check_project,
    _check_python,
    _print_results,
    run_doctor,
)


class TestCheckPython:
    """Python 检查测试"""

    def test_check_python_ok(self):
        """测试 Python 版本满足要求"""
        result = _check_python()
        assert result["name"] == "Python"
        assert result["ok"] is True
        assert "version" in result

    @patch("avm.commands.doctor.subprocess")
    def test_check_python_returns_dict(self, _mock):
        """测试返回字典结构"""
        result = _check_python()
        assert isinstance(result, dict)
        assert "name" in result
        assert "ok" in result
        assert "message" in result


class TestCheckGit:
    """Git 检查测试"""

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/git")
    @patch("avm.commands.doctor.subprocess.run")
    def test_check_git_ok(self, mock_run, mock_which):
        """测试 Git 已安装"""
        mock_run.return_value = MagicMock(stdout="git version 2.43.0", returncode=0)
        result = _check_git()
        assert result["ok"] is True
        assert result["version"] == "2.43.0"

    @patch("avm.commands.doctor.shutil.which", return_value=None)
    def test_check_git_not_installed(self, _mock):
        """测试 Git 未安装"""
        result = _check_git()
        assert result["ok"] is False
        assert "未安装" in result["message"]

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/git")
    @patch("avm.commands.doctor.subprocess.run", side_effect=Exception("timeout"))
    def test_check_git_error(self, _mock_run, _mock_which):
        """测试 Git 命令执行失败"""
        result = _check_git()
        assert result["ok"] is False
        assert "timeout" in result["message"]


class TestCheckGh:
    """GitHub CLI 检查测试"""

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/gh")
    @patch("avm.commands.doctor.subprocess.run")
    def test_check_gh_authenticated(self, mock_run, _mock):
        """测试 gh 已登录"""
        mock_run.return_value = MagicMock(
            stdout="Logged in to github.com account user",
            stderr="",
            returncode=0,
        )
        result = _check_gh()
        assert result["ok"] is True
        assert "已登录" in result["message"]

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/gh")
    @patch("avm.commands.doctor.subprocess.run")
    def test_check_gh_not_authenticated(self, mock_run, _mock):
        """测试 gh 未登录"""
        mock_run.return_value = MagicMock(stdout="", stderr="Not logged in", returncode=1)
        result = _check_gh()
        assert result["ok"] is False
        assert "未登录" in result["message"]

    @patch("avm.commands.doctor.shutil.which", return_value=None)
    def test_check_gh_not_installed(self, _mock):
        """测试 gh 未安装"""
        result = _check_gh()
        assert result["ok"] is False
        assert "未安装" in result["message"]

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/gh")
    @patch("avm.commands.doctor.subprocess.run", side_effect=Exception("timeout"))
    def test_check_gh_error(self, _mock_run, _mock):
        """测试 gh 命令执行失败"""
        result = _check_gh()
        assert result["ok"] is False


class TestCheckGitLfs:
    """Git LFS 检查测试"""

    @patch("avm.commands.doctor.shutil.which", return_value="/usr/bin/git-lfs")
    def test_check_git_lfs_installed(self, _mock):
        """测试 Git LFS 已安装"""
        result = _check_git_lfs()
        assert result["ok"] is True

    @patch("avm.commands.doctor.shutil.which", return_value=None)
    @patch("avm.commands.doctor.subprocess.run")
    def test_check_git_lfs_via_git(self, mock_run, _mock):
        """测试通过 git lfs 检测"""
        mock_run.return_value = MagicMock(returncode=0)
        result = _check_git_lfs()
        assert result["ok"] is True

    @patch("avm.commands.doctor.shutil.which", return_value=None)
    @patch("avm.commands.doctor.subprocess.run", side_effect=Exception("not found"))
    def test_check_git_lfs_not_installed(self, _mock_run, _mock):
        """测试 Git LFS 未安装"""
        result = _check_git_lfs()
        assert result["ok"] is False
        assert "未安装" in result["message"]

    @patch("avm.commands.doctor.shutil.which", return_value=None)
    @patch("avm.commands.doctor.subprocess.run")
    def test_check_git_lfs_git_lfs_fails(self, mock_run, _mock):
        """测试 git lfs 命令失败"""
        mock_run.return_value = MagicMock(returncode=1)
        result = _check_git_lfs()
        assert result["ok"] is False


class TestCheckProject:
    """项目检查测试"""

    def test_check_project_not_exists(self, tmp_path):
        """测试项目路径不存在"""
        result = _check_project(tmp_path / "nonexistent")
        assert result["ok"] is False
        assert "不存在" in result["message"]

    def test_check_project_not_git(self, tmp_path):
        """测试非 Git 仓库"""
        tmp_path.mkdir(exist_ok=True)
        result = _check_project(tmp_path)
        assert result["ok"] is False
        assert "Git" in result["message"]

    def test_check_project_git_not_initialized(self, tmp_path):
        """测试 Git 仓库但未初始化 AVM"""
        (tmp_path / ".git").mkdir()
        result = _check_project(tmp_path)
        assert result["ok"] is True
        assert result["initialized"] is False

    def test_check_project_initialized(self, tmp_path):
        """测试已初始化的项目"""
        (tmp_path / ".git").mkdir()
        version_dir = tmp_path / "版本管理"
        version_dir.mkdir()
        (version_dir / "配置.yaml").write_text("project:\n  name: test", encoding="utf-8")
        result = _check_project(tmp_path)
        assert result["ok"] is True
        assert result["initialized"] is True


class TestRunDoctor:
    """doctor 命令集成测试"""

    @patch(
        "avm.commands.doctor._check_project",
        return_value={"name": "项目", "ok": True, "initialized": True, "message": "OK"},
    )
    @patch("avm.commands.doctor._check_git_lfs", return_value={"name": "Git LFS", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_gh", return_value={"name": "GitHub CLI", "ok": True, "message": "OK"})
    @patch(
        "avm.commands.doctor._check_git", return_value={"name": "Git", "ok": True, "version": "2.43.0", "message": "OK"}
    )
    @patch(
        "avm.commands.doctor._check_python",
        return_value={"name": "Python", "ok": True, "version": "3.12.0", "message": "OK"},
    )
    def test_doctor_all_ok(self, *mocks):
        """测试所有检查通过"""
        result = run_doctor(Path("/tmp"))
        assert result is True

    @patch("avm.commands.doctor._check_project", return_value={"name": "项目", "ok": False, "message": "不是Git仓库"})
    @patch("avm.commands.doctor._check_git_lfs", return_value={"name": "Git LFS", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_gh", return_value={"name": "GitHub CLI", "ok": True, "message": "OK"})
    @patch(
        "avm.commands.doctor._check_git", return_value={"name": "Git", "ok": True, "version": "2.43.0", "message": "OK"}
    )
    @patch(
        "avm.commands.doctor._check_python",
        return_value={"name": "Python", "ok": True, "version": "3.12.0", "message": "OK"},
    )
    def test_doctor_project_fail(self, *mocks):
        """测试项目检查失败"""
        result = run_doctor(Path("/tmp"))
        assert result is False

    @patch("avm.commands.doctor._check_project", return_value={"name": "项目", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_git_lfs", return_value={"name": "Git LFS", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_gh", return_value={"name": "GitHub CLI", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_git", return_value={"name": "Git", "ok": True, "message": "OK"})
    @patch("avm.commands.doctor._check_python", return_value={"name": "Python", "ok": True, "message": "OK"})
    def test_doctor_json_output(self, _p, _g, _gh, _lfs, _proj, capsys):
        """测试 JSON 输出"""
        result = run_doctor(Path("/tmp"), json_output=True)
        assert result is True
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "python" in data
        assert "git" in data


class TestPrintResults:
    """打印结果测试"""

    def test_print_results(self):
        """测试打印结果不报错"""
        results = {
            "python": {"name": "Python", "ok": True, "version": "3.12.0", "message": "OK"},
            "git": {"name": "Git", "ok": False, "message": "未安装"},
        }
        # 不应抛出异常
        _print_results(results)
