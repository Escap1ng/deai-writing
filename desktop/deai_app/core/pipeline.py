"""pipeline — 改写闭环：生成一轮、本地三关复检，带命中再修，最多 N 轮。

模型调用与检查器都从参数或 core/bridge 取，方便在无界面环境里替换成脚本化输出；
真正的重试依据只有本地命中清单，不靠模型自述"已改好"。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from deai_app.bridge import engines
from deai_app.core import checkup, llm, prompt
from deai_app.core.config import Provider, Settings

Emit = Callable[[str], None]
CancelCheck = Callable[[], bool]
RoundStart = Callable[[int], None]
RoundDone = Callable[[int, "RoundResult"], None]
Chat = Callable[..., str]

MAX_ROUNDS = 4


@dataclass
class RoundResult:
    index: int
    text: str
    gate: checkup.GateReport


@dataclass
class RewriteResult:
    text: str
    gate: checkup.GateReport
    rounds: list[RoundResult] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.gate.clean


def strip_fence(text: str) -> str:
    """模型常把整篇塞进一个代码围栏；只在围栏包住全文时拆掉。"""
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return stripped
    first_line, separator, rest = stripped.partition("\n")
    if not separator or not rest.rstrip().endswith("```"):
        return stripped
    return rest.rstrip()[:-3].rstrip()


def rewrite(
    text: str,
    provider: Provider,
    settings: Settings,
    *,
    emit: Emit | None = None,
    should_cancel: CancelCheck | None = None,
    on_round_start: RoundStart | None = None,
    on_round_done: RoundDone | None = None,
    chat: Chat | None = None,
) -> RewriteResult:
    call = chat or llm.stream_chat
    lang = settings.lang if settings.lang in ("zh", "en") else checkup.detect_lang(text)
    rounds: list[RoundResult] = []
    current = text
    gate: checkup.GateReport | None = None
    max_rounds = max(1, min(int(settings.max_rounds), MAX_ROUNDS))

    for index in range(1, max_rounds + 1):
        if on_round_start:
            on_round_start(index)
        messages = prompt.messages(current, lang, settings.preset, settings.intensity, gate)
        raw = call(provider, messages, emit=emit, should_cancel=should_cancel)
        if should_cancel and should_cancel():
            raise llm.Cancelled("已取消")
        cleaned = engines.invisible_clean(strip_fence(raw))[0]
        if not cleaned.strip():
            raise llm.LLMError("模型没有返回正文：换一个模型，或把段落拆短再试")
        gate = checkup.run(cleaned, lang)
        result = RoundResult(index=index, text=cleaned, gate=gate)
        rounds.append(result)
        if on_round_done:
            on_round_done(index, result)
        if gate.clean:
            break
        current = cleaned

    return RewriteResult(text=rounds[-1].text, gate=rounds[-1].gate, rounds=rounds)
