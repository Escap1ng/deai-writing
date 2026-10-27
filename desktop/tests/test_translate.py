"""学术翻译：方向判定、提示词约束，以及译文默认再走降 AI。

模型输出用脚本替身；真实 SSE 与窗口链路在 test_llm_sse / test_rewrite_e2e 里。
"""
from __future__ import annotations

import unittest
from pathlib import Path

from deai_app.core import checkup, llm, translate
from deai_app.core.config import Provider, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_EN = (REPO_ROOT / "examples" / "clean-sample-en.md").read_bytes().decode("utf-8-sig")
SLOP_ZH = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
           "研究表明，这一工作至关重要，有效提升了治理水平。\n")
TRANSLATED = "The baseline error dropped from 4.8% to 1.9% across 120 marked papers.\n"
PROVIDER = Provider(name="测试", base_url="http://127.0.0.1:9/v1", model="m", api_key="")


class Scripted:
    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls: list[list[dict]] = []

    def __call__(self, provider, messages, emit=None, should_cancel=None):
        self.calls.append(messages)
        piece = self.outputs.pop(0)
        if emit:
            emit(piece)
        return piece


class TestDirection(unittest.TestCase):
    def test_auto_target_is_the_other_language(self) -> None:
        self.assertEqual(translate.resolve_target("zh", "自动"), "en")
        self.assertEqual(translate.resolve_target("en", "自动"), "zh")

    def test_explicit_target(self) -> None:
        self.assertEqual(translate.resolve_target("zh", "英文"), "en")
        self.assertEqual(translate.resolve_target("en", "中文"), "zh")

    def test_source_follows_explicit_language_setting(self) -> None:
        self.assertEqual(translate.resolve_source("纯中文", "en"), "en")
        self.assertEqual(translate.resolve_source("纯中文", "自动"), "zh")

    def test_direction_label(self) -> None:
        self.assertEqual(translate.direction_label("zh", "en"), "中文→英文")
        self.assertEqual(translate.direction_label("en", "zh"), "英文→中文")


class TestPrompt(unittest.TestCase):
    def test_prompt_names_direction_and_protects_structure(self) -> None:
        messages = translate.messages("原文一段。", "zh", "en")
        system = messages[0]["content"]
        self.assertEqual(messages[1]["content"], "原文一段。")
        self.assertIn("学术论文翻译", system)
        self.assertIn("把中文文稿译成英文", system)
        for phrase in ("只输出译文", "不增删事实", "LaTeX", "术语前后一致"):
            self.assertIn(phrase, system)

    def test_english_source_translates_to_chinese(self) -> None:
        system = translate.messages("Some text.", "en", "zh")[0]["content"]
        self.assertIn("把英文文稿译成中文", system)


class TestTranslateFlow(unittest.TestCase):
    def test_translation_is_followed_by_deai_by_default(self) -> None:
        script = Scripted(TRANSLATED, CLEAN_EN)
        stages: list[tuple[str, int]] = []
        result = translate.translate(
            SLOP_ZH, PROVIDER, Settings(max_rounds=1),
            chat=script, on_stage=lambda stage, index: stages.append((stage, index)),
        )
        self.assertEqual(stages, [("translate", 0), ("deai", 1)])
        self.assertEqual(len(script.calls), 2)
        self.assertIn("学术论文翻译", script.calls[0][0]["content"])
        self.assertIn("词表级", script.calls[1][0]["content"])
        self.assertIn(TRANSLATED.strip(), script.calls[1][1]["content"])
        self.assertEqual(result.translated, TRANSLATED.strip())
        self.assertEqual(result.text, CLEAN_EN.strip())
        self.assertTrue(result.gate.clean)
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.direction(), "中文→英文")

    def test_deai_stage_uses_translated_language_rules(self) -> None:
        script = Scripted(TRANSLATED, CLEAN_EN)
        translate.translate(SLOP_ZH, PROVIDER, Settings(max_rounds=1), chat=script)
        system = script.calls[1][0]["content"]
        self.assertIn("Template opener", system)

    def test_deai_can_be_disabled_in_config(self) -> None:
        script = Scripted(TRANSLATED)
        result = translate.translate(
            SLOP_ZH, PROVIDER, Settings(auto_deai_after_translate=False), chat=script)
        self.assertEqual(len(script.calls), 1)
        self.assertEqual(result.rounds, [])
        self.assertEqual(result.text, TRANSLATED.strip())
        self.assertEqual(result.gate.lang, "en")

    def test_empty_translation_is_user_facing(self) -> None:
        script = Scripted("  \n")
        with self.assertRaises(llm.LLMError) as ctx:
            translate.translate(SLOP_ZH, PROVIDER, Settings(), chat=script)
        self.assertIn("没有返回译文", str(ctx.exception))

    def test_fence_and_invisible_characters_are_removed(self) -> None:
        script = Scripted(f"```markdown\n{TRANSLATED.replace('error', 'er\u200bror')}```",
                          CLEAN_EN)
        result = translate.translate(SLOP_ZH, PROVIDER, Settings(max_rounds=1), chat=script)
        self.assertNotIn("```", result.translated)
        self.assertNotIn("\u200b", result.translated)

    def test_explicit_target_overrides_auto(self) -> None:
        script = Scripted(TRANSLATED, CLEAN_EN)
        result = translate.translate(SLOP_ZH, PROVIDER,
                                     Settings(max_rounds=1, translate_target="中文"), chat=script)
        self.assertEqual(result.target_lang, "zh")
        self.assertIn("把中文文稿译成中文", script.calls[0][0]["content"])


if __name__ == "__main__":
    unittest.main()
