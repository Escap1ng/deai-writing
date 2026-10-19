"""llm 流式调用对着真实的本地 HTTP 服务测，不用 mock。

错误映射依赖 urllib 真实的异常类型，SSE 分帧依赖 socket 真实的换行与关闭边界，
所以这里起一个 ThreadingHTTPServer：每个路由对应一种供应商行为。
"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from deai_app.core.config import ConfigError, Provider
from deai_app.core.llm import Cancelled, LLMError, _connect_hint, stream_chat

API_KEY = "sk-local-SECRET-9876543210"


def frame(piece: str) -> bytes:
    data = json.dumps({"choices": [{"delta": {"content": piece}}]}, ensure_ascii=False)
    return f"data: {data}\n\n".encode("utf-8")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.received: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802 - http.server 命名
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        self.server.received.append(
            {"path": self.path, "body": raw, "headers": dict(self.headers)}
        )
        route = self.path.split("/")[1]
        if route == "sse":
            self._stream([frame("去"), frame("AI")], done=True)
        elif route == "comment":
            self._stream([b": keep-alive\n\n", frame("好")], done=True)
        elif route == "json":
            self._json({"choices": [{"message": {"content": "整段直接回来了"}}]})
        elif route == "jsonlist":
            self._json([])
        elif route == "jsonbad":
            self._raw(b'{"choices": ["' + API_KEY.encode() + b'"')
        elif route == "cut":
            self._stream([frame("半截")], done=False)
        elif route == "afterdone":
            self._stream([b"data: [DONE]\n\n", frame("不应到达")], done=False)
        elif route == "bad":
            self._raw(b'data: {"message": "' + API_KEY.encode() + b'"\n\n')
        elif route == "list":
            self._raw(b"data: []\n\n")
        elif route == "choicesstr":
            self._raw(b'data: {"choices": "oops"}\n\n')
        elif route == "empty":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
        elif route == "slow":
            self._slow()
        elif route == "cancel":
            self._cancel()
        elif route.startswith("error") and route[5:].isdigit():
            self._error(int(route[5:]))
        else:
            self._error(404)

    # ---------- 响应形态 ----------

    def _stream(self, chunks: list[bytes], done: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for chunk in chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
            if done:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except OSError:
            pass

    def _raw(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except OSError:
            pass

    def _json(self, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except OSError:
            pass

    def _error(self, code: int) -> None:
        body = json.dumps({"error": f"invalid key {API_KEY}"}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except OSError:
            pass

    def _slow(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            self.wfile.write(frame("先到"))
            self.wfile.flush()
            time.sleep(2.0)
        except OSError:
            pass

    def _cancel(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            self.wfile.write(frame("一"))
            self.wfile.flush()
            time.sleep(0.3)
            self.wfile.write(frame("二"))
            self.wfile.flush()
        except OSError:
            pass


class ServerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _Server(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def provider(self, route: str, **overrides) -> Provider:
        data = dict(
            name="本地测试",
            base_url=f"http://127.0.0.1:{self.port}/{route}/v1",
            model="fake-model",
            api_key=API_KEY,
        )
        data.update(overrides)
        return Provider(**data)

    def start(self, route: str, **overrides) -> tuple[str, list[str]]:
        pieces: list[str] = []
        text = stream_chat(self.provider(route, **overrides),
                           [{"role": "user", "content": "原文"}], emit=pieces.append)
        return text, pieces


class TestStreamHappyPath(ServerCase):
    def test_increments_arrive_one_by_one(self) -> None:
        text, pieces = self.start("sse")
        self.assertEqual(pieces, ["去", "AI"])
        self.assertEqual(text, "去AI")

    def test_request_payload_and_auth(self) -> None:
        self.start("sse", temperature=0.2, max_tokens=1234)
        request = self.server.received[0]
        self.assertEqual(request["path"], "/sse/v1/chat/completions")
        self.assertEqual(request["headers"].get("Authorization"), f"Bearer {API_KEY}")
        body = json.loads(request["body"])
        self.assertEqual(body["model"], "fake-model")
        self.assertEqual(body["messages"], [{"role": "user", "content": "原文"}])
        self.assertIs(body["stream"], True)
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["max_tokens"], 1234)

    def test_keyless_local_request_has_no_authorization(self) -> None:
        self.start("sse", api_key="")
        self.assertNotIn("Authorization", self.server.received[0]["headers"])

    def test_comment_lines_are_skipped(self) -> None:
        text, pieces = self.start("comment")
        self.assertEqual((text, pieces), ("好", ["好"]))

    def test_done_stops_reading(self) -> None:
        text, pieces = self.start("afterdone")
        self.assertEqual((text, pieces), ("", []))

    def test_emit_is_optional(self) -> None:
        text = stream_chat(self.provider("sse"), [{"role": "user", "content": "原文"}])
        self.assertEqual(text, "去AI")


class TestNonSseFallback(ServerCase):
    def test_json_body_is_accepted(self) -> None:
        text, pieces = self.start("json")
        self.assertEqual(text, "整段直接回来了")
        self.assertEqual(pieces, ["整段直接回来了"])

    def test_json_list_is_user_facing(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("jsonlist")
        self.assertIn("choices", str(ctx.exception))

    def test_broken_json_is_redacted(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("jsonbad")
        message = str(ctx.exception)
        self.assertIn("既不是 SSE 也不是 JSON", message)
        self.assertNotIn(API_KEY, message)
        self.assertIn("密钥已隐藏", message)

    def test_empty_response_is_user_facing(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("empty")
        self.assertIn("没有返回任何内容", str(ctx.exception))


class TestStreamDefects(ServerCase):
    def test_connection_closed_without_done_returns_partial(self) -> None:
        # 兼容层常常不送 [DONE] 就关流；已收到的正文不该丢掉
        text, pieces = self.start("cut")
        self.assertEqual((text, pieces), ("半截", ["半截"]))

    def test_bad_frame_is_redacted(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("bad")
        message = str(ctx.exception)
        self.assertIn("不是合法 JSON", message)
        self.assertNotIn(API_KEY, message)
        self.assertIn("密钥已隐藏", message)

    def test_non_object_frame_is_user_facing(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("list")
        self.assertIn("JSON 对象", str(ctx.exception))

    def test_non_list_choices_is_user_facing(self) -> None:
        with self.assertRaises(LLMError) as ctx:
            self.start("choicesstr")
        self.assertIn("choices", str(ctx.exception))


class TestHttpErrors(ServerCase):
    def test_known_codes_have_hints_and_hide_key(self) -> None:
        expectations = {
            401: "HTTP 401",
            403: "HTTP 403",
            404: "/v1",
            429: "额度",
            500: "供应商侧错误",
        }
        for code, hint in expectations.items():
            with self.subTest(code=code):
                with self.assertRaises(LLMError) as ctx:
                    self.start(f"error{code}")
                message = str(ctx.exception)
                self.assertIn(hint, message)
                self.assertNotIn(API_KEY, message)
                self.assertIn("密钥已隐藏", message)


class TestTransportFailures(ServerCase):
    def test_read_timeout_reports_progress(self) -> None:
        started = time.monotonic()
        with self.assertRaises(LLMError) as ctx:
            self.start("slow", timeout=1)
        elapsed = time.monotonic() - started
        message = str(ctx.exception)
        self.assertIn("读取超时", message)
        self.assertIn(">1s", message)
        self.assertIn("已收到", message)
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, 3.5)

    def test_cancel_stops_after_first_increment(self) -> None:
        cancelled = False
        pieces: list[str] = []

        def emit(piece: str) -> None:
            nonlocal cancelled
            pieces.append(piece)
            cancelled = True

        started = time.monotonic()
        with self.assertRaises(Cancelled):
            stream_chat(self.provider("cancel"), [{"role": "user", "content": "原文"}],
                        emit=emit, should_cancel=lambda: cancelled)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(pieces, ["一"])

    def test_closed_loopback_port_is_user_facing(self) -> None:
        # 本机的回环对关闭端口是丢 SYN（表现为超时）而不是回 RST，
        # 两种表现都算连通失败，消息必须点出主机并给出排查方向。
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        dead = Provider(name="本地测试", base_url=f"http://127.0.0.1:{port}/v1",
                        model="m", api_key="", timeout=1)
        with self.assertRaises(LLMError) as ctx:
            stream_chat(dead, [{"role": "user", "content": "原文"}])
        message = str(ctx.exception)
        self.assertIn("127.0.0.1", message)
        self.assertTrue("连接不上" in message or "拒绝连接" in message, message)
        self.assertNotIn(API_KEY, message)

    def test_refused_hint_names_local_service(self) -> None:
        message = _connect_hint(ConnectionRefusedError(10061, "refused"),
                                self.provider("sse"), (API_KEY,))
        self.assertIn("拒绝连接", message)
        self.assertIn("本地服务是否已启动", message)

    def test_invalid_provider_is_rejected_before_request(self) -> None:
        broken = self.provider("sse", model="")
        with self.assertRaises(ConfigError):
            stream_chat(broken, [{"role": "user", "content": "原文"}])
        self.assertEqual(self.server.received, [])


if __name__ == "__main__":
    unittest.main()
