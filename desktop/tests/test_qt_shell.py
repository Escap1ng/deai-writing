"""Qt 外壳的无头行为断言（QT_QPA_PLATFORM=offscreen）。

换 Qt 的一个实打实收益：界面断言不再需要真开窗口。
这里量的是像素级几何——左缘对齐、标题栏装得下 Tab、指标带不压正文——
这三条都是上一版肉眼可见的缺陷，写进断言后就不会靠"我看着还行"来判定。
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import deai_app  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402

from deai_app.core import checkup  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

REPO_ROOT = Path(deai_app.__file__).resolve().parents[2]
DESKTOP_ROOT = Path(deai_app.__file__).resolve().parents[1]
SLOP = (REPO_ROOT / "examples" / "slop-sample.md").read_bytes().decode("utf-8-sig")
CLEAN = (REPO_ROOT / "examples" / "clean-sample.md").read_bytes().decode("utf-8-sig")


def first_char_x(win: qt_app.DeaiApp, pane) -> int:
    viewport = pane.edit.viewport()
    origin = viewport.mapTo(win, QPoint(0, 0))
    return origin.x() + pane.edit.cursorRect(QTextCursor(pane.edit.document())).left()


def top_y(widget, target) -> int:
    return widget.mapTo(target, QPoint(0, 0)).y()


class TestQtShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.resize(cls.theme.shell("width"), cls.theme.shell("height"))
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()

    def setUp(self) -> None:
        self.win.input.set_text("")
        self.win.output.set_text("")
        self.win.input.set_gate(None, None, None)
        self.qapp.processEvents()

    def test_title_and_body_share_left_edge(self) -> None:
        for pane in (self.win.input, self.win.output):
            with self.subTest(pane=pane.title_label.text()):
                self.assertEqual(first_char_x(self.win, pane),
                                 pane.title_label.mapTo(self.win, QPoint(0, 0)).x())

    def test_titlebar_fits_tabs(self) -> None:
        for tab in self.win.titlebar.tabs:
            self.assertLessEqual(tab.sizeHint().height(), self.win.titlebar.height())
            self.assertLessEqual(top_y(tab, self.win) + tab.height(),
                                 top_y(self.win.titlebar, self.win) + self.win.titlebar.height())

    def test_band_does_not_overlap_editor(self) -> None:
        for pane in (self.win.input, self.win.output):
            with self.subTest(pane=pane.title_label.text()):
                self.assertGreaterEqual(top_y(pane.band, self.win),
                                        top_y(pane.edit, self.win) + pane.edit.height())

    def test_metrics_band_matches_engine_numbers(self) -> None:
        self.win.input.set_text(SLOP)
        self.win.run_check()
        gate = checkup.run(SLOP, "自动")
        numbers = [number.text() for number, _ in self.win.output.metrics]
        self.assertEqual(numbers, [str(len(gate.phrasing) + len(gate.style)), gate.style_risk,
                                   "阻断" if gate.blocked else "待改"])
        chips = [text.text() for _, text in self.win.input.chips]
        self.assertEqual(chips, [f"词表 {len(gate.phrasing)}", f"结构 {gate.style_risk}",
                                 f"字符 {gate.invisible_total}"])
        self.assertIn("门禁：阻断", self.win.status.text())

    def test_clean_sample_passes_gate(self) -> None:
        self.win.input.set_text(CLEAN)
        self.win.run_check()
        self.assertEqual([text.text() for _, text in self.win.input.chips],
                         ["词表 0", "结构 低", "字符 0"])
        self.assertEqual([number.text() for number, _ in self.win.output.metrics], ["0", "低", "通过"])
        self.assertIn("门禁：通过", self.win.status.text())

    def test_empty_input_says_so(self) -> None:
        self.win.run_check()
        self.assertIn("输入是空的", self.win.status.text())

    def test_placeholder_is_not_content(self) -> None:
        self.assertEqual(self.win.input.text(), "")
        self.assertTrue(self.win.input.edit.placeholderText())
        self.win.input.set_text("正文")
        self.assertEqual(self.win.input.text(), "正文")

    def test_tab_switch_updates_hint_and_underline(self) -> None:
        self.win._select_tab(1)
        self.assertEqual(self.win.hint.text(), qt_app.HINTS[1])
        self.assertEqual(self.win.titlebar.tabs[1].objectName(), "tabOn")
        self.assertEqual(self.win.titlebar.tabs[0].objectName(), "tab")
        self.win._select_tab(0)
        self.assertEqual(self.win.titlebar.tabs[0].objectName(), "tabOn")

    def test_strip_invisible_removes_and_reports(self) -> None:
        self.win.input.set_text("方法\u200b有效")
        self.win.strip_invisible()
        self.assertEqual(self.win.input.text(), "方法有效")
        self.assertIn("已清除 1 个", self.win.status.text())
        self.win.input.set_text("方法有效")
        self.win.strip_invisible()
        self.assertIn("未发现不可见字符", self.win.status.text())

    def test_char_counter_uses_engine_definition(self) -> None:
        self.win.input.set_text(SLOP)
        self.assertEqual(self.win.input.meta.text(),
                         f"{checkup.visible_chars(SLOP)} 字 · {len(SLOP.splitlines())} 行")

    def test_cli_entry_launches_the_window(self) -> None:
        """入口与外壳之间的接线要有一条测试兜住：删了 --scale 却没改入口体那次就是这么崩的。"""
        from deai_app import __main__ as entry

        launched: list[str] = []
        original = qt_app.DeaiApp.launch
        qt_app.DeaiApp.launch = lambda self: launched.append(self.windowTitle()) or 0
        try:
            self.assertEqual(entry.main([]), 0)
            self.assertEqual(entry.main(["--version"]), 0)
        finally:
            qt_app.DeaiApp.launch = original
        self.assertEqual(launched, ["降 AI 工作台"])

    def test_entry_subprocess_starts_the_event_loop(self) -> None:
        """入口必须在子进程里验：本进程已有 QApplication，会掩盖"先建窗口后建 app"这类 abort。"""
        import subprocess

        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            subprocess.run([sys.executable, "-m", "deai_app"], cwd=str(DESKTOP_ROOT), env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=6)
        self.assertNotIn("QApplication", str(caught.exception))

    def test_window_respects_minimum_size(self) -> None:
        self.assertEqual(self.win.minimumWidth(), int(self.theme.shell("min_width")))
        self.assertEqual(self.win.minimumHeight(), int(self.theme.shell("min_height")))

    def test_stylesheet_is_applied_from_theme(self) -> None:
        self.assertIn(self.theme.color("canvas_bg"), self.qapp.styleSheet())
        self.assertIn(f'{self.theme.shell("card_radius")}px', self.qapp.styleSheet())


if __name__ == "__main__":
    unittest.main()
