"""前端换新批的验收断言：可调分栏、轮次进度、提示条收起、报告定位与展开。

与 test_qt_shell 同一口径：offscreen 实例化，量行为与几何，不靠肉眼。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl  # noqa: E402

from deai_app.core import config  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

MANY_HITS = "综上所述，" * 40
LOCATE_TEXT = "第一行开场。\n综上所述，随着人工智能技术的快速发展，本文进行了深入研究。\n第三行收尾。\n"


class TestRefreshUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-refresh-")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: cls.tmp.name})
        cls.env.start()
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.resize(cls.theme.shell("width"), cls.theme.shell("height"))
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.win.input.set_text("")
        self.win.output.set_text("")
        self.win.input.set_gate(None, None, None)
        self.win._last_gate = None
        self.win._last_source = ""
        self.win._last_result = None
        self.win._worker = None
        self.win._report_expanded = False
        self.win._select_tab(0)
        self.win._output_view = 0
        self.win.output_view.select(0, notify=False)
        self.qapp.processEvents()

    # ---------- 可调分栏 ----------

    def test_splitter_holds_both_panes_and_keeps_minimum(self) -> None:
        splitter = self.win.splitter
        self.assertEqual(splitter.count(), 2)
        self.assertIs(splitter.widget(0), self.win.input)
        self.assertIs(splitter.widget(1), self.win.output)
        self.assertFalse(splitter.childrenCollapsible())
        self.assertEqual(splitter.handleWidth(), int(self.theme.shell("splitter_width")))
        self.assertGreaterEqual(self.win.input.minimumWidth(), 240)
        self.assertGreaterEqual(self.win.output.minimumWidth(), 240)

    def test_split_ratio_round_trips_through_window_state(self) -> None:
        self.win.splitter.setSizes([700, 300])
        self.qapp.processEvents()
        self.win._save_window_state()
        data = json.loads((Path(config.config_dir()) / qt_app.WINDOW_FILE)
                          .read_text(encoding="utf-8"))
        self.assertAlmostEqual(data["split"][0], 0.7, delta=0.02)
        twin = qt_app.DeaiApp(self.theme)
        twin.show()
        self.qapp.processEvents()
        try:
            sizes = twin.splitter.sizes()
            self.assertAlmostEqual(sizes[0] / sum(sizes), 0.7, delta=0.05)
        finally:
            twin._save_window_state = lambda: None
            twin.close()

    def test_corrupt_split_falls_back_to_equal(self) -> None:
        state_path = Path(config.config_dir()) / qt_app.WINDOW_FILE
        state_path.write_text(json.dumps({"split": ["宽", None]}), encoding="utf-8")
        twin = qt_app.DeaiApp(self.theme)
        try:
            sizes = twin.splitter.sizes()
            self.assertAlmostEqual(sizes[0] / sum(sizes), 0.5, delta=0.05)
        finally:
            twin._save_window_state = lambda: None
            twin.close()

    # ---------- 轮次进度 ----------

    def test_progress_label_tracks_rounds_and_hides_when_idle(self) -> None:
        self.assertFalse(self.win.progress_label.isVisibleTo(self.win))
        self.win.input.set_text("误差从 4.8% 降到 1.9%。\n")
        self.assertTrue(self.win._prepare_generation(self.win.input.text()))
        self.assertTrue(self.win.progress_label.isVisibleTo(self.win))
        self.assertEqual(self.win.progress_label.text(), "准备中")
        self.win._on_round_start(1)
        self.assertEqual(self.win.progress_label.text(),
                         f"第 1/{self.win._settings.max_rounds} 轮")
        self.win._on_round_start(2)
        self.assertEqual(self.win.progress_label.text(),
                         f"第 2/{self.win._settings.max_rounds} 轮")
        self.win._on_worker_finished()
        self.assertFalse(self.win.progress_label.isVisibleTo(self.win))

    def test_translation_stage_updates_progress(self) -> None:
        self.win.input.set_text("误差从 4.8% 降到 1.9%。\n")
        self.assertTrue(self.win._prepare_generation(self.win.input.text()))
        self.win._on_translation_stage("translate", 0)
        self.assertEqual(self.win.progress_label.text(), "翻译阶段")
        self.win._on_translation_stage("deai", 1)
        self.assertIn("去 AI 第 1", self.win.progress_label.text())
        self.win._on_worker_finished()

    # ---------- 提示条收起 ----------

    def test_banner_can_be_dismissed_and_returns_on_new_message(self) -> None:
        long_text = "还没发出请求：全文约 5132 tokens，超过输入预算 4607 tokens。" \
                    "把稿子拆成几段分别处理，或把供应商的 context_tokens 填大一些"
        self.win._say(long_text)
        self.assertTrue(self.win.banner_widget.isVisible())
        self.win.banner_close.click()
        self.assertFalse(self.win.banner_widget.isVisible())
        self.win._say(long_text)
        self.assertTrue(self.win.banner_widget.isVisible())
        self.win._say(self.win._idle_status())
        self.assertFalse(self.win.banner_widget.isVisible())

    # ---------- 报告定位与展开 ----------

    def test_report_items_carry_locate_links(self) -> None:
        self.win.input.set_text(LOCATE_TEXT)
        self.win.run_check()
        markup = self.win.output.edit.toHtml()
        self.assertIn("locate:", markup)
        self.assertTrue(self.win.output.edit.isReadOnly())

    def test_locate_anchor_moves_input_cursor_to_the_line(self) -> None:
        self.win.input.set_text(LOCATE_TEXT)
        self.win.run_check()
        gate = self.win._last_gate
        self.assertTrue(gate.phrasing)
        hit = gate.phrasing[0]
        self.win._on_report_anchor(QUrl(f"locate:{hit['line']},{hit['col']}"))
        cursor = self.win.input.edit.textCursor()
        self.assertEqual(cursor.blockNumber(), int(hit["line"]) - 1)
        self.assertIn("已定位到输入", self.win.status.text())
        self.assertTrue(self.win.input.edit.extraSelections())

    def test_more_anchor_expands_remaining_hits(self) -> None:
        self.win.input.set_text(MANY_HITS)
        self.win.run_check()
        self.assertGreater(len(self.win._last_gate.phrasing), 30)
        self.assertIn("另有", self.win.output.text())
        self.assertIn("more:", self.win.output.edit.toHtml())
        self.win._on_report_anchor(QUrl("more:0"))
        self.assertTrue(self.win._report_expanded)
        self.assertNotIn("另有", self.win.output.text())
        self.win._switch_output_view(1)
        self.win._switch_output_view(0)
        self.assertFalse(self.win._report_expanded)
        self.assertIn("另有", self.win.output.text())

    def test_locate_after_rewrite_points_to_whole_text_view(self) -> None:
        from tests.test_rewrite_ui import CLEAN, rewrite_result
        self.win._on_rewrite_done(rewrite_result(CLEAN))
        self.win._output_view = 0
        self.win.output_view.select(0, notify=False)
        self.win._on_report_anchor(QUrl("locate:1,1"))
        self.assertEqual(self.win._output_view, 1)
        self.assertIn("整段", self.win.status.text())

    # ---------- Esc 停止 ----------

    def test_escape_stops_only_while_generating(self) -> None:
        worker = mock.Mock()
        self.win._worker = worker
        try:
            self.win._stop_generation()
            worker.cancel.assert_called_once_with()
        finally:
            self.win._worker = None
        self.win._stop_generation()  # 空闲时按 Esc 不应有任何副作用

    # ---------- 品牌与空态 ----------

    def test_brand_mark_is_painted(self) -> None:
        marks = self.win.titlebar.findChildren(qt_app.BrandMark)
        self.assertEqual(len(marks), 1)
        image = marks[0].grab().toImage()
        background = image.pixel(0, 0)
        drawn = sum(1 for y in range(image.height()) for x in range(image.width())
                    if image.pixel(x, y) != background)
        self.assertGreater(drawn, 10)

    def test_input_placeholder_guides_first_run(self) -> None:
        placeholder = self.win.input.edit.placeholderText()
        self.assertIn("Ctrl+Enter", placeholder)
        self.assertIn("拖入", placeholder)


if __name__ == "__main__":
    unittest.main()
