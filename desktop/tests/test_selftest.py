"""exe 自检入口：无界面、无 stdout 也能给出结论。

真实 PyInstaller 构建不在这里跑；这里验自检项本身会通过、坏掉时会失败，
以及 windowed 环境（stdout=None）与 --out 落盘的行为。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import deai_app
from deai_app import __main__ as entry
from deai_app.core import selftest

DESKTOP_ROOT = Path(deai_app.__file__).resolve().parent.parent
CHECK_NAMES = ["词表级", "结构级", "字符级", "主题", "示例配置"]


class TestSelftest(unittest.TestCase):
    def test_all_checks_pass_in_source_tree(self) -> None:
        items = selftest.run()
        self.assertEqual([item.name for item in items], CHECK_NAMES)
        self.assertTrue(selftest.ok(items), selftest.render(items))

    def test_negative_control_flips_an_item(self) -> None:
        with mock.patch.object(selftest.engines, "phrasing_scan",
                               return_value={"rules": 0, "hits": []}):
            items = selftest.run()
        item = {item.name: item for item in items}["词表级"]
        self.assertFalse(item.ok)
        self.assertIn("0 条规则", item.detail)
        self.assertFalse(selftest.ok(items))

    def test_render_marks_frozen_and_counts_failures(self) -> None:
        items = [selftest.Item("甲", True, "ok"), selftest.Item("乙", False, "bad")]
        text = selftest.render(items)
        self.assertIn("[PASS] 甲", text)
        self.assertIn("[FAIL] 乙", text)
        self.assertIn("有失败项（1/2）", text)
        with mock.patch.object(selftest.paths, "is_frozen", return_value=True):
            self.assertIn("frozen", selftest.render(items))


class TestEntryEmit(unittest.TestCase):
    def test_emit_tolerates_missing_stdout(self) -> None:
        original = sys.stdout
        try:
            sys.stdout = None
            entry._emit("窗口版没有控制台")  # 不应抛异常
        finally:
            sys.stdout = original

    def test_emit_writes_file_when_requested(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deai-emit-") as tmp:
            target = Path(tmp) / "out.txt"
            entry._emit("结论", str(target))
            self.assertEqual(target.read_text(encoding="utf-8"), "结论\n")


class TestSmokeCli(unittest.TestCase):
    def run_entry(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, "-m", "deai_app", *args],
                              cwd=str(DESKTOP_ROOT), env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=120)

    def test_smoke_writes_file_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deai-smoke-") as tmp:
            target = Path(tmp) / "smoke.txt"
            proc = self.run_entry("--smoke", "--out", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("全部通过（5/5）", text)
            self.assertEqual(text.count("[PASS]"), 5)
            for name in CHECK_NAMES:
                self.assertIn(name, text)

    def test_checkup_also_supports_out_file(self) -> None:
        sample = DESKTOP_ROOT.parent / "examples" / "clean-sample.md"
        with tempfile.TemporaryDirectory(prefix="deai-checkup-") as tmp:
            target = Path(tmp) / "checkup.txt"
            proc = self.run_entry("--checkup", str(sample), "--out", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("降 AI 三关体检", text)


if __name__ == "__main__":
    unittest.main()
