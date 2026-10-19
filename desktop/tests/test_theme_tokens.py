"""主题 token 的可用性与可维护性：色值全部来自 theme.json，对比度必须实测达标。

对比度用 WCAG 2.1 公式实测，不写"看起来够"这种话；不达标就是红。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import deai_app
import tests.test_layering as layering
from deai_app.ui import theme as theme_mod
from deai_app.ui.theme import ThemeError, contrast_ratio, load_theme, parse_hex

APP_DIR = Path(deai_app.__file__).resolve().parent
HEX_LITERAL = re.compile(r"#[0-9A-Fa-f]{6}\b")


class TestThemeValues(unittest.TestCase):
    def setUp(self) -> None:
        self.theme = load_theme()

    def test_math_is_sane(self) -> None:
        self.assertAlmostEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(contrast_ratio("#FFFFFF", "#FFFFFF"), 1.0, places=6)
        self.assertEqual(parse_hex("#abc"), (170, 187, 204))

    def test_bad_hex_raises(self) -> None:
        for bad in ("#12345", "zzvvww", "#12345g"):
            with self.assertRaises(ThemeError, msg=bad):
                parse_hex(bad)

    def test_measured_contrast_meets_floors(self) -> None:
        rows = []
        for rule in self.theme.raw["contrast"]:
            fg, bg = self.theme.color(rule["fg"]), self.theme.color(rule["bg"])
            ratio = contrast_ratio(fg, bg)
            rows.append((rule["fg"], fg, rule["bg"], bg, ratio, float(rule["min"])))
            self.assertGreaterEqual(ratio, float(rule["min"]), f"{rule['fg']} on {rule['bg']}")
        print("\n实测对比度（WCAG 2.1）")
        for fg, fg_hex, bg, bg_hex, ratio, floor in rows:
            print(f"  {fg:<16} {fg_hex}  on  {bg:<14} {bg_hex}  = {ratio:>5.2f}  (要求 ≥{floor})")

    def test_required_tokens_exist(self) -> None:
        for name in ("window_bg", "editor_bg", "text", "ink_bg", "ink_fg", "divider",
                     "gate_pass", "gate_warn", "gate_block", "surface_hover", "surface_selected",
                     "selection_bg", "mark_bg", "segment_track", "segment_pill",
                     "segment_border", "segment_text"):
            self.theme.color(name)
        for name in ("width", "height", "min_width", "min_height", "corner_radius",
                     "titlebar_height", "statusbar_height", "resize_grip", "content_padding"):
            self.assertIsInstance(self.theme.win(name), int)
        for name in ("meta", "body", "emphasis", "title"):
            self.assertGreater(self.theme.size(name), 0)


class TestNoBareValues(unittest.TestCase):
    """颜色只能写在 theme.json 里；源码出现裸十六进制色值即越界。"""

    def test_sources_have_no_hex_literal(self) -> None:
        self.assertTrue(HEX_LITERAL.search("bg = '#141416'"), "探测器本身失效：匹配不到裸色值")
        offenders = []
        for folder in ("ui", "core", "bridge"):
            for path in (APP_DIR / folder).rglob("*.py"):
                for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if HEX_LITERAL.search(line):
                        offenders.append(f"{path.relative_to(APP_DIR).as_posix()}:{i}")
        self.assertEqual(offenders, [], f"源码里有裸色值：{offenders}")

    def test_theme_module_is_tkinter_free(self) -> None:
        source = (APP_DIR / "ui" / "theme.py").read_text(encoding="utf-8")
        spelled = [name for _, name in layering.imports_of(source, "ui/theme.py")]
        self.assertFalse([s for s in spelled if s.startswith("tkinter")], spelled)


if __name__ == "__main__":
    unittest.main()
