"""提示词拼装：规则与阈值必须来自 bridge，复检轮要带上具体命中。

这里不验证模型效果，只钉住"提示词里有什么、没有什么"：
每条规则都出现、预设与强度真的改变指令、复检信息只来自本地三关报告。
"""
from __future__ import annotations

import unittest

from deai_app.bridge import engines
from deai_app.core import checkup, prompt


def slop_gate() -> checkup.GateReport:
    text = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
            "研究表明，这一工作至关重要，有效提升了治理水平。\n")
    return checkup.run(text, "zh")


class TestRuleDigest(unittest.TestCase):
    def test_every_phrasing_rule_is_listed(self) -> None:
        digest = prompt.rule_digest("zh")
        rules = engines.phrasing_rules("zh")
        self.assertGreaterEqual(len(rules), 20)
        for rule in rules:
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["label"], digest)
                self.assertIn(rule["fix"], digest)

    def test_style_metrics_and_thresholds_are_listed(self) -> None:
        digest = prompt.rule_digest("zh")
        for metric in engines.style_thresholds()["metrics"]:
            with self.subTest(metric=metric["id"]):
                self.assertIn(metric["label"], digest)
                self.assertIn(metric["fix"], digest)
        self.assertIn("25 字", digest)
        self.assertIn("20%-50%", digest)
        self.assertIn("2-4 位小数", digest)

    def test_english_digest_uses_engine_labels(self) -> None:
        digest = prompt.rule_digest("en")
        for rule in engines.phrasing_rules("en"):
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["label"], digest)


class TestSystemPrompt(unittest.TestCase):
    def test_preset_and_intensity_change_instructions(self) -> None:
        paper = prompt.system_prompt("zh", "论文", "轻")
        official = prompt.system_prompt("zh", "公文", "重")
        self.assertNotEqual(paper, official)
        self.assertIn("论文", paper)
        self.assertIn("公文", official)
        self.assertIn(prompt._INTENSITY_TEXT["轻"], paper)
        self.assertIn(prompt._INTENSITY_TEXT["重"], official)

    def test_hard_rules_cover_facts_and_format(self) -> None:
        system = prompt.system_prompt()
        for phrase in ("不得新增或编造事实", "LaTeX", "只输出改写后的正文"):
            self.assertIn(phrase, system)

    def test_unknown_preset_falls_back_to_general(self) -> None:
        self.assertIn(prompt._PRESET_TEXT["通用"], prompt.system_prompt("zh", "未知", "中"))


class TestMessages(unittest.TestCase):
    def test_first_round_has_no_feedback(self) -> None:
        messages = prompt.messages("原文一段。", "zh", "论文", "中")
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("原文一段。", messages[1]["content"])
        self.assertNotIn("上一版复检", messages[1]["content"])

    def test_retry_round_lists_actual_hits(self) -> None:
        gate = slop_gate()
        self.assertGreater(len(gate.phrasing), 0, "样本必须真的命中，否则反馈内容为空")
        messages = prompt.messages("原文一段。", "zh", "论文", "中", gate)
        feedback = messages[1]["content"]
        self.assertIn("上一版复检", feedback)
        hit = gate.phrasing[0]
        self.assertIn(hit["label"], feedback)
        self.assertIn(hit["text"], feedback)
        self.assertIn(hit["fix"], feedback)

    def test_feedback_is_capped(self) -> None:
        hits = [{"label": "套话", "text": f"命中{index}", "fix": "改具体", "line": 1,
                 "col": 1, "rule": "x", "severity": "high"} for index in range(45)]
        gate = checkup.GateReport(lang="zh", chars=10, phrasing=hits)
        feedback = prompt._feedback(gate, limit=5)
        self.assertEqual(feedback.count("- 词表·"), 5)
        self.assertIn("另有 40 处", feedback)

    def test_clean_gate_adds_no_feedback(self) -> None:
        clean = checkup.run("误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n")
        self.assertTrue(clean.clean)
        self.assertNotIn("上一版复检", prompt._feedback(clean))


if __name__ == "__main__":
    unittest.main()
