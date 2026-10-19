"""UI 契约与体检行为：token 引用不许悬空，三关报告数字要真实可核。

这一份是无头测试（不开窗口）：窗口能否画出来要人眼看，
但"引用的色值键不存在""报告里少了改法提示""语言判定反了"这类缺陷由这里兜住。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

import deai_app
from deai_app.core import checkup
from deai_app.ui import app as ui_app
from deai_app.ui.theme import load_theme

APP_DIR = Path(deai_app.__file__).resolve().parent
DESKTOP_ROOT = APP_DIR.parent
REPO_ROOT = DESKTOP_ROOT.parent
COLOR_REF = re.compile(r'\.(?:color|win|size)\("([A-Za-z_][A-Za-z0-9_]*)"|font_for\([\w.]+, "([A-Za-z_][A-Za-z0-9_]*)')


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def token_names() -> set[str]:
    data = json.loads((APP_DIR / "assets" / "theme.json").read_text(encoding="utf-8"))
    return set(data["color"]) | set(data["window"]) | set(data["font"]["size"])


class TestThemeTokenReferences(unittest.TestCase):
    def test_every_referenced_token_exists(self) -> None:
        known = token_names()
        dangling = []
        for path in list(APP_DIR.rglob("*.py")):
            for match in COLOR_REF.finditer(path.read_text(encoding="utf-8")):
                name = next(group for group in match.groups() if group)
                if name not in known:
                    dangling.append(f"{path.relative_to(APP_DIR).as_posix()} → {name}")
        self.assertEqual(dangling, [], f"引用了 theme.json 里不存在的键：{dangling}")

    def test_probe_can_fail(self) -> None:
        self.assertTrue(COLOR_REF.search('x = theme.color("nope_key")'))
        self.assertTrue(COLOR_REF.search('f = font_for(theme, "bodiy")'))


class TestGlyphs(unittest.TestCase):
    def test_codepoints_are_as_documented(self) -> None:
        self.assertEqual(ord(ui_app.MINIMIZE_GLYPH), 0x2014)
        self.assertEqual(ord(ui_app.MAXIMIZE_GLYPH), 0x25A1)
        self.assertEqual(ord(ui_app.CLOSE_GLYPH), 0x2715)
        glyphs = {ui_app.MINIMIZE_GLYPH, ui_app.MAXIMIZE_GLYPH, ui_app.CLOSE_GLYPH}
        self.assertEqual(len(glyphs), 3, "三个键位不能共用一个字形")


class TestCheckup(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.slop = read(REPO_ROOT / "examples" / "slop-sample.md")
        cls.style_slop = read(REPO_ROOT / "examples" / "style-slop-sample.md")
        cls.clean = read(REPO_ROOT / "examples" / "clean-sample.md")
        cls.clean_en = read(REPO_ROOT / "examples" / "clean-sample-en.md")

    def test_clean_sample_passes_all_three(self) -> None:
        report = checkup.run(self.clean)
        self.assertTrue(report.clean, f"正例被判有痕：{report.phrasing} {report.style}")
        self.assertFalse(report.blocked)
        self.assertEqual(report.lang, "zh")

    def test_phrasing_slop_reports_hits_but_is_not_structurally_blocked(self) -> None:
        report = checkup.run(self.slop)
        self.assertGreater(len(report.phrasing), 0)
        self.assertFalse(report.clean)

    def test_style_slop_is_blocked(self) -> None:
        report = checkup.run(self.style_slop)
        self.assertGreater(len(report.style), 0)
        self.assertIn(report.style_risk, ("高", "极高"))
        self.assertTrue(report.blocked)

    def test_invisible_count_and_codepoints(self) -> None:
        text = "方\u200b法\u200b有效\u200b"
        report = checkup.run(text)
        self.assertEqual(report.invisible_total, 3)
        self.assertIn("U+200B×3", report.codepoints())

    def test_lang_detection_both_directions(self) -> None:
        self.assertEqual(checkup.detect_lang(self.clean_en), "en")
        self.assertEqual(checkup.detect_lang(self.clean), "zh")
        self.assertEqual(checkup.detect_lang("这是一段中文，夹杂少量 English 术语。"), "zh")

    def test_render_carries_rule_ids_and_fixes(self) -> None:
        report = checkup.run(self.slop)
        text = checkup.render(report, self.slop)
        self.assertIn("【词表级】", text)
        self.assertIn("改法：", text)
        for hit in report.phrasing[:3]:
            self.assertIn(hit["rule"], text)

    def test_render_truncates_long_lists(self) -> None:
        text = "综上所述，" * 40
        report = checkup.run(text)
        rendered = checkup.render(report, text, limit=5)
        self.assertIn("另有", rendered)
        self.assertGreater(len(report.phrasing), 5)

    def test_char_count_uses_one_definition(self) -> None:
        """页脚与报告都走 visible_chars，否则同一屏会出现两个字数。"""
        self.assertEqual(checkup.visible_chars("ab\ncd\r\n"), 4)
        report = checkup.run(self.slop)
        self.assertEqual(report.chars, checkup.visible_chars(self.slop))
        self.assertIn(f"输入 {report.chars} 字", checkup.render(report, self.slop))

    def test_empty_input_is_not_an_error(self) -> None:
        report = checkup.run("")
        self.assertTrue(report.clean)
        self.assertEqual(report.lang, "zh")


class TestCheckupCli(unittest.TestCase):
    """命令行入口跑的是同一条路：无界面模式必须真能出报告。"""

    def test_checkup_exits_1_on_slop_and_prints_report(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "deai_app", "--checkup",
             str(REPO_ROOT / "examples" / "slop-sample.md")],
            capture_output=True, text=True, encoding="utf-8", cwd=str(DESKTOP_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr[:300])
        self.assertIn("【词表级】", proc.stdout)

    def test_checkup_exits_0_on_clean_sample(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "deai_app", "--checkup",
             str(REPO_ROOT / "examples" / "clean-sample.md")],
            capture_output=True, text=True, encoding="utf-8", cwd=str(DESKTOP_ROOT), timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("门禁：通过", proc.stdout)


if __name__ == "__main__":
    unittest.main()
