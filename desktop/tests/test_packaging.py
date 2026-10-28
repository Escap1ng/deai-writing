"""打包清单与 frozen 路径约定。

PyInstaller 本身不在这个测试里跑（它要装包、要几分钟）；
这里验的是"清单说得对不对"：该进 bundle 的文件都在、bundle 内的相对位置
与 paths.py 在 exe 里的取法一致、命令行组装没有把用到的 Qt 模块排除掉。
"""
from __future__ import annotations

import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import deai_app
from deai_app import paths
from deai_app.bridge import engines

DESKTOP_ROOT = Path(deai_app.__file__).resolve().parent.parent
BUILD_DIR = DESKTOP_ROOT / "build"


def load_module(name: str, source: Path):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bundle = load_module("deai_build_bundle", BUILD_DIR / "bundle.py")
build = load_module("deai_build_script", BUILD_DIR / "build.py")

QT_IMPORT = re.compile(r"PySide6\.([A-Za-z0-9_]+)")


class TestBundleManifest(unittest.TestCase):
    def test_every_listed_file_exists(self) -> None:
        entries = bundle.data_files()
        self.assertGreaterEqual(len(entries), 4, "清单近乎为空，等于没打包引擎")
        for source, dest in entries:
            with self.subTest(source=source.name):
                self.assertTrue(source.is_file(), source)
                self.assertIn(dest, {bundle.CODE_DEST, bundle.ASSETS_DEST})

    def test_manifest_covers_engines_and_assets_both_ways(self) -> None:
        listed = {source.name for source, dest in bundle.data_files() if dest == bundle.CODE_DEST}
        self.assertEqual(listed, {path.name for path in engines.engine_files()})
        assets = {source.name for source, dest in bundle.data_files() if dest == bundle.ASSETS_DEST}
        on_disk = {path.name for path in paths.ASSETS_DIR.iterdir() if path.is_file()}
        self.assertEqual(assets, on_disk)
        self.assertIn("theme.json", assets)
        self.assertIn("providers.example.json", assets)

    def test_dest_paths_match_runtime_lookup(self) -> None:
        self.assertEqual(Path(bundle.ASSETS_DEST), paths.ASSETS_DIR.relative_to(DESKTOP_ROOT))
        self.assertEqual(bundle.CODE_DEST, "code")

    def test_frozen_lookup_uses_the_same_relative_place(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deai-bundle-") as tmp:
            root = Path(tmp)
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "_MEIPASS", str(root), create=True):
                with self.assertRaises(LookupError):
                    paths.require_code_dir()  # 阴性对照：没放进去就该报错
                (root / bundle.CODE_DEST).mkdir()
                self.assertEqual(paths.require_code_dir(), root / bundle.CODE_DEST)


class TestPyInstallerArgs(unittest.TestCase):
    def test_entry_script_and_window_mode(self) -> None:
        args = bundle.pyinstaller_args(onefile=False)
        self.assertEqual(Path(args[-1]), bundle.ENTRY_SCRIPT)
        self.assertIn("--windowed", args)
        self.assertIn("--name", args)
        self.assertEqual(args[args.index("--name") + 1], bundle.EXE_NAME)

    def test_onefile_and_onedir_are_exclusive(self) -> None:
        one = bundle.pyinstaller_args(onefile=True)
        many = bundle.pyinstaller_args(onefile=False)
        self.assertIn("--onefile", one)
        self.assertNotIn("--onedir", one)
        self.assertIn("--onedir", many)
        self.assertNotIn("--onefile", many)

    def test_add_data_uses_platform_separator(self) -> None:
        args = bundle.pyinstaller_args()
        pairs = [args[index + 1] for index, value in enumerate(args) if value == "--add-data"]
        self.assertEqual(len(pairs), len(bundle.data_files()))
        for pair in pairs:
            with self.subTest(pair=pair.split(os.pathsep)[0]):
                source, _, dest = pair.partition(os.pathsep)
                self.assertTrue(Path(source).is_file())
                self.assertIn(dest, {bundle.CODE_DEST, bundle.ASSETS_DEST})

    def test_excludes_keep_used_qt_modules(self) -> None:
        used = set()
        for source in sorted(paths.APP_DIR.rglob("*.py")):
            used.update(QT_IMPORT.findall(source.read_text(encoding="utf-8")))
        self.assertTrue(used, "扫描没抓到 Qt 导入，等于这条断言空转")
        self.assertTrue(used <= set(bundle.ALLOWED_QT), used)
        for module in sorted(used):
            self.assertNotIn(f"PySide6.{module}", bundle.EXCLUDES)
        self.assertIn("tkinter", bundle.EXCLUDES)
        self.assertTrue(QT_IMPORT.search("from PySide6.QtWebEngineCore import a"))


class TestBuildScript(unittest.TestCase):
    def test_dry_run_prints_command_without_running_pyinstaller(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = build.main(["--dry-run", "--onefile"])
        self.assertEqual(code, 0)
        printed = buffer.getvalue().splitlines()
        self.assertIn("-m", printed)
        self.assertIn("PyInstaller", printed)
        self.assertIn("--onefile", printed)
        self.assertIn("--add-data", printed)
        self.assertTrue(printed[-1].endswith("__main__.py"))


if __name__ == "__main__":
    unittest.main()
