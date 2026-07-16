"""发布事实对账测试。"""

from unittest.mock import MagicMock

import pytest

from avm.core.publish_saga import PublishSaga, extract_manifest_hash
from avm.exceptions import PublishConflictError, PublishError

MANIFEST_HASH = "a" * 64


def test_existing_matching_tag_is_idempotent():
    github = MagicMock()
    github.get_tag_target.return_value = "merge-sha"
    git = MagicMock()

    PublishSaga(github, git).ensure_tag("v2", "merge-sha")

    git.create_annotated_tag.assert_not_called()
    git.push_tag.assert_not_called()


def test_existing_wrong_tag_blocks_publish():
    github = MagicMock()
    github.get_tag_target.return_value = "other-sha"

    with pytest.raises(PublishConflictError, match="不同提交"):
        PublishSaga(github, MagicMock()).ensure_tag("v2", "merge-sha")


def test_extract_manifest_hash_rejects_missing_value():
    assert extract_manifest_hash("no manifest") == ""
    assert extract_manifest_hash(f'{{"manifest_hash": "{MANIFEST_HASH}"}}') == MANIFEST_HASH


def test_push_response_loss_accepts_observed_remote_tag():
    github = MagicMock()
    github.get_tag_target.side_effect = [None, "merge-sha"]
    git = MagicMock()
    git.create_annotated_tag.return_value = True
    git.push_tag.return_value = False

    PublishSaga(github, git).ensure_tag("v2", "merge-sha")


def test_push_failure_without_remote_fact_is_error():
    github = MagicMock()
    github.get_tag_target.side_effect = [None, None]
    git = MagicMock()
    git.create_annotated_tag.return_value = True
    git.push_tag.return_value = False

    with pytest.raises(PublishError, match="远端事实不一致"):
        PublishSaga(github, git).ensure_tag("v2", "merge-sha")


def test_existing_matching_release_is_idempotent():
    github = MagicMock()
    github.get_release.return_value = {
        "body": f'{{"manifest_hash": "{MANIFEST_HASH}"}}',
        "url": "https://example.invalid/v2",
    }

    url = PublishSaga(github, MagicMock()).ensure_release("v2", "Release v2", "body", MANIFEST_HASH)

    assert url == "https://example.invalid/v2"
    github.create_release.assert_not_called()


def test_existing_conflicting_release_is_blocked():
    github = MagicMock()
    github.get_release.return_value = {
        "body": f'{{"manifest_hash": "{"b" * 64}"}}',
        "url": "https://example.invalid/v2",
    }

    with pytest.raises(PublishConflictError, match="manifest 冲突"):
        PublishSaga(github, MagicMock()).ensure_release("v2", "Release v2", "body", MANIFEST_HASH)


def test_invalid_create_release_response_is_error():
    github = MagicMock()
    github.get_release.return_value = None
    github.create_release.return_value = "unexpected"

    with pytest.raises(PublishError, match="响应格式"):
        PublishSaga(github, MagicMock()).ensure_release("v2", "Release v2", "body", MANIFEST_HASH)


def test_non_string_tag_observation_is_treated_as_absent():
    github = MagicMock()
    github.get_tag_target.return_value = MagicMock()
    git = MagicMock()
    git.create_annotated_tag.return_value = True
    git.push_tag.return_value = True

    PublishSaga(github, git).ensure_tag("v2", "merge-sha")

    git.push_tag.assert_called_once_with("v2")


def test_existing_matching_local_tag_can_be_pushed():
    github = MagicMock()
    github.get_tag_target.return_value = None
    git = MagicMock()
    git.create_annotated_tag.return_value = False
    git._run_git.return_value = MagicMock(returncode=0, stdout="merge-sha\n")
    git.push_tag.return_value = True

    PublishSaga(github, git).ensure_tag("v2", "merge-sha")


def test_conflicting_local_tag_blocks_publish():
    github = MagicMock()
    github.get_tag_target.return_value = None
    git = MagicMock()
    git.create_annotated_tag.return_value = False
    git._run_git.return_value = MagicMock(returncode=0, stdout="other\n")

    with pytest.raises(PublishError, match="创建本地标签失败"):
        PublishSaga(github, git).ensure_tag("v2", "merge-sha")


def test_non_mapping_release_observation_is_recreated_with_html_url():
    github = MagicMock()
    github.get_release.return_value = MagicMock()
    github.create_release.return_value = {"html_url": "https://example.invalid/v2"}

    assert (
        PublishSaga(github, MagicMock()).ensure_release("v2", "Release v2", "body", MANIFEST_HASH)
        == "https://example.invalid/v2"
    )
