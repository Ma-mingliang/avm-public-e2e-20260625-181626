"""AVM GitHub 客户端测试"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from avm.exceptions import GitHubError
from avm.github.client import GitHubClient


@pytest.fixture
def mock_gh():
    """模拟 gh CLI"""
    with patch("avm.github.client.subprocess.run") as mock_run:
        yield mock_run


class TestGitHubClient:
    """GitHub 客户端测试"""

    def test_detect_repo(self, mock_gh):
        """测试仓库检测"""
        mock_gh.return_value = MagicMock(
            returncode=0,
            stdout='{"owner": {"login": "testuser"}, "name": "testrepo"}',
        )

        client = GitHubClient()
        assert client.repo_owner == "testuser"
        assert client.repo_name == "testrepo"

    def test_detect_repo_manual(self):
        """测试手动指定仓库"""
        client = GitHubClient(repo_owner="myuser", repo_name="myrepo")
        assert client.repo_owner == "myuser"
        assert client.repo_name == "myrepo"

    def test_create_pull_request(self, mock_gh):
        """测试创建 PR"""
        # 第一次调用：创建 PR
        mock_gh.side_effect = [
            MagicMock(returncode=0, stdout="https://github.com/testuser/testrepo/pull/1"),
            MagicMock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "number": 1,
                        "title": "Test PR",
                        "state": "OPEN",
                        "url": "https://github.com/testuser/testrepo/pull/1",
                        "headRefName": "feature",
                        "baseRefName": "main",
                    }
                ),
            ),
        ]

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        pr = client.create_pull_request(
            title="Test PR",
            body="Test body",
            head="feature",
            base="main",
        )

        assert pr["number"] == 1
        assert pr["title"] == "Test PR"

    @patch("urllib.request.urlopen")
    def test_create_pull_request_falls_back_to_rest_after_gh_failure(self, mock_urlopen, mock_gh):
        """gh TLS 失败时，使用现有登录凭据通过 REST 创建 PR。"""
        mock_gh.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="TLS handshake timeout"),
            MagicMock(returncode=0, stdout="token-from-gh\n", stderr=""),
        ]
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"number": 7, "html_url": "https://github.com/testuser/testrepo/pull/7", "state": "open"}
        ).encode()
        mock_urlopen.return_value.__enter__.return_value = response

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        pr = client.create_pull_request("Test PR", "Test body", "feature")

        assert pr["number"] == 7
        assert pr["html_url"] == "https://github.com/testuser/testrepo/pull/7"
        request = mock_urlopen.call_args.args[0]
        assert request.full_url.endswith("/repos/testuser/testrepo/pulls")
        assert request.method == "POST"

    @patch("urllib.request.urlopen")
    def test_create_pull_request_reuses_existing_rest_pr_after_gh_view_failure(self, mock_urlopen, mock_gh):
        """gh 创建后查询失败时，REST 必须复用同源分支的开放 PR。"""
        mock_gh.side_effect = [
            MagicMock(returncode=0, stdout="https://github.com/testuser/testrepo/pull/8\n", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="TLS handshake timeout"),
            MagicMock(returncode=0, stdout="token-from-gh\n", stderr=""),
        ]
        response = MagicMock()
        response.read.return_value = json.dumps(
            [{"number": 8, "html_url": "https://github.com/testuser/testrepo/pull/8", "head": {"ref": "feature"}}]
        ).encode()
        mock_urlopen.return_value.__enter__.return_value = response

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        pr = client.create_pull_request("Test PR", "Test body", "feature")

        assert pr["number"] == 8
        assert mock_urlopen.call_count == 1
        assert mock_urlopen.call_args.args[0].method == "GET"

    @patch("urllib.request.urlopen", side_effect=OSError("network unavailable"))
    def test_create_pull_request_fails_closed_when_rest_fallback_fails(self, _mock_urlopen, mock_gh):
        """gh 与 REST 都失败时，创建 PR 必须失败闭合。"""
        mock_gh.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="TLS handshake timeout"),
            MagicMock(returncode=0, stdout="token-from-gh\n", stderr=""),
        ]
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")

        with pytest.raises(GitHubError, match="REST"):
            client.create_pull_request("Test PR", "Test body", "feature")

    def test_merge_pull_request(self, mock_gh):
        """测试合并 PR"""
        mock_gh.return_value = MagicMock(returncode=0, stdout="")

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        result = client.merge_pull_request(1, merge_method="squash")

        assert result["merged"] is True
        assert result["method"] == "squash"

    def test_create_tag(self, mock_gh):
        """测试创建标签"""
        mock_gh.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
        ]

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        result = client.create_tag("v1", "版本1")

        assert result["tag"] == "v1"
        assert result["message"] == "版本1"

    def test_create_release(self, mock_gh):
        """测试创建发布"""
        mock_gh.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/testuser/testrepo/releases/tag/v1",
        )

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        result = client.create_release("v1", "版本1", "发布描述")

        assert result["tag"] == "v1"
        assert result["title"] == "版本1"
        assert "url" in result

    def test_create_reference(self, mock_gh):
        """测试创建引用（远程锁）"""
        mock_gh.return_value = MagicMock(returncode=0, stdout="{}")

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.create_reference("refs/heads/avm/lock", "abc123")

    def test_create_reference_already_exists(self, mock_gh):
        """测试创建已存在的引用"""
        mock_gh.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="HTTP 422: Reference already exists",
        )

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert not client.create_reference("refs/heads/avm/lock", "abc123")

    def test_delete_reference(self, mock_gh):
        """测试删除引用"""
        mock_gh.return_value = MagicMock(returncode=0, stdout="")

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.delete_reference("refs/heads/avm/lock")

    def test_get_reference(self, mock_gh):
        """测试获取引用"""
        mock_gh.return_value = MagicMock(
            returncode=0,
            stdout='{"object": {"sha": "abc123def456"}}',
        )

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        sha = client.get_reference("refs/heads/main")

        assert sha == "abc123def456"

    def test_get_reference_not_found(self, mock_gh):
        """测试获取不存在的引用"""
        mock_gh.return_value = MagicMock(returncode=1, stdout="", stderr="Not Found")

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.get_reference("refs/heads/nonexistent") is None

    def test_gh_not_installed(self, mock_gh):
        """测试 gh 未安装"""
        mock_gh.side_effect = FileNotFoundError()

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        with pytest.raises(GitHubError) as exc_info:
            client.create_pull_request("title", "body", "feature")
        assert "未安装" in str(exc_info.value)

    def test_gh_timeout(self, mock_gh):
        """测试 gh 超时"""
        mock_gh.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=60)

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        with pytest.raises(GitHubError) as exc_info:
            client.create_pull_request("title", "body", "feature")
        assert "超时" in str(exc_info.value)

    def test_list_workflow_runs(self, mock_gh):
        """测试列出工作流运行"""
        mock_gh.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "headBranch": "main",
                        "createdAt": "2024-01-01",
                    }
                ]
            ),
        )

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        runs = client.list_workflow_runs("ci.yml")

        assert len(runs) == 1
        assert runs[0]["status"] == "completed"

    def test_get_repo_info(self, mock_gh):
        """测试获取仓库信息"""
        mock_gh.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "name": "testrepo",
                    "owner": {"login": "testuser"},
                    "description": "Test",
                    "defaultBranchRef": {"name": "main"},
                    "isPrivate": True,
                }
            ),
        )

        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        info = client.get_repo_info()

        assert info["name"] == "testrepo"
        assert info["isPrivate"] is True


class TestMergePullRequestSHA:
    def test_merge_returns_merge_sha(self, mock_gh):
        mock_merge = MagicMock(returncode=0, stdout="")
        mock_pr_view = MagicMock(returncode=0, stdout=json.dumps({"mergeCommit": {"oid": "abc123def456"}}))

        def side_effect(*args, **kwargs):
            call_args = args[0] if args else kwargs.get("args", [])
            if "view" in call_args:
                return mock_pr_view
            return mock_merge

        mock_gh.side_effect = side_effect
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        result = client.merge_pull_request(1)
        assert result["merged"] is True
        assert result["merge_commit_sha"] == "abc123def456"

    def test_merge_sha_fallback(self, mock_gh):
        mock_merge = MagicMock(returncode=0, stdout="")
        mock_pr_view = MagicMock(returncode=1, stdout="")

        def side_effect(*args, **kwargs):
            call_args = args[0] if args else kwargs.get("args", [])
            if "view" in call_args:
                return mock_pr_view
            return mock_merge

        mock_gh.side_effect = side_effect
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        result = client.merge_pull_request(1)
        assert result["merge_commit_sha"] == ""


class TestNewMethods:
    def test_get_commit_sha(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=0, stdout=json.dumps({"sha": "abc123"}))
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.get_commit_sha("abc123") == "abc123"

    def test_get_commit_sha_not_found(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=1, stdout="", stderr="Not Found")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.get_commit_sha("nonexistent") is None

    def test_get_commit_sha_exception(self, mock_gh):
        mock_gh.side_effect = Exception("network error")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.get_commit_sha("abc123") is None

    def test_tag_exists(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=0, stdout="{}")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.tag_exists("v1") is True

    def test_tag_not_exists(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=1, stderr="Not Found")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.tag_exists("v999") is False

    def test_tag_exists_exception(self, mock_gh):
        mock_gh.side_effect = Exception("error")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.tag_exists("v1") is False

    def test_release_exists(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=0, stdout="{}")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.release_exists("v1") is True

    def test_release_not_exists(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=1, stderr="Not Found")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.release_exists("v999") is False

    def test_release_exists_exception(self, mock_gh):
        mock_gh.side_effect = Exception("error")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.release_exists("v1") is False

    def test_delete_branch(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=0, stdout="")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.delete_branch("feature") is True

    def test_delete_branch_failure(self, mock_gh):
        mock_gh.return_value = MagicMock(returncode=1, stderr="Not Found")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.delete_branch("feature") is False

    def test_delete_branch_exception(self, mock_gh):
        mock_gh.side_effect = Exception("error")
        client = GitHubClient(repo_owner="testuser", repo_name="testrepo")
        assert client.delete_branch("feature") is False
