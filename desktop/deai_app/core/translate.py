"""translate — 学术翻译，译文默认再走一遍降 AI 闭环。

翻译只负责跨语言：保住事实、数字、引用、LaTeX 与段落结构；
去 AI 腔仍由 pipeline 用本地三关驱动，规则不在这里另抄一份。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from deai_app.bridge import engines
from deai_app.core import checkup, llm, pipeline
from deai_app.core.config import Provider, Settings

TARGETS = ("自动", "英文", "中文")
STAGE_TRANSLATE = "translate"
STAGE_DEAI = "deai"

StageStart = Callable[[str, int], None]
RoundDone = Callable[[int, pipeline.RoundResult], None]

_LANG_NAME = {"zh": "中文", "en": "英文"}


@dataclass
class TranslationResult:
    text: str
    translated: str
    gate: checkup.GateReport
    source_lang: str
    target_lang: str
    rounds: list[pipeline.RoundResult] = field(default_factory=list)

    def direction(self) -> str:
        return direction_label(self.source_lang, self.target_lang)


def resolve_source(text: str, setting: str) -> str:
    return setting if setting in ("zh", "en") else checkup.detect_lang(text)


def resolve_target(source_lang: str, setting: str) -> str:
    if setting == "英文":
        return "en"
    if setting == "中文":
        return "zh"
    return "en" if source_lang == "zh" else "zh"


def direction_label(source_lang: str, target_lang: str) -> str:
    return f"{_LANG_NAME.get(source_lang, source_lang)}→{_LANG_NAME.get(target_lang, target_lang)}"


def messages(text: str, source_lang: str, target_lang: str) -> list[dict]:
    target = _LANG_NAME.get(target_lang, target_lang)
    source = _LANG_NAME.get(source_lang, source_lang)
    system = (
        f"你是学术论文翻译，把{source}文稿译成{target}。\n"
        "硬性要求：\n"
        "1. 只输出译文，不要说明、对照表或 Markdown 代码围栏。\n"
        "2. 不增删事实、数字、文献、案例与限定条件；不得编造来源。\n"
        "3. 保留 Markdown、LaTeX 命令、公式、引用标记、图表编号与段落结构。\n"
        "4. 术语前后一致，采用目标语言的学术书面语；句法自然，不逐字硬译。\n"
        "5. 译文随后会统一降 AI 腔，这一步只需准确、通顺、克制。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


def translate(
    text: str,
    provider: Provider,
    settings: Settings,
    *,
    emit: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_stage: StageStart | None = None,
    on_round_done: RoundDone | None = None,
    chat: pipeline.Chat | None = None,
) -> TranslationResult:
    call = chat or llm.stream_chat
    source_lang = resolve_source(text, settings.lang)
    target_lang = resolve_target(source_lang, settings.translate_target)
    if on_stage:
        on_stage(STAGE_TRANSLATE, 0)
    raw = call(provider, messages(text, source_lang, target_lang),
               emit=emit, should_cancel=should_cancel)
    if should_cancel and should_cancel():
        raise llm.Cancelled("已取消")
    translated = engines.invisible_clean(pipeline.strip_fence(raw))[0]
    if not translated.strip():
        raise llm.LLMError("模型没有返回译文：换一个模型，或把段落拆短再试")

    if settings.auto_deai_after_translate:
        deai = pipeline.rewrite(
            translated,
            provider,
            replace(settings, preset="论文", lang=target_lang),
            emit=emit,
            should_cancel=should_cancel,
            on_round_start=(lambda index: on_stage(STAGE_DEAI, index)) if on_stage else None,
            on_round_done=on_round_done,
            chat=call,
        )
        return TranslationResult(deai.text, translated, deai.gate, source_lang, target_lang,
                                 deai.rounds)

    gate = checkup.run(translated, target_lang)
    return TranslationResult(translated, translated, gate, source_lang, target_lang, [])
