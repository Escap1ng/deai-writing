"""llm — OpenAI 兼容 /chat/completions 的流式调用，只用标准库。

为什么不用 requests/httpx：exe 体积与依赖面。代价是 SSE 分帧与错误映射自己写，
所以 tests/test_llm_sse.py 对着一个真的本地 HTTP 服务打（不是假函数），
覆盖增量、[DONE]、非 SSE 回退、401/404/429/5xx、超时、流中断与取消。

错误文本一律先过 config.redact()：供应商常把请求头回显在错误体里，密钥不能跟着进日志。
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

from deai_app.core import config
from deai_app.core.config import Provider

__all__ = ["Cancelled", "LLMError", "stream_chat"]

_PREFIX = "data:"
_MAX_BODY_SNIPPET = 300

Emit = Callable[[str], None]
CancelCheck = Callable[[], bool]

_HTTP_HINT = {
    401: "密钥或权限不被接受（HTTP 401）：核对 api_key 与 base_url 是否属于同一供应商",
    403: "被供应商拒绝访问（HTTP 403）：核对密钥权限与账户状态",
    404: "接口路径不存在（HTTP 404）：多数情况是 base_url 少了 /v1 或多写了路径",
    429: "触发限流或额度用尽（HTTP 429）：稍后重试，或改用额度内的模型",
}


class LLMError(RuntimeError):
    """面向用户的接口错误；message 里不含密钥。"""


class Cancelled(LLMError):
    """用户主动取消，不算故障。"""


def _headers(provider: Provider) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "deai-desktop",
    }
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    return headers


def _payload(provider: Provider, messages: Sequence[dict], stream: bool) -> bytes:
    body = {
        "model": provider.model,
        "messages": list(messages),
        "stream": stream,
        "temperature": provider.temperature,
        "max_tokens": provider.max_tokens,
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _http_error(exc: urllib.error.HTTPError, secrets: Sequence[str]) -> LLMError:
    code = exc.code
    snippet = ""
    try:
        snippet = _decode(exc.read(_MAX_BODY_SNIPPET)).strip().replace("\n", " ")
    except OSError:
        pass
    finally:
        exc.close()
    hint = _HTTP_HINT.get(code, "服务端返回错误（HTTP {code}）").format(code=code)
    if code >= 500:
        hint = f"供应商侧错误（HTTP {code}）：稍后重试或换模型"
    detail = f"：{snippet}" if snippet else ""
    return LLMError(config.redact(hint + detail, secrets))


def _delta_content(frame: str, secrets: Sequence[str] = ()) -> str:
    try:
        data = json.loads(frame)
    except ValueError as exc:
        raise LLMError(config.redact(
            f"响应帧不是合法 JSON：{frame[:80]!r}（{exc}）", secrets)) from exc
    if not isinstance(data, dict):
        raise LLMError(config.redact(f"响应帧不是 JSON 对象：{frame[:80]!r}", secrets))
    choices = data.get("choices")
    if choices is None:
        return ""
    if not isinstance(choices, list):
        raise LLMError("响应帧里的 choices 不是数组")
    if not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMError("响应帧里的 choices[0] 不是对象")
    delta = first.get("delta") or {}
    if not isinstance(delta, dict):
        delta = {}
    if isinstance(delta.get("content"), str):
        return delta["content"]
    # 少数兼容层把正文放在 message.content 而非 delta.content
    message = first.get("message") or {}
    if not isinstance(message, dict):
        return ""
    return message.get("content", "") if isinstance(message.get("content"), str) else ""


def _open(request: urllib.request.Request, provider: Provider):
    """本地服务绕过系统代理：Windows 的注册表代理会把 127.0.0.1 也接管成 502。"""
    if provider.is_local():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=provider.timeout)
    return urllib.request.urlopen(request, timeout=provider.timeout)


def stream_chat(
    provider: Provider,
    messages: Sequence[dict],
    emit: Emit | None = None,
    should_cancel: CancelCheck | None = None,
) -> str:
    """流式取回一次补全，返回完整文本；emit 每来一段正文就收到增量。"""
    provider.validate()
    secrets = (provider.api_key,)
    request = urllib.request.Request(provider.endpoint(), data=_payload(provider, messages, True),
                                     headers=_headers(provider), method="POST")
    parts: list[str] = []
    plain: list[str] = []
    saw_event = False
    try:
        response = _open(request, provider)
    except urllib.error.HTTPError as exc:
        raise _http_error(exc, secrets) from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise LLMError(_connect_hint(exc, provider, secrets)) from exc

    try:
        with response:
            while True:
                if should_cancel and should_cancel():
                    raise Cancelled("已取消")
                try:
                    raw = response.readline()
                except socket.timeout as exc:
                    raise LLMError(
                        f"读取超时（>{provider.timeout}s），已收到 {sum(len(p) for p in parts)} 字：可拆小段落再试"
                    ) from exc
                if not raw:
                    break
                text = _decode(raw).strip()
                if not text or text.startswith(":"):
                    continue
                if not text.startswith(_PREFIX):
                    plain.append(text)  # 不是 SSE：攒起来留给整体回退
                    continue
                saw_event = True
                frame = text[len(_PREFIX):].strip()
                if frame == "[DONE]":
                    break
                piece = _delta_content(frame, secrets)
                if piece:
                    parts.append(piece)
                    if emit:
                        emit(piece)
    except Cancelled:
        raise
    except LLMError:
        raise
    except urllib.error.HTTPError as exc:
        raise _http_error(exc, secrets) from exc
    except (socket.timeout, OSError) as exc:
        raise LLMError(_connect_hint(exc, provider, secrets)) from exc

    if saw_event:
        return "".join(parts)
    return _fallback_non_sse(plain, provider, emit, secrets)


def _fallback_non_sse(lines: list[str], provider: Provider, emit: Emit | None,
                      secrets: Sequence[str]) -> str:
    """有些兼容层忽略 stream=true，直接回一个 JSON 对象——这种情况也要能取到正文。"""
    raw = "\n".join(lines).strip()
    if not raw:
        raise LLMError("接口没有返回任何内容：检查 base_url 与 model")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise LLMError(config.redact(f"响应既不是 SSE 也不是 JSON：{raw[:120]!r}（{exc}）", secrets)) from exc
    if not isinstance(data, dict):
        raise LLMError("响应不是含 choices 的 JSON 对象，无法解析")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError(config.redact(f"响应缺少 choices：{raw[:160]!r}", secrets))
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message")
    content = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(content, str):
        raise LLMError("响应里的正文不是文本，无法解析")
    if content and emit:
        emit(content)
    return content


def _connect_hint(exc: BaseException, provider: Provider, secrets: Sequence[str]) -> str:
    host = provider.base_url.split("//", 1)[-1].split("/", 1)[0]
    if isinstance(exc, socket.timeout) or "timed out" in str(exc).lower():
        text = f"连接不上 {host}（超时 {provider.timeout}s）：检查网络、代理，或把 timeout 调大"
    elif "getaddrinfo" in str(exc).lower() or "name or service" in str(exc).lower():
        text = f"域名解析失败：{host} 打不通，检查地址拼写与网络"
    elif "refused" in str(exc).lower():
        text = f"{host} 拒绝连接：本地服务是否已启动？"
    else:
        text = f"请求 {host} 失败：{exc}"
    return config.redact(text, secrets)
