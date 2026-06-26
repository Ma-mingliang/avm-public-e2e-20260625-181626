"""AVM 哈希工具测试"""

import pytest

from avm.core.hashing import (
    compute_approval_hash,
    compute_bytes_sha256,
    compute_file_sha256,
    compute_hmac_signature,
    compute_manifest_hash,
    compute_string_sha256,
    generate_random_key,
    short_hash,
    verify_hmac_signature,
)


class TestSHA256:
    """SHA-256 测试"""

    def test_compute_string_sha256(self):
        """测试字符串SHA-256"""
        hash1 = compute_string_sha256("hello")
        hash2 = compute_string_sha256("hello")
        hash3 = compute_string_sha256("world")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64

    def test_compute_bytes_sha256(self):
        """测试字节SHA-256"""
        hash1 = compute_bytes_sha256(b"hello")
        hash2 = compute_string_sha256("hello")

        assert hash1 == hash2

    def test_compute_file_sha256(self, tmp_path):
        """测试文件SHA-256"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello", encoding="utf-8")

        hash1 = compute_file_sha256(test_file)
        hash2 = compute_file_sha256(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_compute_file_sha256_different_files(self, tmp_path):
        """测试不同文件的SHA-256"""
        file1 = tmp_path / "test1.txt"
        file1.write_text("hello", encoding="utf-8")

        file2 = tmp_path / "test2.txt"
        file2.write_text("world", encoding="utf-8")

        hash1 = compute_file_sha256(file1)
        hash2 = compute_file_sha256(file2)

        assert hash1 != hash2

    def test_compute_file_sha256_not_found(self, tmp_path):
        """测试不存在的文件"""
        with pytest.raises(FileNotFoundError):
            compute_file_sha256(tmp_path / "nonexistent.txt")


class TestManifestHash:
    """清单哈希测试"""

    def test_compute_manifest_hash(self):
        """测试清单哈希"""
        parts = ["part1", "part2", "part3"]
        hash1 = compute_manifest_hash(parts)
        hash2 = compute_manifest_hash(parts)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_manifest_hash_order_matters(self):
        """测试清单哈希顺序敏感"""
        hash1 = compute_manifest_hash(["a", "b", "c"])
        hash2 = compute_manifest_hash(["c", "b", "a"])

        assert hash1 != hash2


class TestHMAC:
    """HMAC 测试"""

    def test_compute_and_verify(self):
        """测试HMAC计算和验证"""
        key = generate_random_key()
        message = "test message"

        signature = compute_hmac_signature(key, message)
        assert verify_hmac_signature(key, message, signature)

    def test_verify_wrong_message(self):
        """测试错误消息验证"""
        key = generate_random_key()
        message = "test message"

        signature = compute_hmac_signature(key, message)
        assert not verify_hmac_signature(key, "wrong message", signature)

    def test_verify_wrong_key(self):
        """测试错误密钥验证"""
        key1 = generate_random_key()
        key2 = generate_random_key()
        message = "test message"

        signature = compute_hmac_signature(key1, message)
        assert not verify_hmac_signature(key2, message, signature)

    def test_generate_random_key(self):
        """测试随机密钥生成"""
        key1 = generate_random_key()
        key2 = generate_random_key()

        assert len(key1) == 32
        assert key1 != key2


class TestApprovalHash:
    """审批哈希测试"""

    def test_compute_approval_hash(self):
        """测试审批哈希"""
        hash1 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[{"path": "src/main.py", "sha256": "def456"}],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )
        hash2 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[{"path": "src/main.py", "sha256": "def456"}],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )

        assert hash1 == hash2

    def test_approval_hash_different_files(self):
        """测试不同文件的审批哈希"""
        hash1 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[{"path": "src/main.py", "sha256": "def456"}],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )
        hash2 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[{"path": "src/other.py", "sha256": "def456"}],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )

        assert hash1 != hash2

    def test_approval_hash_sorted_files(self):
        """测试审批哈希文件排序"""
        hash1 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[
                {"path": "src/b.py", "sha256": "hash_b"},
                {"path": "src/a.py", "sha256": "hash_a"},
            ],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )
        hash2 = compute_approval_hash(
            base_commit="abc123",
            file_manifest=[
                {"path": "src/a.py", "sha256": "hash_a"},
                {"path": "src/b.py", "sha256": "hash_b"},
            ],
            commit_message_hash="hash1",
            pr_body_hash="hash2",
            release_body_hash="hash3",
            config_hash="hash4",
        )

        assert hash1 == hash2


class TestShortHash:
    """短哈希测试"""

    def test_short_hash(self):
        """测试短哈希"""
        full_hash = "a" * 64
        short = short_hash(full_hash)

        assert len(short) == 8
        assert short == "aaaaaaaa"

    def test_short_hash_custom_length(self):
        """测试自定义长度短哈希"""
        full_hash = "a" * 64
        short = short_hash(full_hash, length=12)

        assert len(short) == 12
