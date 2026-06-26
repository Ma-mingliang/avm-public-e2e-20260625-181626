"""AVM 任务分类器测试"""

import pytest

from avm.core.classifier import TaskClassifier
from avm.models import ProjectConfig, ProjectInfo, TaskType


@pytest.fixture
def classifier():
    return TaskClassifier()


@pytest.fixture
def config_classifier():
    config = ProjectConfig(
        project=ProjectInfo(name="test", root="."),
    )
    return TaskClassifier(config)


class TestTaskClassifier:
    """任务分类器测试"""

    def test_empty_files_returns_read_only(self, classifier):
        """空文件列表返回只读"""
        result = classifier.classify([])
        assert result == TaskType.READ_ONLY

    def test_code_files_returns_mandatory(self, classifier, tmp_path):
        """代码文件返回项目版本"""
        # 创建临时文件
        (tmp_path / "main.py").write_text("print('hello')")
        result = classifier.classify(["main.py"], base_path=tmp_path)
        assert result == TaskType.MANDATORY_PROJECT_VERSION

    def test_doc_files_returns_optional(self, classifier, tmp_path):
        """纯非根级文档文件返回文档版本"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text("# Guide")
        result = classifier.classify(["docs/guide.md"], base_path=tmp_path)
        assert result == TaskType.OPTIONAL_DOCUMENT_VERSION

    def test_root_readme_returns_mandatory(self, classifier, tmp_path):
        """项目根级 README 变更需要项目版本"""
        (tmp_path / "README.md").write_text("# Hello")
        result = classifier.classify(["README.md"], base_path=tmp_path)
        assert result == TaskType.MANDATORY_PROJECT_VERSION

    def test_nested_readme_not_root_doc(self, classifier, tmp_path):
        """非根目录的 README 不应被当作项目根级文档"""
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        (notes_dir / "README.md").write_text("# Notes")
        result = classifier.classify(["notes/README.md"], base_path=tmp_path)
        assert result == TaskType.OPTIONAL_DOCUMENT_VERSION

    def test_doc_purpose_task_with_code_files(self, classifier, tmp_path):
        """任务描述明确为文档目的时，即使包含代码文件也按文档任务分类"""
        (tmp_path / "convert.py").write_text("import docx")
        result = classifier.classify(
            ["convert.py"],
            task_description="修改 Python 脚本以处理 Word 文档",
            base_path=tmp_path,
        )
        assert result == TaskType.OPTIONAL_DOCUMENT_VERSION

    def test_mixed_files_returns_mandatory(self, classifier, tmp_path):
        """混合文件返回项目版本"""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Hello")
        result = classifier.classify(["main.py", "README.md"], base_path=tmp_path)
        assert result == TaskType.MANDATORY_PROJECT_VERSION

    def test_config_files_returns_mandatory(self, classifier, tmp_path):
        """配置文件返回项目版本"""
        (tmp_path / "config.json").write_text("{}")
        result = classifier.classify(["config.json"], base_path=tmp_path)
        assert result == TaskType.MANDATORY_PROJECT_VERSION

    def test_missing_files_returns_blocked(self, classifier, tmp_path):
        """缺失文件返回阻断"""
        result = classifier.classify(["nonexistent.py"], base_path=tmp_path)
        assert result == TaskType.BLOCKED_UNCLEAR

    def test_multiple_doc_files(self, classifier, tmp_path):
        """多个文档文件返回文档版本"""
        (tmp_path / "doc1.md").write_text("# Doc 1")
        (tmp_path / "doc2.txt").write_text("Doc 2")
        result = classifier.classify(["doc1.md", "doc2.txt"], base_path=tmp_path)
        assert result == TaskType.OPTIONAL_DOCUMENT_VERSION

    def test_various_code_extensions(self, classifier, tmp_path):
        """各种代码扩展名"""
        for ext in [".py", ".js", ".ts", ".go", ".rs", ".java"]:
            (tmp_path / f"file{ext}").write_text("")
            result = classifier.classify([f"file{ext}"], base_path=tmp_path)
            assert result == TaskType.MANDATORY_PROJECT_VERSION

    def test_various_doc_extensions(self, classifier, tmp_path):
        """各种文档扩展名"""
        for ext in [".md", ".txt", ".rst", ".doc", ".docx", ".pdf"]:
            (tmp_path / f"file{ext}").write_text("")
            result = classifier.classify([f"file{ext}"], base_path=tmp_path)
            assert result == TaskType.OPTIONAL_DOCUMENT_VERSION

    def test_risk_summary(self, classifier, tmp_path):
        """风险摘要"""
        (tmp_path / "main.py").write_text("print('hello')")
        summary = classifier.get_risk_summary(["main.py"], tmp_path)
        assert summary["task_type"] == "MANDATORY_PROJECT_VERSION"
        assert summary["code_files"] == 1
        assert summary["doc_files"] == 0

    def test_high_risk_files(self, classifier, tmp_path):
        """高风险路径文件"""
        (tmp_path / "src" / "main.py").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        summary = classifier.get_risk_summary(["src/main.py"], tmp_path)
        assert summary["high_risk_files"] == 1
