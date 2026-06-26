"""AVM 任务分类器

根据文件变更模式和上下文确定任务类型：
- MANDATORY_PROJECT_VERSION: 代码变更，需要项目版本号
- OPTIONAL_DOCUMENT_VERSION: 仅文档变更，可选文档版本号
- READ_ONLY: 只读操作，无需版本
- BLOCKED_UNCLEAR: 无法确定或被阻断
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import ProjectConfig, TaskType

# 文档文件扩展名
DOCUMENT_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".doc",
    ".docx",
    ".pdf",
    ".html",
    ".htm",
    ".adoc",
    ".tex",
    ".latex",
    ".csv",
}

# 配置文件扩展名
CONFIG_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".env.example",
    ".env.local",
}

# 代码文件扩展名
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".vue",
    ".svelte",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".fs",
    ".rb",
    ".php",
    ".swift",
    ".dart",
    ".lua",
    ".r",
    ".m",
    ".mm",
    ".ex",
    ".exs",
    ".erl",
    ".hs",
    ".clj",
    ".cljs",
    ".lisp",
    ".el",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".sql",
    ".graphql",
    ".proto",
}

# 高风险路径模式
HIGH_RISK_PATTERNS = [
    "src/",
    "lib/",
    "app/",
    "cmd/",
    "internal/",
    "pkg/",
    "bin/",
    "scripts/",
    "tools/",
]


class TaskClassifier:
    """任务分类器"""

    def __init__(self, config: ProjectConfig | None = None):
        self.config = config

    def classify(
        self,
        changed_files: list[str],
        task_description: str = "",
        base_path: Path | None = None,
    ) -> TaskType:
        """分类任务类型

        Args:
            changed_files: 变更文件列表（相对于项目根目录的路径）
            task_description: 任务描述文本
            base_path: 项目根路径（用于检查文件是否存在）

        Returns:
            任务类型
        """
        if not changed_files:
            return TaskType.READ_ONLY

        # 分析文件类型
        analysis = self._analyze_files(changed_files, base_path)

        # 决策逻辑
        return self._decide(analysis, task_description)

    def _analyze_files(
        self,
        files: list[str],
        base_path: Path | None,
    ) -> dict[str, Any]:
        """分析文件列表"""
        code_files: list[str] = []
        doc_files: list[str] = []
        config_files: list[str] = []
        other_files: list[str] = []
        high_risk_files: list[str] = []
        missing_files: list[str] = []

        for f in files:
            p = Path(f)
            ext = p.suffix.lower()

            # 检查文件是否存在
            if base_path and not (base_path / f).exists():
                missing_files.append(f)

            # 分类
            if ext in CODE_EXTENSIONS:
                code_files.append(f)
            elif ext in DOCUMENT_EXTENSIONS:
                doc_files.append(f)
            elif ext in CONFIG_EXTENSIONS:
                config_files.append(f)
            else:
                other_files.append(f)

            # 高风险路径检查
            for pattern in HIGH_RISK_PATTERNS:
                if f.startswith(pattern):
                    high_risk_files.append(f)
                    break

            # 自定义高风险路径
            if self.config and self.config.risk.high_risk_paths:
                for pattern in self.config.risk.high_risk_paths:
                    if pattern and f.startswith(pattern):
                        if f not in high_risk_files:
                            high_risk_files.append(f)

        return {
            "code_files": code_files,
            "doc_files": doc_files,
            "config_files": config_files,
            "other_files": other_files,
            "high_risk_files": high_risk_files,
            "missing_files": missing_files,
            "total": len(files),
        }

    def _decide(self, analysis: dict, task_description: str) -> TaskType:
        """根据分析结果决定任务类型

        决策优先级：
        1. 缺失文件 → 阻断
        2. 任务描述明确为文档目的 → 文档版本（最终目的优先）
        3. 项目根级 README/文档 → 项目版本（不可变规则）
        4. 纯文档文件 → 文档版本
        5. 有代码/配置文件 → 项目版本
        6. 其他 → 阻断
        """
        code_count = len(analysis["code_files"])
        doc_count = len(analysis["doc_files"])
        config_count = len(analysis["config_files"])
        other_count = len(analysis["other_files"])
        missing_count = len(analysis["missing_files"])

        # 有缺失文件 -> 阻断
        if missing_count > 0:
            return TaskType.BLOCKED_UNCLEAR

        # 检查任务描述是否明确为文档任务
        doc_keywords = {"文档", "文档版本", "doc", "document", "readme", "说明", "手册", "指南"}
        is_doc_task = any(kw in task_description.lower() for kw in doc_keywords)

        # 检查是否为项目根级文档（README、CHANGELOG 等）——只检查真正位于项目根目录的文件
        root_docs = {"readme.md", "readme.txt", "readme.rst", "changelog.md", "contributing.md", "license.md"}
        has_root_doc = any(Path(f).name.lower() in root_docs and len(Path(f).parts) == 1 for f in analysis["doc_files"])

        # 任务描述明确为文档目的（最终目的优先）→ 文档版本
        # 即使包含代码文件，只要任务目的是处理文档，就按文档任务分类
        if is_doc_task:
            if has_root_doc:
                # 项目根级文档变更需要项目版本
                return TaskType.MANDATORY_PROJECT_VERSION
            return TaskType.OPTIONAL_DOCUMENT_VERSION

        # 纯文档文件且非项目根级文档
        if code_count == 0 and config_count == 0 and other_count == 0 and doc_count > 0:
            if has_root_doc:
                return TaskType.MANDATORY_PROJECT_VERSION
            return TaskType.OPTIONAL_DOCUMENT_VERSION

        # 有代码文件 -> 项目版本
        if code_count > 0:
            return TaskType.MANDATORY_PROJECT_VERSION

        # 只有配置文件 -> 项目版本（配置变更也需要版本管理）
        if config_count > 0 and code_count == 0:
            return TaskType.MANDATORY_PROJECT_VERSION

        # 其他情况 -> 无法确定
        return TaskType.BLOCKED_UNCLEAR

    def get_risk_summary(self, changed_files: list[str], base_path: Path | None = None) -> dict:
        """获取风险摘要

        Args:
            changed_files: 变更文件列表
            base_path: 项目根路径

        Returns:
            风险摘要字典
        """
        analysis = self._analyze_files(changed_files, base_path)

        extra_file_limit = 5
        if self.config:
            extra_file_limit = self.config.risk.extra_file_limit

        risks = []
        warnings = []

        # 检查文件数量
        if analysis["total"] > extra_file_limit:
            warnings.append(f"变更文件数 ({analysis['total']}) 超过限制 ({extra_file_limit})")

        # 检查高风险文件
        if analysis["high_risk_files"]:
            risks.append(f"包含高风险路径文件: {', '.join(analysis['high_risk_files'][:3])}")

        # 检查缺失文件
        if analysis["missing_files"]:
            risks.append(f"文件不存在: {', '.join(analysis['missing_files'][:3])}")

        return {
            "task_type": self._decide(analysis, "").value,
            "code_files": len(analysis["code_files"]),
            "doc_files": len(analysis["doc_files"]),
            "config_files": len(analysis["config_files"]),
            "other_files": len(analysis["other_files"]),
            "high_risk_files": len(analysis["high_risk_files"]),
            "missing_files": len(analysis["missing_files"]),
            "risks": risks,
            "warnings": warnings,
        }
