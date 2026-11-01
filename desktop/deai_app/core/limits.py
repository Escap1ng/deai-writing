"""limits — 长文前置检查：按字符估算 tokens，超过供应商上下文就在发出前拦下。

估算是粗的（各模型 tokenizer 不同），只对填了 context_tokens 的供应商启用；
数字一律往偏大估，宁可早一步请用户拆稿，也不把整篇送进一个注定 400 的请求。
"""
from __future__ import annotations

import math

from deai_app.core import llm
from deai_app.core.config import Provider

#: 估算系数：中日韩区每个字按 1.6 tokens 计，其余按每 4 字符 1 token 计，两条都偏保守。
_CJK_THRESHOLD = 0x2E80
_CJK_TOKENS = 1.6
_OTHER_CHARS_PER_TOKEN = 4
_PER_MESSAGE_OVERHEAD = 8


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    wide = sum(1 for ch in text if ord(ch) >= _CJK_THRESHOLD)
    narrow = len(text) - wide
    return math.ceil(wide * _CJK_TOKENS + narrow / _OTHER_CHARS_PER_TOKEN)


def estimate_messages(messages: list[dict]) -> int:
    payload = sum(estimate_tokens(str(item.get("content", ""))) for item in messages)
    return payload + _PER_MESSAGE_OVERHEAD * len(messages)


def check_fit(messages: list[dict], provider: Provider) -> None:
    """第 0 轮发送前的检查；超限抛 llm.LLMError，信息直接面向用户。"""
    if provider.context_tokens <= 0:
        return
    budget = provider.context_tokens - provider.max_tokens
    if budget <= 0:
        raise llm.LLMError(
            f"还没发出请求：「{provider.name}」的 context_tokens（{provider.context_tokens}）"
            f"要大于输出预留 max_tokens（{provider.max_tokens}），否则生成都放不下")
    limit = int(budget * 0.9)
    used = estimate_messages(messages)
    if used <= limit:
        return
    raise llm.LLMError(
        f"还没发出请求：全文约 {used} tokens，超过「{provider.name}」的输入预算 "
        f"{limit} tokens。把稿子拆成几段分别处理，或把供应商的 context_tokens 填大一些"
        f"（现在 {provider.context_tokens}，已扣除输出预留 {provider.max_tokens}）")
