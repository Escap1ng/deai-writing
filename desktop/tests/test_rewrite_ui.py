"""改写 UI：设置面板落盘、流式追加、结果交付与复制口径。

面板与主窗口都用 offscreen Qt 实例化；模型调用要么用脚本替身，
要么在设置面板里根本不发请求。
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
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit  # noqa: E402

from deai_app.core import config, llm, pipeline, translate  # noqa: E402
from deai_app.core.config import Provider, Settings  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui.panes import first_loadable_url  # noqa: E402
from deai_app.ui.rewrite import RewriteWorker, TranslationWorker  # noqa: E402
from deai_app.ui.settings import SettingsDialog  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

CLEAN = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"
SLOP = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
        "研究表明，这一工作至关重要，有效提升了治理水平。\n")
REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_EN = (REPO_ROOT / "examples" / "clean-sample-en.md").read_bytes().decode("utf-8-sig")
TRANSLATED = "The baseline error dropped from 4.8% to 1.9% across 120 marked papers.\n"
PROVIDER = Provider(name="测试", base_url="http://127.0.0.1:9/v1", model="m", api_key="")


def providers() -> list[Provider]:
    return [
        Provider(name="远程", base_url="https://api.example.com/v1", model="remote-model"),
        Provider(name="本地", base_url="http://127.0.0.1:11434/v1", model="local-model"),
    ]


def rewrite_result(output: str) -> pipeline.RewriteResult:
    def chat(*args, **kwargs):
        if kwargs.get("emit"):
            kwargs["emit"](output)
        return output

    return pipeline.rewrite("原文一段。", PROVIDER, Settings(max_rounds=1), chat=chat)


def translation_result() -> translate.TranslationResult:
    outputs = [TRANSLATED, CLEAN_EN]

    def chat(*args, **kwargs):
        piece = outputs.pop(0)
        if kwargs.get("emit"):
            kwargs["emit"](piece)
        return piece

    return translate.translate(SLOP, PROVIDER, Settings(max_rounds=1), chat=chat)


class SettingsCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="deai-dialog-")
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {config.ENV_DIR: str(self.dir)})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def dialog(self, active: str = "本地", **settings) -> SettingsDialog:
        current = Settings(active_provider=active, **settings)
        return SettingsDialog(self.theme, providers(), current)


class TestSettingsDialog(SettingsCase):
    def test_populates_active_provider_and_rules(self) -> None:
        dialog = self.dialog("本地", preset="公文", intensity="重", max_rounds=3)
        self.assertEqual(dialog.combo.currentText(), "本地")
        self.assertEqual(dialog.base_edit.text(), "http://127.0.0.1:11434/v1")
        self.assertEqual(dialog.model_edit.text(), "local-model")
        self.assertEqual(dialog.preset.currentText(), "公文")
        self.assertEqual(dialog.intensity.currentText(), "重")
        self.assertEqual(dialog.rounds.value(), 3)

    def test_switching_provider_keeps_edits(self) -> None:
        dialog = self.dialog("远程")
        dialog.model_edit.setText("edited-remote")
        dialog.combo.setCurrentIndex(1)
        dialog.combo.setCurrentIndex(0)
        self.assertEqual(dialog.model_edit.text(), "edited-remote")

    def test_key_is_hidden_until_toggled(self) -> None:
        dialog = self.dialog()
        self.assertEqual(dialog.key_edit.echoMode(), QLineEdit.EchoMode.Password)
        dialog._toggle_key()
        self.assertEqual(dialog.key_edit.echoMode(), QLineEdit.EchoMode.Normal)
        dialog._toggle_key()
        self.assertEqual(dialog.key_edit.echoMode(), QLineEdit.EchoMode.Password)

    def test_remote_without_key_is_rejected(self) -> None:
        dialog = self.dialog("远程")
        dialog._save()
        self.assertIsNone(dialog.settings_out)
        self.assertIn("api_key", dialog.error.text())
        self.assertFalse((self.dir / config.PROVIDERS_FILE).exists())

    def test_local_saves_and_round_trips(self) -> None:
        dialog = self.dialog("本地", preset="论文", intensity="轻", max_rounds=1)
        dialog.model_edit.setText("qwen2.5:14b")
        dialog._save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIsNotNone(dialog.settings_out)
        saved = config.load_providers(self.dir)
        self.assertEqual([p.name for p in saved], ["远程", "本地"])
        self.assertEqual(saved[1].model, "qwen2.5:14b")
        settings = config.load_settings(self.dir)
        self.assertEqual(settings.active_provider, "本地")
        self.assertEqual((settings.preset, settings.intensity, settings.max_rounds),
                         ("论文", "轻", 1))

    def test_duplicate_names_are_rejected(self) -> None:
        dialog = self.dialog("本地")
        dialog.name_edit.setText("远程")
        dialog._save()
        self.assertIsNone(dialog.settings_out)
        self.assertIn("不能重复", dialog.error.text())

    def test_translation_target_is_saved(self) -> None:
        dialog = self.dialog("本地", translate_target="英文")
        self.assertEqual(dialog.target.currentText(), "英文")
        dialog.target.setCurrentText("中文")
        dialog._save()
        self.assertEqual(config.load_settings(self.dir).translate_target, "中文")

    def test_add_and_delete_provider(self) -> None:
        dialog = self.dialog()
        self.assertEqual(dialog.combo.count(), 2)
        dialog._on_add()
        self.assertEqual(dialog.combo.count(), 3)
        self.assertEqual(dialog.combo.currentIndex(), 2)
        dialog._on_delete()
        self.assertEqual(dialog.combo.count(), 2)

    def test_delete_keeps_one_provider(self) -> None:
        dialog = SettingsDialog(self.theme, [providers()[0]], Settings(active_provider="远程"))
        dialog._on_delete()
        self.assertEqual(dialog.combo.count(), 1)
        self.assertIn("至少保留", dialog.error.text())

    def test_dialog_fits_screen_and_fields(self) -> None:
        dialog = self.dialog()
        dialog.show(); self.qapp.processEvents()
        self.assertEqual(dialog.width(), 580)
        self.assertLessEqual(dialog.height(), 760)
        limit = dialog.width() - 14
        for widget in (dialog.combo, dialog.name_edit, dialog.base_edit,
                       dialog.model_edit, dialog.preset, dialog.intensity,
                       dialog.target, dialog.rounds, dialog.temp, dialog.timeout,
                       dialog.context):
            with self.subTest(widget=widget.objectName() or type(widget).__name__):
                right = widget.mapTo(dialog, widget.rect().topLeft()).x() + widget.width()
                self.assertLessEqual(right, limit)
        dialog.close()

    def test_context_tokens_round_trip(self) -> None:
        dialog = self.dialog("本地")
        self.assertEqual(dialog.context.value(), 0)
        dialog.context.setValue(32768)
        dialog._save()
        saved = config.load_providers(self.dir)
        self.assertEqual(saved[1].context_tokens, 32768)
        settings = dialog.settings_out
        self.assertIsNotNone(settings)


class TestQuickControls(unittest.TestCase):
    """工具栏供应商下拉与学术翻译方向控件：高频操作不出主页。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-quick-")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: cls.tmp.name})
        cls.env.start()
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def test_provider_combo_lists_and_selects_active(self) -> None:
        combo = self.win.provider_combo
        self.assertEqual(combo.count(), len(self.win._providers))
        self.assertGreaterEqual(combo.count(), 2)
        self.assertEqual(combo.currentText(), self.win._active_provider.name)

    def test_provider_switch_persists_and_updates_state(self) -> None:
        combo = self.win.provider_combo
        other = (combo.currentIndex() + 1) % combo.count()
        combo.setCurrentIndex(other)
        expected = combo.itemText(other)
        self.assertEqual(self.win._settings.active_provider, expected)
        self.assertEqual(self.win._active_provider.name, expected)
        self.assertEqual(config.load_settings().active_provider, expected)
        self.assertIn("就绪", self.win.status.text())

    def test_provider_switch_tolerates_persist_failure(self) -> None:
        combo = self.win.provider_combo
        other = (combo.currentIndex() + 1) % combo.count()
        with mock.patch.object(config, "save_settings", side_effect=OSError("目录锁死")):
            combo.setCurrentIndex(other)
        expected = combo.itemText(other)
        self.assertEqual(self.win._settings.active_provider, expected)
        self.assertIn("切换没保存下来", self.win.banner.text())
        self.assertTrue(combo.isEnabled())
        self.win._sync_provider_combo()
        self.assertEqual(combo.currentText(), expected)

    def test_combo_disabled_without_providers(self) -> None:
        with mock.patch.object(config, "load_providers", return_value=[]):
            self.win._reload_config()
        self.assertFalse(self.win.provider_combo.isEnabled())
        self.win._reload_config()
        self.assertTrue(self.win.provider_combo.isEnabled())

    def test_direction_visible_only_in_translate_mode(self) -> None:
        self.win._select_tab(0)
        self.assertTrue(self.win.direction_view.isHidden())
        self.win._select_tab(1)
        self.assertTrue(self.win.direction_view.isVisible())

    def test_direction_switch_persists(self) -> None:
        self.win._select_tab(1)
        self.win.direction_view.select(1)  # 英文
        self.assertEqual(self.win._settings.translate_target, "英文")
        self.assertEqual(config.load_settings().translate_target, "英文")
        self.assertIn("中文→英文", self.win.status.text())
        self.win.direction_view.select(2)  # 中文
        self.assertEqual(config.load_settings().translate_target, "中文")

    def test_direction_switch_tolerates_persist_failure(self) -> None:
        self.win.direction_view.select(0)
        self.win._settings.translate_target = "自动"
        with mock.patch.object(config, "save_settings", side_effect=OSError("写不进")):
            self.win.direction_view.select(1)
        self.assertEqual(self.win._settings.translate_target, "英文")
        self.assertIn("写不进", self.win.banner.text())
        self.win.direction_view.select(0)
        self.win._say(self.win._idle_status())


class TestRewriteHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-rewrite-ui-")
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
        self.win._last_gate = None
        self.win._last_source = ""
        self.win._last_result = None
        self.win._stream_text = ""
        self.win._worker = None
        self.win._translation_draft = None
        self.win._translation_resume = None
        self.win._select_tab(0)
        self.win._output_view = 1
        self.win.output_view.select(1, notify=False)
        self.qapp.processEvents()

    def test_round_reset_clears_previous_stream(self) -> None:
        self.win._on_round_start(1)
        self.win._on_delta("半")
        self.win._on_delta("成品")
        self.assertEqual(self.win.output.text(), "半成品")
        self.assertEqual(self.win._stream_text, "半成品")
        self.win._on_round_start(2)
        self.assertEqual(self.win.output.text(), "")
        self.assertEqual(self.win._stream_text, "")

    def test_done_delivers_plain_result_and_copy_ignores_view(self) -> None:
        result = rewrite_result(CLEAN)
        self.win._on_rewrite_done(result)
        self.assertEqual(self.win._last_result, CLEAN.strip())
        self.assertEqual(self.win._last_source, CLEAN.strip())
        self.assertIn("改写完成", self.win.status.text())
        self.assertIn("门禁：通过", self.win.status.text())

        self.win.output_view.select(0, notify=False)
        self.win._output_view = 0
        self.win._copy()
        self.assertEqual(QApplication.clipboard().text(), CLEAN.strip())

    def test_dirty_result_keeps_hits_in_annotated_view(self) -> None:
        result = rewrite_result(SLOP)
        self.win._on_rewrite_done(result)
        self.assertGreater(len(result.gate.phrasing), 0)
        self.assertIn("待改", self.win.status.text())
        self.assertIn("background-color", self.win.output.edit.toHtml().lower())

    def test_strip_after_rewrite_keeps_result(self) -> None:
        result = rewrite_result(CLEAN)
        self.win._on_rewrite_done(result)
        self.win.input.set_text("方法\u200b有效")
        self.win.strip_invisible()
        self.assertEqual(self.win._last_result, CLEAN.strip())
        self.assertEqual(self.win._last_source, CLEAN.strip())
        self.assertIn("已清除 1 个", self.win.status.text())

    def test_local_check_clears_result_for_copy(self) -> None:
        self.win._last_result = "旧的改写结果"
        self.win.output_view.select(0, notify=False)
        self.win._output_view = 0
        self.win.input.set_text(CLEAN)
        self.win.run_check()
        self.assertIsNone(self.win._last_result)
        self.win._copy()
        self.assertIn("降 AI 三关体检", QApplication.clipboard().text())

    def test_idle_status_shows_unready_provider(self) -> None:
        self.assertIn("就绪", self.win._idle_status())
        self.assertIn("未就绪", self.win._idle_status())

    def test_missing_provider_is_explained(self) -> None:
        self.assertIn("接口设置", self.win._provider_error(None))

    def test_mode_switch_changes_primary_action_label(self) -> None:
        self.win._select_tab(1)
        self.assertEqual(self.win._mode, 1)
        self.assertEqual(self.win.rewrite_button.text(), "AI 翻译")
        self.win._select_tab(0)
        self.assertEqual(self.win.rewrite_button.text(), "AI 改写")

    def test_primary_action_dispatches_by_mode(self) -> None:
        with mock.patch.object(self.win, "start_translation") as translated, \
                mock.patch.object(self.win, "start_rewrite") as rewritten:
            self.win._mode = 1
            self.win.start_primary_action()
            translated.assert_called_once_with()
            self.win._mode = 0
            self.win.start_primary_action()
            rewritten.assert_called_once_with()

    def test_mode_switch_is_blocked_while_generating(self) -> None:
        self.win._worker = mock.Mock()
        try:
            self.win._select_tab(1)
            self.assertEqual(self.win._mode, 0)
            self.assertIn("生成进行中", self.win.status.text())
        finally:
            self.win._worker = None

    def test_translation_done_delivers_final_text(self) -> None:
        self.win._on_translation_done(translation_result())
        self.assertEqual(self.win._last_result, CLEAN_EN.strip())
        self.assertIn("翻译完成", self.win.status.text())
        self.assertIn("中文→英文", self.win.status.text())
        self.assertIn("去 AI 1 轮", self.win.status.text())
        self.assertIn("门禁：通过", self.win.status.text())

    def test_deai_failure_keeps_draft_and_offers_retry(self) -> None:
        self.win._select_tab(1)
        self.assertEqual(self.win.rewrite_button.text(), "AI 翻译")
        self.win._on_translation_deai_failed("接口超时", TRANSLATED, "zh", "en")
        self.assertEqual(self.win._translation_draft, TRANSLATED)
        self.assertEqual(self.win._translation_resume, ("zh", "en"))
        self.assertIsNone(self.win._last_result)
        self.assertEqual(self.win.output.text(), TRANSLATED)
        self.assertEqual(self.win.rewrite_button.text(), "重试降 AI")
        self.assertIn("草稿已保留", self.win.status.text())
        self.assertIn("接口超时", self.win.status.text())

    def test_deai_cancel_keeps_draft(self) -> None:
        self.win._select_tab(1)
        self.win._on_translation_deai_cancelled(TRANSLATED, "zh", "en")
        self.assertEqual(self.win._translation_draft, TRANSLATED)
        self.assertEqual(self.win.rewrite_button.text(), "重试降 AI")

    def test_primary_action_dispatches_to_retry_when_draft_pending(self) -> None:
        self.win._select_tab(1)
        self.win._translation_draft = TRANSLATED
        self.win._translation_resume = ("zh", "en")
        with mock.patch.object(self.win, "start_deai_retry") as retry, \
                mock.patch.object(self.win, "start_translation") as translated:
            self.win.start_primary_action()
            retry.assert_called_once_with()
            translated.assert_not_called()

    def test_retry_success_clears_draft(self) -> None:
        self.win._select_tab(1)
        self.win._translation_draft = TRANSLATED
        self.win._translation_resume = ("zh", "en")
        self.win._on_translation_done(translation_result())
        self.assertIsNone(self.win._translation_draft)
        self.assertIsNone(self.win._translation_resume)
        self.assertEqual(self.win._primary_label(), "AI 翻译")

    def test_copy_labels_draft_explicitly(self) -> None:
        self.win._translation_draft = TRANSLATED
        self.win._translation_resume = ("zh", "en")
        self.win._copy()
        self.assertEqual(QApplication.clipboard().text(), TRANSLATED)
        self.assertIn("译文草稿（未过降 AI）", self.win.status.text())

    def test_editing_input_voids_pending_draft(self) -> None:
        self.win._select_tab(1)
        self.win._translation_draft = TRANSLATED
        self.win._translation_resume = ("zh", "en")
        self.win.rewrite_button.setText(self.win._primary_label())
        self.win.input.set_text("新的输入")
        self.assertIsNone(self.win._translation_draft)
        self.assertIsNone(self.win._translation_resume)
        self.assertEqual(self.win.rewrite_button.text(), "AI 翻译")


class TestMessageRouting(unittest.TestCase):
    """状态行单行不换行：长文案路由进可换行提示条，状态行只留摘要。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-banner-")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: cls.tmp.name})
        cls.env.start()
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def test_split_message_thresholds(self) -> None:
        short = "就绪 · v0.1.0"
        self.assertEqual(qt_app.split_message(short), (short, ""))
        long_text = "还没发出请求：全文约 5132 tokens，超过「测试」的输入预算 4607 tokens。" \
                    "把稿子拆成几段分别处理，或把供应商的 context_tokens 填大一些"
        self.assertGreater(len(long_text), qt_app.LONG_HINT_CHARS)
        status, hint = qt_app.split_message(long_text)
        self.assertTrue(status.endswith("…"))
        self.assertEqual(hint, long_text)
        self.assertEqual(qt_app.split_message(long_text, banner=False, limit=500),
                         (long_text, ""))

    def test_done_verdict_stays_in_status(self) -> None:
        self.win._on_rewrite_done(rewrite_result(CLEAN))
        self.assertIn("门禁：通过", self.win.status.text())
        self.assertFalse(self.win.banner.isVisible())

    def test_long_message_shows_banner_and_summary(self) -> None:
        long_text = "还没发出请求：全文约 5132 tokens，超过输入预算 4607 tokens。把稿子拆成几段分别处理，" \
                    "或把供应商的 context_tokens 填大一些（现在 8192，已扣除输出预留 4096）"
        self.win._say(long_text)
        self.assertTrue(self.win.banner.isVisible())
        self.assertEqual(self.win.banner.text(), long_text)
        self.assertTrue(self.win.status.text().endswith("…"))
        self.assertLess(len(self.win.status.text()), len(long_text))

    def test_short_message_hides_banner(self) -> None:
        self.win._say("体检完成 · 用时 0.02s · 门禁：通过")
        self.assertFalse(self.win.banner.isVisible())
        self.assertFalse(self.win.banner.text())

    def test_failure_messages_route_even_when_short(self) -> None:
        self.win._on_rewrite_failed("接口坏了")
        self.assertTrue(self.win.banner.isVisible())
        self.assertIn("改写失败：接口坏了", self.win.banner.text())
        self.assertEqual("改写失败：接口坏了", self.win.status.text())
        self.win._say(self.win._idle_status())
        self.assertFalse(self.win.banner.isVisible())

    def test_config_error_route_reaches_banner(self) -> None:
        with mock.patch.object(config, "load_settings",
                               side_effect=config.ConfigError("设置文件应是一个 JSON 对象："
                                                              "C:/生活的 providers.json 里多了逗号")):
            self.win._reload_config()
        self.assertTrue(self.win.banner.isVisible())
        self.assertIn("providers.json", self.win.banner.text())


class TestDropsAndWindowState(unittest.TestCase):
    """输入栏拖放载入与窗口几何记忆：走回调与存读文件，不模拟 Qt 事件本身。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-drag-")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: cls.tmp.name})
        cls.env.start()
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def write_file(self, name: str, content: str) -> Path:
        path = Path(self.tmp.name) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_first_loadable_url(self) -> None:
        md = self.write_file("a.md", "x")
        urls = [QUrl("https://example.com/doc.md"), QUrl.fromLocalFile(str(md))]
        self.assertEqual(first_loadable_url(urls, qt_app.READ_SUFFIXES), md)
        other = self.write_file("b.doc", "x")
        self.assertIsNone(
            first_loadable_url([QUrl.fromLocalFile(str(other))], qt_app.READ_SUFFIXES))
        self.assertIsNone(first_loadable_url([QUrl("https://example.com/doc.pdf")],
                                            qt_app.READ_SUFFIXES))

    def test_drop_callback_loads_into_input(self) -> None:
        path = self.write_file("b.md", "拖进来的稿子。\n")
        self.win._on_file_dropped(path)
        self.assertEqual(self.win.input.text(), "拖进来的稿子。\n")

    def test_drop_blocked_while_generating(self) -> None:
        path = self.write_file("c.md", "生成中不许换稿")
        self.win._worker = mock.Mock()
        try:
            self.win._on_file_dropped(path)
            self.assertEqual(self.win.input.text(), "")
            self.assertIn("生成进行中", self.win.status.text())
        finally:
            self.win._worker = None

    def test_pane_accepts_only_listed_suffixes(self) -> None:
        self.assertTrue(self.win.input.acceptDrops())
        self.assertFalse(self.win.output.acceptDrops())

    def test_geometry_round_trip(self) -> None:
        self.win.resize(1100, 700)
        self.win.move(37, 41)
        self.win._save_window_state()
        data = json.loads(Path(config.config_dir()) .joinpath(
            qt_app.WINDOW_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data["size"], [1100, 700])
        self.assertFalse(data["maximized"])
        twin = qt_app.DeaiApp(self.theme)
        try:
            self.assertEqual((twin.width(), twin.height()), (1100, 700))
            self.assertEqual((twin.x(), twin.y()), (37, 41))
            self.assertFalse(twin._start_maximized)
        finally:
            twin._save_window_state = lambda: None
            twin.close()

    def test_restores_maximized_flag(self) -> None:
        state_path = Path(config.config_dir()) / qt_app.WINDOW_FILE
        state_path.write_text(json.dumps(
            {"size": [1100, 700], "pos": [37, 41], "maximized": True}), encoding="utf-8")
        twin = qt_app.DeaiApp(self.theme)
        try:
            self.assertTrue(twin._start_maximized)
        finally:
            twin._save_window_state = lambda: None
            twin.close()

    def test_offscreen_position_is_discarded(self) -> None:
        state_path = Path(config.config_dir()) / qt_app.WINDOW_FILE
        state_path.write_text(json.dumps(
            {"size": [1100, 700], "pos": [20000, 20000], "maximized": False}), encoding="utf-8")
        twin = qt_app.DeaiApp(self.theme)
        try:
            self.assertEqual((twin.width(), twin.height()), (1100, 700))
            self.assertNotEqual(twin.x(), 20000)
        finally:
            twin._save_window_state = lambda: None
            twin.close()

    def test_corrupt_state_file_uses_defaults(self) -> None:
        state_path = Path(config.config_dir()) / qt_app.WINDOW_FILE
        state_path.write_text("{ 不是 JSON", encoding="utf-8")
        twin = qt_app.DeaiApp(self.theme)
        try:
            self.assertEqual(twin._start_maximized, False)
        finally:
            twin._save_window_state = lambda: None
            twin.close()


class TestGenerationLock(unittest.TestCase):
    """生成期间的行为收口：动作按钮禁用、进行中指示出现，结束全部恢复。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-lock-")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: cls.tmp.name})
        cls.env.start()
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def disable_then_restore(self) -> None:
        self.win.input.set_text("误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n")
        self.assertTrue(self.win._prepare_generation(self.win.input.text()))
        self.qapp.processEvents()

        self.assertTrue(self.win.busy_dot.isVisible())
        self.assertEqual(self.win.rewrite_button.text(), "停止生成")
        for pane, names in ((self.win.input, ("清空", "载入")),
                            (self.win.output, ("复制", "存为文件"))):
            buttons = list(zip(pane._action_buttons, names))
            self.assertTrue(buttons)
            for button, name in buttons:
                self.assertEqual(button.text(), name)
                self.assertFalse(button.isEnabled())
        self.assertFalse(self.win.check_button.isEnabled())
        self.assertFalse(self.win.settings_button.isEnabled())
        self.assertFalse(self.win.provider_combo.isEnabled())
        self.assertFalse(self.win.direction_view.isEnabled())

        self.win._on_worker_finished()
        self.qapp.processEvents()
        self.assertFalse(self.win.busy_dot.isVisible())
        for pane in (self.win.input, self.win.output):
            for button in pane._action_buttons:
                self.assertTrue(button.isEnabled())
        self.assertTrue(self.win.check_button.isEnabled())
        self.assertTrue(self.win.settings_button.isEnabled())
        self.assertTrue(self.win.provider_combo.isEnabled())
        self.assertTrue(self.win.direction_view.isEnabled())

    def test_full_lock_cycle(self) -> None:
        self.disable_then_restore()

    def test_lock_cycle_with_pending_translation_draft(self) -> None:
        self.win._select_tab(1)
        self.disable_then_restore()
        self.win._select_tab(0)

    def test_busy_dot_hidden_before_first_run(self) -> None:
        self.assertFalse(self.win.busy_dot.isVisibleTo(self.win))


class TestRewriteWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qapp = QApplication.instance() or QApplication([])

    def worker(self) -> RewriteWorker:
        return RewriteWorker("原文", PROVIDER, Settings(max_rounds=1))

    def test_done_signal(self) -> None:
        results, errors = [], []
        worker = self.worker()
        worker.done.connect(results.append)
        worker.failed.connect(errors.append)
        with mock.patch.object(llm, "stream_chat", return_value=CLEAN):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(len(results), 1)
        self.assertEqual(errors, [])
        self.assertEqual(results[0].text, CLEAN.strip())

    def test_llm_error_is_forwarded(self) -> None:
        errors = []
        worker = self.worker()
        worker.failed.connect(errors.append)
        with mock.patch.object(llm, "stream_chat", side_effect=llm.LLMError("接口坏了")):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(errors, ["接口坏了"])

    def test_cancel_is_not_reported_as_failure(self) -> None:
        state = {"cancelled": False, "failed": []}
        worker = self.worker()
        worker.cancelled.connect(lambda: state.update(cancelled=True))
        worker.failed.connect(state["failed"].append)
        with mock.patch.object(llm, "stream_chat", side_effect=llm.Cancelled("已取消")):
            worker.run()
        self.qapp.processEvents()
        self.assertTrue(state["cancelled"])
        self.assertEqual(state["failed"], [])

    def test_unexpected_error_is_wrapped(self) -> None:
        errors = []
        worker = self.worker()
        worker.failed.connect(errors.append)
        with mock.patch.object(llm, "stream_chat", side_effect=RuntimeError("boom")):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(len(errors), 1)
        self.assertIn("改写意外中断", errors[0])
        self.assertIn("boom", errors[0])

    def test_translation_worker_emits_stages_and_result(self) -> None:
        results, stages = [], []
        worker = TranslationWorker("原文", PROVIDER, Settings(max_rounds=1))
        worker.done.connect(results.append)
        worker.stage_started.connect(lambda stage, index: stages.append((stage, index)))
        with mock.patch.object(llm, "stream_chat", side_effect=[TRANSLATED, CLEAN_EN]):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(stages, [("translate", 0), ("deai", 1)])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, CLEAN_EN.strip())
        self.assertEqual(results[0].direction(), "中文→英文")

    def test_translation_deai_failure_keeps_draft(self) -> None:
        interrupted, delivered = [], []
        worker = TranslationWorker(SLOP, PROVIDER, Settings(max_rounds=1))
        worker.deai_failed.connect(
            lambda reason, draft, source, target: interrupted.append(
                (reason, draft, source, target)))
        worker.failed.connect(delivered.append)
        worker.done.connect(delivered.append)
        with mock.patch.object(llm, "stream_chat", side_effect=[TRANSLATED, llm.LLMError("接口超时")]):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(len(interrupted), 1)
        reason, draft, source, target = interrupted[0]
        self.assertIn("接口超时", reason)
        self.assertEqual(draft.rstrip(), TRANSLATED.strip())
        self.assertEqual((source, target), ("zh", "en"))
        self.assertEqual(delivered, [])

    def test_translation_deai_cancel_keeps_draft(self) -> None:
        drafts, cancelled, done = [], [], []
        worker = TranslationWorker(SLOP, PROVIDER, Settings(max_rounds=1))
        worker.deai_cancelled.connect(
            lambda draft, source, target: drafts.append((draft, source, target)))
        worker.cancelled.connect(cancelled.append)
        worker.done.connect(done.append)
        with mock.patch.object(llm, "stream_chat", side_effect=[TRANSLATED, llm.Cancelled("停")]):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(len(drafts), 1)
        draft, source, target = drafts[0]
        self.assertEqual(draft.rstrip(), TRANSLATED.strip())
        self.assertEqual((source, target), ("zh", "en"))
        self.assertEqual(cancelled, [])
        self.assertEqual(done, [])

    def test_translation_stage1_failure_has_no_draft(self) -> None:
        interrupted, failed = [], []
        worker = TranslationWorker(SLOP, PROVIDER, Settings(max_rounds=1))
        worker.deai_failed.connect(lambda *args: interrupted.append(args))
        worker.deai_cancelled.connect(lambda *args: interrupted.append(args))
        worker.failed.connect(failed.append)
        with mock.patch.object(llm, "stream_chat", side_effect=llm.LLMError("没响应")):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(interrupted, [])
        self.assertEqual(failed, ["没响应"])

    def test_translation_resume_only_runs_deai(self) -> None:
        results, stages = [], []
        worker = TranslationWorker(TRANSLATED, PROVIDER, Settings(max_rounds=1),
                                   resume=("zh", "en"))
        worker.done.connect(results.append)
        worker.stage_started.connect(lambda stage, index: stages.append((stage, index)))
        with mock.patch.object(llm, "stream_chat", side_effect=[CLEAN_EN]):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(stages, [("deai", 1)])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].text, CLEAN_EN.strip())
        self.assertEqual(results[0].direction(), "中文→英文")

    def test_translation_resume_failure_keeps_draft(self) -> None:
        interrupted, delivered = [], []
        worker = TranslationWorker(TRANSLATED, PROVIDER, Settings(max_rounds=1),
                                   resume=("zh", "en"))
        worker.deai_failed.connect(
            lambda reason, draft, source, target: interrupted.append(
                (reason, draft, source, target)))
        worker.failed.connect(delivered.append)
        with mock.patch.object(llm, "stream_chat", side_effect=llm.LLMError("坏了")):
            worker.run()
        self.qapp.processEvents()
        self.assertEqual(len(interrupted), 1)
        _, draft, source, target = interrupted[0]
        self.assertEqual(draft, TRANSLATED)
        self.assertEqual((source, target), ("zh", "en"))
        self.assertEqual(delivered, [])


if __name__ == "__main__":
    unittest.main()
