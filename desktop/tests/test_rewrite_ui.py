"""改写 UI：设置面板落盘、流式追加、结果交付与复制口径。

面板与主窗口都用 offscreen Qt 实例化；模型调用要么用脚本替身，
要么在设置面板里根本不发请求。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLineEdit  # noqa: E402

from deai_app.core import config, llm, pipeline  # noqa: E402
from deai_app.core.config import Provider, Settings  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui.rewrite import RewriteWorker  # noqa: E402
from deai_app.ui.settings import SettingsDialog  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

CLEAN = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"
SLOP = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
        "研究表明，这一工作至关重要，有效提升了治理水平。\n")
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
                       dialog.model_edit, dialog.preset, dialog.rounds):
            with self.subTest(widget=widget.objectName() or type(widget).__name__):
                right = widget.mapTo(dialog, widget.rect().topLeft()).x() + widget.width()
                self.assertLessEqual(right, limit)
        dialog.close()


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


if __name__ == "__main__":
    unittest.main()
