"""theme — 读 assets/theme.json，提供色值/字号/尺寸的唯一取用口。

本模块**不 import 任何界面工具包**：token 校验与对比度计算要能在无界面环境跑（CI、--checkup、
打包自检都靠它）。控件里出现裸色值或裸字号就是越界，tests/test_theme_tokens.py 会拦。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from deai_app import paths

__all__ = ["Theme", "ThemeError", "contrast_ratio", "load_theme"]

_REQUIRED_SECTIONS = ("color", "font", "window")


class ThemeError(RuntimeError):
    """主题文件缺失、字段不全或对比度不达标。"""


def _channel(value: int) -> float:
    v = value / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    rgb = parse_hex(hex_color)
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def parse_hex(hex_color: str) -> tuple[int, int, int]:
    text = hex_color.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ThemeError(f"色值不是 #RRGGBB：{hex_color!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as exc:
        raise ThemeError(f"色值含非十六进制字符：{hex_color!r}") from exc


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 对比度，范围 1.0–21.0。"""
    lighter = max(_relative_luminance(fg), _relative_luminance(bg))
    darker = min(_relative_luminance(fg), _relative_luminance(bg))
    return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True)
class Theme:
    raw: dict

    def color(self, name: str) -> str:
        return self._pick("color", name)

    def win(self, name: str):
        return self._pick("window", name)

    def shell(self, name: str):
        return self._pick("shell", name)

    def family(self, kind: str = "cjk") -> str:
        return self._pick("font", f"family_{kind}")

    def size(self, name: str) -> int:
        return int(self._pick("font", "size")[name])

    def _pick(self, section: str, name: str):
        try:
            value = self.raw[section][name]
        except KeyError as exc:
            raise ThemeError(f"主题缺少 {section}.{name}") from exc
        return value


def load_theme(force: bool = False) -> Theme:
    if force:
        load_theme.cache_clear()
    theme = _read()
    problems = validate(theme)
    if problems:
        raise ThemeError("主题校验未通过：\n  - " + "\n  - ".join(problems))
    return theme


@lru_cache(maxsize=1)
def _read() -> Theme:
    path = paths.ASSETS_DIR / "theme.json"
    if not path.is_file():
        raise ThemeError(f"主题文件缺失：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ThemeError(f"主题文件不是合法 JSON：{path}（{exc}）") from exc
    missing = [key for key in _REQUIRED_SECTIONS if not isinstance(data.get(key), dict)]
    if missing:
        raise ThemeError(f"主题缺少段落：{', '.join(missing)}")
    return Theme(data)


def validate(theme: Theme) -> list[str]:
    """返回缺陷清单；空列表代表可用。控件层只消费通过校验的主题。"""
    problems: list[str] = []
    for rule in theme.raw.get("contrast", []):
        try:
            fg = theme.color(rule["fg"])
            bg = theme.color(rule["bg"])
        except (KeyError, ThemeError) as exc:
            problems.append(f"对比度规则取不到色：{rule}（{exc}）")
            continue
        ratio = contrast_ratio(fg, bg)
        if ratio < float(rule["min"]):
            problems.append(
                f"{rule['fg']} on {rule['bg']} 对比度 {ratio:.2f} < 要求 {rule['min']}"
            )
    for name, value in theme.raw["color"].items():
        try:
            parse_hex(value)
        except ThemeError as exc:
            problems.append(f"{name}: {exc}")
    return problems
