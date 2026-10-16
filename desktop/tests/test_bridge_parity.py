"""闸门口径一致性：App 内检查结果的数字，必须等于用户手跑 CLI 的数字。

做法是同一份文本走两条路——bridge 的内存路径 vs 子进程跑 code/ 的 CLI（--json）——
逐条比对命中位置与结构风险等级。任何一侧改了规则或阈值，这里就红。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from deai_app import paths
from deai_app.bridge import engines

REPO_ROOT = paths.CODE_DIR.parent
CODE_DIR = paths.CODE_DIR
TEXT_SUFFIXES = (".md", ".tex")

# 词表级反例：开头模板腔 + 空泛收尾，必须命中
SLOP_PHRASING = (
    "综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
    "研究表明，这一工作至关重要，效果很好，有望在较大程度上提升效率。"
)
# 结构级反例：连续 4 句同形开头（MIN_SENTENCE=8 以上）+ 6 位小数，实测触发 2 处
SLOP_STYLE = (
    "本研究的基线模型在 120 份卷面上给出误差率 3.14159265 的实测记录。"
    "本研究的对照组在同一批样本上复跑了三轮，把漏检数从 18 个压到 7 个。"
    "本研究的复核环节由两名标注员独立完成，分歧条目按事先约定的一致规则处理。\n\n"
    "本研究的误差分布集中在中等长度样本，短句与长句两端都保持较低水平。\n"
)
CLEAN_TEXT = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"


def read_like_cli(path: Path) -> str:
    """按 CLI 的读法取文本（utf-8-sig 会吃掉前置 BOM）。"""
    return path.read_bytes().decode("utf-8-sig")


def lang_of(path: Path) -> str:
    return "en" if path.stem.endswith("-en") else "zh"


def run_cli(module: str, target: Path, lang: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(CODE_DIR / f"{module}.py"), str(target), "--json", "--lang", lang],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"{module} 退出码 {proc.returncode}：{proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


def corpus() -> list[Path]:
    files = sorted(p for p in (REPO_ROOT / "examples").iterdir() if p.suffix in TEXT_SUFFIXES)
    files.append(REPO_ROOT / "docs" / "deai-rules.md")
    return files


def phrasing_key(hit: dict) -> tuple:
    return (hit["line"], hit["col"], hit["rule"], hit["text"])


def style_key(hit: dict) -> tuple:
    return (hit["line"], hit["metric"], hit["text"], hit["severity"])


class TestGateParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if getattr(sys, "frozen", False):
            raise unittest.SkipTest("exe 内不跑子进程 CLI 对比")
        cls.tmp = tempfile.TemporaryDirectory(prefix="deai-parity-")
        cls.tmpdir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def test_phrasing_matches_cli_on_corpus(self) -> None:
        for path in corpus():
            with self.subTest(file=path.name):
                cli = run_cli("check_phrasing", path, lang_of(path))
                mine = engines.phrasing_scan(read_like_cli(path), lang_of(path))
                self.assertEqual(mine["rules"], cli["rules"], "词表规则条数不一致")
                self.assertEqual(
                    sorted(map(phrasing_key, mine["hits"])),
                    sorted(map(phrasing_key, cli["hits"])),
                )

    def test_style_matches_cli_on_corpus(self) -> None:
        for path in corpus():
            with self.subTest(file=path.name):
                cli = run_cli("check_style", path, lang_of(path))
                mine = engines.style_scan(read_like_cli(path), lang_of(path))
                self.assertEqual(mine["chars"], cli["chars"], "字数口径不一致")
                self.assertEqual(mine["risk"], cli["risk"], "风险等级不一致")
                self.assertEqual(
                    sorted(map(style_key, mine["hits"])),
                    sorted(map(style_key, cli["hits"])),
                )

    def test_synthetic_text_also_matches_cli(self) -> None:
        for name, text in (
            ("slop_phrasing.md", SLOP_PHRASING),
            ("slop_style.md", SLOP_STYLE),
            ("clean.md", CLEAN_TEXT),
        ):
            with self.subTest(case=name):
                target = self.tmpdir / name
                target.write_text(text, encoding="utf-8")
                for module, key_fn, mine_fn in (
                    ("check_phrasing", phrasing_key, engines.phrasing_scan),
                    ("check_style", style_key, engines.style_scan),
                ):
                    cli = run_cli(module, target, "zh")
                    mine = mine_fn(text, "zh")
                    self.assertEqual(sorted(map(key_fn, mine["hits"])),
                                     sorted(map(key_fn, cli["hits"])), f"{module}/{name}")

    def test_corpus_actually_contains_hits(self) -> None:
        """语料里必须真有命中：否则逐文件"相等"可能只是两个空集在相等。"""
        for module, mine_fn in (("check_phrasing", engines.phrasing_scan),
                                ("check_style", engines.style_scan)):
            with self.subTest(module=module):
                bridge_total = sum(len(mine_fn(read_like_cli(p), lang_of(p))["hits"]) for p in corpus())
                cli_total = sum(len(run_cli(module, p, lang_of(p))["hits"]) for p in corpus())
                self.assertGreater(bridge_total, 0, "全语料零命中，样本失去意义")
                self.assertEqual(bridge_total, cli_total)

    def test_negative_and_positive_control(self) -> None:
        """反例必须非零、正例必须为零——否则以上比对可能是两个空集在相等。"""
        self.assertGreater(len(engines.phrasing_scan(SLOP_PHRASING)["hits"]), 0)
        self.assertGreater(len(engines.style_scan(SLOP_STYLE)["hits"]), 0)
        self.assertEqual(len(engines.phrasing_scan(CLEAN_TEXT)["hits"]), 0)
        self.assertEqual(engines.style_scan(CLEAN_TEXT)["risk"], "低")
        clean = REPO_ROOT / "examples" / "clean-sample.md"
        self.assertEqual(len(engines.phrasing_scan(read_like_cli(clean))["hits"]), 0)


class TestRuleDigestSource(unittest.TestCase):
    """提示词只能从引擎取规则，不许在 App 里另抄一份。"""

    def test_phrasing_rules_cover_all_rules(self) -> None:
        rules = engines.phrasing_rules()
        self.assertEqual(len(rules), engines.phrasing_scan("")["rules"])
        for rule in rules:
            self.assertTrue(rule["id"] and rule["label"] and rule["fix"], rule["id"])

    def test_style_metrics_cover_six_indicators(self) -> None:
        data = engines.style_thresholds()
        self.assertEqual(len(data["metrics"]), 6)
        self.assertIn("max_decimals", data["thresholds"])


class TestInvisibleBridge(unittest.TestCase):
    """字符级走的是引擎自带的文本函数，这里钉住检出→清理→复检。"""

    def test_strips_known_invisible_chars(self) -> None:
        for ch in ("\u200b", "\u200d", "\u2060", "\ufeff"):
            with self.subTest(ch=f"U+{ord(ch):04X}"):
                dirty = f"方法{ch}有效"
                self.assertEqual(sum(engines.invisible_scan(dirty).values()), 1)
                cleaned, removed = engines.invisible_clean(dirty)
                self.assertEqual(sum(removed.values()), 1)
                self.assertEqual(cleaned, "方法有效")
                self.assertEqual(sum(engines.invisible_scan(cleaned).values()), 0)

    def test_clean_text_is_untouched(self) -> None:
        text = "方法与结论均不含隐写字符。\n"
        self.assertEqual(sum(engines.invisible_scan(text).values()), 0)
        cleaned, removed = engines.invisible_clean(text)
        self.assertEqual((cleaned, sum(removed.values())), (text, 0))

    def test_cjk_variant_selector_survives(self) -> None:
        """CJK 后的变体选择符是合法正字：非 CJK 后要剥，CJK 后不能剥。"""
        vs = "\ufe00"
        self.assertEqual(sum(engines.invisible_scan(f"note{vs}text").values()), 1)
        self.assertEqual(sum(engines.invisible_scan(f"汉字{vs}测试").values()), 0)


if __name__ == "__main__":
    unittest.main()
