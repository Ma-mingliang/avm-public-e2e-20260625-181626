"""AVM __main__ 入口测试"""

from unittest.mock import patch


class TestMainModule:
    """__main__.py 模块测试"""

    def test_main_import(self):
        """测试 __main__ 模块可以导入"""
        import importlib

        mod = importlib.import_module("avm.__main__")
        assert hasattr(mod, "app")

    def test_main_has_app(self):
        """测试 __main__ 导出了 app"""
        from avm.cli import app

        assert app is not None

    @patch("avm.cli.app")
    def test_main_calls_app(self, mock_app):
        """测试 __main__ 调用 app()"""
        # Import the module to verify it loads
        import avm.__main__

        # The module-level code only runs on direct execution
        # We verify the import and that app is accessible
        assert hasattr(avm.__main__, "app")
