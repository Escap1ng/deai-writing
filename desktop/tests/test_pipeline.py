"""改写闭环：轮次、复检反馈、清理与取消，模型输出用脚本替身。

SSE 的真实分帧已由 test_llm_sse 对着本地服务覆盖；这里只验流水线自己的判断：
什么时候停、下一轮喂什么、最终交付哪一版。
"""
from __future__ import annotations

import unittest

from deai_app.core import checkup, llm, pipeline
from deai_app.core.config import Provider, Settings

CLEAN = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"
SLOP = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
        "研究表明，这一工作至关重要，有效提升了治理水平。\n")
PROVIDER = Provider(name="测试", base_url="http://127.0.0.1:9/v1", model="m", api_key="")
SETTINGS = Settings(preset="论文", intensity="中", max_rounds=2)


class Scripted:
    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def __call__(self, provider, messages, emit=None, should_cancel=None):
        self.calls.append({"provider": provider, "messages": messages})
        piece = self.outputs.pop(0)
        if emit:
            emit(piece)
        return piece


class TestRewriteLoop(unittest.TestCase):
    def test_stops_after_first_clean_round(self) -> None:
        events: list[str] = []
        script = Scripted(CLEAN)
        result = pipeline.rewrite(
            "原文。", PROVIDER, SETTINGS, chat=script,
            on_round_start=lambda index: events.append(f"start{index}"),
            on_round_done=lambda index, _: events.append(f"done{index}"),
        )
        self.assertEqual(len(result.rounds), 1)
        self.assertTrue(result.clean)
        self.assertEqual(result.text, CLEAN.strip())
        self.assertEqual(events, ["start1", "done1"])
        self.assertEqual(len(script.calls), 1)

    def test_retries_with_hits_until_clean(self) -> None:
        script = Scripted(SLOP, CLEAN)
        result = pipeline.rewrite("原文。", PROVIDER, SETTINGS, chat=script)
        self.assertEqual(len(result.rounds), 2)
        self.assertTrue(result.clean)
        self.assertGreater(len(result.rounds[0].gate.phrasing), 0, "第一轮必须真的脏")
        second_user = script.calls[1]["messages"][1]["content"]
        self.assertIn("上一版复检", second_user)
        self.assertIn(result.rounds[0].gate.phrasing[0]["label"], second_user)

    def test_stops_at_max_rounds_and_returns_last_version(self) -> None:
        script = Scripted(SLOP, SLOP + SLOP, SLOP * 3)
        result = pipeline.rewrite("原文。", PROVIDER, Settings(max_rounds=2), chat=script)
        self.assertEqual(len(result.rounds), 2)
        self.assertFalse(result.clean)
        self.assertEqual(len(script.calls), 2)
        self.assertEqual(result.text, (SLOP + SLOP).strip())

    def test_invisible_characters_are_stripped(self) -> None:
        script = Scripted(CLEAN.replace("误差", "误\u200b差"))
        result = pipeline.rewrite("原文。", PROVIDER, SETTINGS, chat=script)
        self.assertNotIn("\u200b", result.text)
        self.assertEqual(result.gate.invisible_total, 0)

    def test_code_fence_is_removed(self) -> None:
        script = Scripted(f"```markdown\n{CLEAN}```")
        result = pipeline.rewrite("原文。", PROVIDER, SETTINGS, chat=script)
        self.assertEqual(result.text, CLEAN.strip())
        self.assertFalse(result.text.startswith("```"))

    def test_empty_output_is_user_facing(self) -> None:
        script = Scripted("  \n")
        with self.assertRaises(llm.LLMError) as ctx:
            pipeline.rewrite("原文。", PROVIDER, SETTINGS, chat=script)
        self.assertIn("没有返回正文", str(ctx.exception))

    def test_cancel_propagates(self) -> None:
        def chat(*args, **kwargs):
            raise llm.Cancelled("已取消")

        with self.assertRaises(llm.Cancelled):
            pipeline.rewrite("原文。", PROVIDER, SETTINGS, chat=chat)

    def test_emit_receives_pieces(self) -> None:
        pieces: list[str] = []
        pipeline.rewrite("原文。", PROVIDER, SETTINGS, emit=pieces.append, chat=Scripted(CLEAN))
        self.assertEqual(pieces, [CLEAN])

    def test_language_override_reaches_prompt(self) -> None:
        script = Scripted(CLEAN)
        pipeline.rewrite("Some text.", PROVIDER, Settings(lang="en", max_rounds=1), chat=script)
        system = script.calls[0]["messages"][0]["content"]
        self.assertIn("Template opener", system)


class TestStripFence(unittest.TestCase):
    def test_only_strips_full_document_fence(self) -> None:
        self.assertEqual(pipeline.strip_fence("```\n正文\n```"), "正文")
        self.assertEqual(pipeline.strip_fence("```markdown\n正文\n```"), "正文")
        self.assertEqual(pipeline.strip_fence("正文里有 ``` 片段"), "正文里有 ``` 片段")
        self.assertEqual(pipeline.strip_fence("```\n只有开头"), "```\n只有开头")


if __name__ == "__main__":
    unittest.main()
