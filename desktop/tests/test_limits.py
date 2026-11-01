"""长文前置检查：估算口径、启用条件与拦截文案。

估算系数是刻意的保守值，先钉住公式；拦截行为对着预算边界做正负对照。
"""
from __future__ import annotations

import unittest

from deai_app.core import limits
from deai_app.core import llm
from deai_app.core.config import Provider


def provider(context_tokens: int = 0, max_tokens: int = 4096) -> Provider:
    return Provider(name="测试", base_url="http://127.0.0.1:9/v1", model="m",
                    api_key="", max_tokens=max_tokens, context_tokens=context_tokens)


class TestEstimate(unittest.TestCase):
    def test_ascii_is_four_chars_per_token(self) -> None:
        self.assertEqual(limits.estimate_tokens("abcd" * 10), 10)

    def test_cjk_is_conservative_per_char(self) -> None:
        self.assertEqual(limits.estimate_tokens("降味检查器"), 8)

    def test_mixed_and_cjk_punctuation_count_as_wide(self) -> None:
        # 全角标点也是宽字符（≥ U+2E80），与正文同价
        self.assertEqual(limits.estimate_tokens("，。a"), 4)

    def test_empty_is_zero(self) -> None:
        self.assertEqual(limits.estimate_tokens(""), 0)

    def test_messages_add_per_message_overhead(self) -> None:
        payload = limits.estimate_tokens("abcd" * 10)
        self.assertEqual(
            limits.estimate_messages([{"content": "abcd" * 10}]), payload + 8)
        self.assertEqual(
            limits.estimate_messages([{"content": "abcd" * 10}] * 3), payload * 3 + 24)


class TestCheckFit(unittest.TestCase):
    def huge(self) -> list[dict]:
        return [{"role": "user", "content": "测" * 100000}]

    def test_disabled_by_default_even_for_huge_text(self) -> None:
        limits.check_fit(self.huge(), provider())  # 不填 context_tokens 就不拦

    def test_too_long_is_refused_before_sending(self) -> None:
        with self.assertRaises(llm.LLMError) as ctx:
            limits.check_fit(self.huge(), provider(context_tokens=8192))
        message = str(ctx.exception)
        self.assertIn("还没发出", message)
        self.assertIn("测试", message)
        self.assertIn("拆", message)
        self.assertIn("8192", message)

    def test_just_inside_budget_passes(self) -> None:
        # 预算宽松时放行；「不填不拦」与「超了才拒」分别构成两侧对照
        small = [{"role": "user", "content": "abcd" * 10}]
        limits.check_fit(small, provider(context_tokens=8192))

    def test_budget_must_leave_room_for_output(self) -> None:
        with self.assertRaises(llm.LLMError) as ctx:
            limits.check_fit([{"role": "user", "content": "正文"}],
                             provider(context_tokens=4096, max_tokens=4096))
        self.assertIn("max_tokens", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
