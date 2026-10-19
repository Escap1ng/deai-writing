"""checkup — 本地三关体检：输入一段文本，输出命中清单与可渲染的报告文本。

放在 core 层是因为它必须能在无界面环境跑（测试、--smoke、以后的批处理都靠它）。
数字全部来自 bridge 调 code/ 的引擎，这里只做汇总与排版，不判定任何规则。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from deai_app.bridge import engines

CJK_MIN_RATIO = 0.12
RENDER_LIMIT = 30

_RISK_ORDER = ("低", "中", "高", "极高")


def detect_lang(text: str) -> str:
    """按 CJK 占比粗判中英：只影响提示信息语言，不改检查规则集。"""
    sample = text[:4000]
    if not sample.strip():
        return "zh"
    cjk = sum(1 for ch in sample if "\u3400" <= ch <= "\u9fff")
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    if latin and cjk / max(1, cjk + latin) < CJK_MIN_RATIO:
        return "en"
    return "zh"


def visible_chars(text: str) -> int:
    """界面上"字数"的唯一口径：不计换行。页脚与报告都走它，两处数字必须相同。"""
    return len(text.replace("\r", "").replace("\n", ""))


@dataclass
class GateReport:
    lang: str
    chars: int
    phrasing: list[dict] = field(default_factory=list)
    style: list[dict] = field(default_factory=list)
    style_risk: str = "低"
    invisible: Counter = field(default_factory=Counter)
    rules: int = 0

    @property
    def invisible_total(self) -> int:
        return sum(self.invisible.values())

    @property
    def clean(self) -> bool:
        return not self.phrasing and not self.style and self.invisible_total == 0

    @property
    def blocked(self) -> bool:
        """SKILL 门禁：结构级风险到高/极高不得交付。"""
        return self.style_risk in _RISK_ORDER[2:]

    def codepoints(self) -> str:
        return "、".join(f"U+{cp:04X}×{n}" for cp, n in sorted(self.invisible.items())) or "无"


def run(text: str, lang: str = "自动") -> GateReport:
    resolved = detect_lang(text) if lang == "自动" else lang
    phrasing = engines.phrasing_scan(text, resolved)
    style = engines.style_scan(text, resolved)
    return GateReport(
        lang=resolved,
        chars=visible_chars(text),
        phrasing=phrasing["hits"],
        rules=phrasing["rules"],
        style=style["hits"],
        style_risk=style["risk"],
        invisible=engines.invisible_scan(text),
    )


def _line_of(text: str, line: int) -> str:
    lines = text.splitlines()
    return lines[line - 1].strip()[:60] if 0 < line <= len(lines) else ""


def render(report: GateReport, source: str, limit: int = RENDER_LIMIT) -> str:
    """把人可读报告排成一段文本；UI 与 --checkup 共用这一份排版。"""
    verdict = "阻断" if report.blocked else ("通过" if report.clean else "待改")
    head = (
        f"降 AI 三关体检 · 提示语言 {report.lang} · 输入 {report.chars} 字\n"
        f"词表 {len(report.phrasing)} 处 · 结构 {report.style_risk}（{len(report.style)} 处） · "
        f"字符 {report.invisible_total} 个 · 门禁：{verdict}"
    )
    out = [head]

    if report.phrasing:
        out.append("\n【词表级】")
        for index, hit in enumerate(report.phrasing[:limit], 1):
            out.append(f"{index}. 第 {hit['line']} 行第 {hit['col']} 列 [{hit['rule']}] {hit['label']}"
                       f"　命中：{hit['text']}")
            if hit.get("fix"):
                out.append(f"   改法：{hit['fix']}")
        if len(report.phrasing) > limit:
            out.append(f"……另有 {len(report.phrasing) - limit} 处")
    else:
        out.append("\n【词表级】未命中")

    if report.style:
        out.append("\n【结构级】")
        for index, hit in enumerate(report.style[:limit], 1):
            out.append(f"{index}. 第 {hit['line']} 行 [{hit['metric']}] 风险 {hit['severity']}"
                       f"　原文：{_line_of(source, hit['line'])}")
            if hit.get("fix"):
                out.append(f"   改法：{hit['fix']}")
        if len(report.style) > limit:
            out.append(f"……另有 {len(report.style) - limit} 处")
    else:
        out.append("\n【结构级】未命中")

    out.append("\n【字符级】")
    out.append(f"检出 {report.invisible_total} 个不可见字符：{report.codepoints()}"
               if report.invisible_total else "未发现零宽、bidi、tag、私用区等不可见字符")
    return "\n".join(out)
