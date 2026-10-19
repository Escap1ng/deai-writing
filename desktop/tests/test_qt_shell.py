"""Qt 外壳的无头行为断言（QT_QPA_PLATFORM=offscreen）。

换 Qt 的一个实打实收益：界面断言不再需要真开窗口。
这里量的是像素级几何——左缘对齐、标题栏装得下 Tab、指标带不压正文——
这三条都是上一版肉眼可见的缺陷，写进断言后就不会靠"我看着还行"来判定。
"""
from __future__ import annotations

import os
import re
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import deai_app  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QTextCursor, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from deai_app.core import checkup  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui import motion  # noqa: E402
from deai_app.ui.segmented import INSET  # noqa: E402
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
        self.win._select_tab(0)
        self.win._last_gate = None
        self.win._last_source = ""
        self.win.output_view.select(0, notify=False)
        self.win._output_view = 0
        self.qapp.processEvents()

    def test_title_and_body_share_left_edge(self) -> None:
        for pane in (self.win.input, self.win.output):
            with self.subTest(pane=pane.title_label.text()):
                self.assertEqual(first_char_x(self.win, pane),
                                 pane.title_label.mapTo(self.win, QPoint(0, 0)).x())

    def test_titlebar_fits_mode_switch(self) -> None:
        tabs = self.win.titlebar.tabs
        self.assertLessEqual(tabs.height(), self.win.titlebar.height())
        self.assertLessEqual(top_y(tabs, self.win) + tabs.height(),
                             top_y(self.win.titlebar, self.win) + self.win.titlebar.height())
        self.assertGreaterEqual(tabs.height(), 24, "分段控件低于最小点击目标 24px")
        self.assertGreaterEqual(tabs.width(), 220)

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

    def test_mode_switch_updates_hint_and_pill(self) -> None:
        tabs = self.win.titlebar.tabs
        self.win._select_tab(1)
        self.assertEqual(tabs.index, 1)
        self.assertEqual(self.win.hint.text(), qt_app.HINTS[1])
        QTest.qWait(260)
        target = INSET + (tabs.width() - 2 * INSET) * 0.5
        self.assertAlmostEqual(tabs.pill, target, delta=1.0)
        self.win._select_tab(0)
        self.assertEqual(tabs.index, 0)
        self.assertEqual(self.win.hint.text(), qt_app.HINTS[0])

    def test_mode_switch_responds_to_click_and_arrow_keys(self) -> None:
        tabs = self.win.titlebar.tabs
        x = int(INSET + (tabs.width() - 2 * INSET) * 0.75)
        QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, pos=QPoint(x, tabs.height() // 2))
        self.assertEqual(tabs.index, 1)
        self.assertEqual(self.win.hint.text(), qt_app.HINTS[1])
        tabs.setFocus()
        QTest.keyClick(tabs, Qt.Key.Key_Left)
        self.assertEqual(tabs.index, 0)
        self.assertEqual(self.win.hint.text(), qt_app.HINTS[0])

    def test_output_view_switches_between_rows_and_whole_text(self) -> None:
        self.win.input.set_text(SLOP)
        self.win.run_check()
        self.assertEqual(self.win.output_view.index, 0)
        self.assertIn("词表级", self.win.output.text())
        self.win.output_view.select(1)
        self.assertEqual(self.win.output_view.index, 1)
        self.assertNotIn("词表级", self.win.output.text())
        self.assertIn("随着人工智能技术的快速发展", self.win.output.text())
        self.assertIn(self.theme.color("mark_bg").lower(),
                      self.win.output.edit.toHtml().lower())
        self.win.output_view.select(0)
        self.assertIn("词表级", self.win.output.text())

    def test_whole_text_view_keeps_every_character(self) -> None:
        self.win.input.set_text(SLOP)
        self.win.run_check()
        self.win.output_view.select(1)
        self.qapp.processEvents()
        plain = re.sub(r"\s+", "", self.win.output.text())
        self.assertEqual(plain, re.sub(r"\s+", "", SLOP))

    def test_output_view_is_compact_and_fits_header(self) -> None:
        view = self.win.output_view
        header = self.win.output.title_label.parentWidget()
        self.assertGreaterEqual(view.height(), 24, "低于最小点击目标 24px")
        self.assertLessEqual(view.height(), header.height())

    def test_output_view_switch_before_check_says_so(self) -> None:
        self.win._last_gate = None
        self.win.output_view.select(1)
        self.assertIn("先跑一次体检", self.win.status.text())
        self.win.output_view.select(0)

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

    def test_caption_buttons_are_painted_not_glyphs(self) -> None:
        """三键必须是画出来的几何图形：文字字形的字重和字宽对不齐。"""
        buttons = self.win.titlebar.findChildren(qt_app.CaptionButton)
        self.assertEqual([b.kind for b in buttons], list(qt_app.CAPTION_KINDS))
        for button in buttons:
            self.assertEqual(button.text(), "", "窗口键不该再用文字字形")
            image = button.grab().toImage()
            background = image.pixel(1, 1)
            drawn = sum(1 for y in range(image.height()) for x in range(image.width())
                        if image.pixel(x, y) != background)
            self.assertGreater(drawn, 10, f"{button.kind} 键没有画出图形")

    def test_brand_aligns_with_pane_titles(self) -> None:
        brand_x = self.win.titlebar.brand_label.mapTo(self.win, QPoint(0, 0)).x()
        title_x = self.win.input.title_label.mapTo(self.win, QPoint(0, 0)).x()
        self.assertLessEqual(abs(brand_x - title_x), 2, f"品牌 {brand_x} vs 左栏标题 {title_x}")

    def test_loaded_sample_sits_at_top(self) -> None:
        self.win._read_into(self.win.input, REPO_ROOT / "examples" / "slop-sample.md")
        self.qapp.processEvents()
        self.assertEqual(self.win.input.edit.textCursor().position(), 0)
        self.assertEqual(self.win.input.edit.verticalScrollBar().value(), 0)

    def test_window_respects_minimum_size(self) -> None:
        self.assertEqual(self.win.minimumWidth(), int(self.theme.shell("min_width")))
        self.assertEqual(self.win.minimumHeight(), int(self.theme.shell("min_height")))

    def test_wheel_scrolls_smoothly_to_target(self) -> None:
        self.win.input.set_text(SLOP * 10)
        self.qapp.processEvents()
        bar = self.win.input.edit.verticalScrollBar()
        bar.setValue(0)
        event = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(0, 0), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        self.qapp.sendEvent(self.win.input.edit.viewport(), event)
        expected = min(motion.WHEEL_STEP_PX, bar.maximum())
        if motion.enabled():
            self.assertLess(bar.value(), expected, "滚轮不该一帧跳到位")
            QTest.qWait(motion.FAST_MS + 100)
        self.assertEqual(bar.value(), expected)

    def test_stylesheet_is_applied_from_theme(self) -> None:
        self.assertIn(self.theme.color("canvas_bg"), self.qapp.styleSheet())
        self.assertIn(f'{self.theme.shell("card_radius")}px', self.qapp.styleSheet())
        self.assertIn(self.theme.color("selection_bg"), self.qapp.styleSheet())


if __name__ == "__main__":
    unittest.main()
