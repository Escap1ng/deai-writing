"""端到端：本地假供应商 → QThread → 主窗口，确认改写按钮真的能交付结果。

前面几层各自有测试；这一条只回答一个问题：用户点下按钮后，
窗口是否在事件循环里收到流式内容、跑完三关、把纯文本结果存好并恢复按钮。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from deai_app.core import config  # noqa: E402
from deai_app.ui import app as qt_app  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

CLEAN = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"
SLOP = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
        "研究表明，这一工作至关重要，有效提升了治理水平。\n")
TRANSLATED = "The baseline error dropped from 4.8% to 1.9% across 120 marked papers.\n"
REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_EN = (REPO_ROOT / "examples" / "clean-sample-en.md").read_bytes().decode("utf-8-sig")


def has_cjk(text: str) -> bool:
    return any("\u3400" <= ch <= "\u9fff" for ch in text)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802 - http.server 命名
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        self.server.requests += 1
        try:
            payload = json.loads(raw)
            messages = payload.get("messages") or []
            system = messages[0].get("content", "") if messages else ""
            user = messages[1].get("content", "") if len(messages) > 1 else ""
        except ValueError:
            system, user = "", ""
        if "学术论文翻译" in system:
            output = TRANSLATED
        elif TRANSLATED.strip() in user:
            output = CLEAN_EN
        elif has_cjk(user):
            output = CLEAN
        else:
            output = CLEAN_EN
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for start in range(0, len(output), 8):
            piece = output[start:start + 8]
            data = json.dumps({"choices": [{"delta": {"content": piece}}]}, ensure_ascii=False)
            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.005)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    requests = 0


class TestRewriteEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-e2e-")
        cls.dir = Path(cls.tmp.name)
        cls.server = _Server(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        port = cls.server.server_address[1]
        (cls.dir / config.PROVIDERS_FILE).write_text(json.dumps({"providers": [{
            "name": "本地假接口",
            "base_url": f"http://127.0.0.1:{port}/v1",
            "model": "fake-model",
            "api_key": "",
            "timeout": 10,
        }]}, ensure_ascii=False), encoding="utf-8")
        (cls.dir / config.SETTINGS_FILE).write_text(json.dumps({
            "active_provider": "本地假接口",
            "preset": "论文",
            "intensity": "中",
            "max_rounds": 1,
        }, ensure_ascii=False), encoding="utf-8")
        cls.env = mock.patch.dict(os.environ, {config.ENV_DIR: str(cls.dir)})
        cls.env.start()
        cls.theme = load_theme()
        cls.qapp = qt_app.ensure_app(cls.theme)
        cls.win = qt_app.DeaiApp(cls.theme)
        cls.win.show()
        cls.qapp.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.close()
        cls.qapp.processEvents()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.win.input.set_text(SLOP)
        self.win.output.set_text("")
        self.win._last_result = None
        self.win._last_gate = None
        self.win._last_source = ""
        self.win._worker = None
        self.win._select_tab(0)
        self.win._output_view = 1
        self.win.output_view.select(1, notify=False)
        self.win.rewrite_button.setText("AI 改写")
        self.win.check_button.setEnabled(True)
        self.win.settings_button.setEnabled(True)
        self.qapp.processEvents()

    def test_button_delivers_streamed_result(self) -> None:
        self.assertEqual(self.win._active_provider.name, "本地假接口")
        self.win.start_rewrite()
        self.assertEqual(self.win.rewrite_button.text(), "停止生成")
        self.assertFalse(self.win.check_button.isEnabled())

        deadline = time.monotonic() + 10
        while self.win._worker is not None and time.monotonic() < deadline:
            self.qapp.processEvents()
            time.sleep(0.01)
        self.qapp.processEvents()

        self.assertIsNone(self.win._worker, "后台线程未在 10 秒内结束")
        self.assertGreaterEqual(self.server.requests, 1)
        self.assertEqual(self.win._last_result, CLEAN.strip())
        self.assertEqual(self.win._last_source, CLEAN.strip())
        self.assertIn("改写完成", self.win.status.text())
        self.assertIn("门禁：通过", self.win.status.text())
        self.assertEqual(self.win.rewrite_button.text(), "AI 改写")
        self.assertTrue(self.win.check_button.isEnabled())
        self.assertTrue(self.win.settings_button.isEnabled())

    def test_translation_mode_translates_then_deais(self) -> None:
        self.win._select_tab(1)
        self.assertEqual(self.win.rewrite_button.text(), "AI 翻译")
        before = self.server.requests
        self.win.start_primary_action()
        self.assertEqual(self.win.rewrite_button.text(), "停止生成")

        deadline = time.monotonic() + 10
        while self.win._worker is not None and time.monotonic() < deadline:
            self.qapp.processEvents()
            time.sleep(0.01)
        self.qapp.processEvents()

        self.assertIsNone(self.win._worker, "翻译线程未在 10 秒内结束")
        self.assertEqual(self.server.requests - before, 2, "应为翻译 + 一轮译后去 AI")
        self.assertEqual(self.win._last_result, CLEAN_EN.strip())
        self.assertIn("翻译完成", self.win.status.text())
        self.assertIn("中文→英文", self.win.status.text())
        self.assertIn("门禁：通过", self.win.status.text())
        self.assertEqual(self.win.rewrite_button.text(), "AI 翻译")


if __name__ == "__main__":
    unittest.main()
