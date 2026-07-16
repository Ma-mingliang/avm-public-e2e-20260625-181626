"""发布包元数据完整性测试。"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_declared_license_file_exists():
    assert (REPO_ROOT / "LICENSE").is_file()


def test_readme_has_no_placeholder_e2e_heading():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert not text.rstrip().endswith("# E2E test")
