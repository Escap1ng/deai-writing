"""report — 体检报告的分层渲染。

先产出 (kind, text) 块序列（纯数据，测试直接断言它），再包成 HTML 交给只读栏。
分层规则：组标题 > 命中条目（规则名与位置用次级色，命中原文用正文色）> 改法（缩进、弱化色）。
"""
from __future__ import annotations

import html

from deai_app.core.checkup import GateReport
from deai_app.ui.theme import Theme, load_theme

LIMIT = 30
Block = tuple[str, str]

_KINDS = ("head", "sub", "group", "item", "fix", "more", "note")


def _line_of(source: str, line: int) -> str:
    lines = source.splitlines()
    return lines[line - 1].strip()[:48] if 0 < line <= len(lines) else ""


def blocks(report: GateReport, source: str, limit: int = LIMIT) -> list[Block]:
    verdict = "阻断" if report.blocked else ("通过" if report.clean else "待改")
    out: list[Block] = [
        ("head", "降 AI 三关体检"),
        ("sub", f"提示语言 {report.lang} · 输入 {report.chars} 字 · 门禁：{verdict}"),
        ("sub", f"词表 {len(report.phrasing)} 处 · 结构 {report.style_risk}（{len(report.style)} 处） · "
                f"字符 {report.invisible_total} 个"),
    ]
    out.append(("group", "词表级"))
    if not report.phrasing:
        out.append(("note", "未命中"))
    for index, hit in enumerate(report.phrasing[:limit], 1):
        out.append(("item", f"{index}. 第 {hit['line']} 行第 {hit['col']} 列 [{hit['rule']}] "
                            f"{hit['label']}　命中：{hit['text']}"))
        if hit.get("fix"):
            out.append(("fix", hit["fix"]))
    if len(report.phrasing) > limit:
        out.append(("more", f"另有 {len(report.phrasing) - limit} 处未列出"))

    out.append(("group", "结构级"))
    if not report.style:
        out.append(("note", "未命中"))
    for index, hit in enumerate(report.style[:limit], 1):
        out.append(("item", f"{index}. 第 {hit['line']} 行 [{hit['metric']}] 风险 {hit['severity']}"
                            f"　原文：{_line_of(source, hit['line'])}"))
        if hit.get("fix"):
            out.append(("fix", hit["fix"]))
    if len(report.style) > limit:
        out.append(("more", f"另有 {len(report.style) - limit} 处未列出"))

    out.append(("group", "字符级"))
    out.append(("note" if not report.invisible_total else "item",
                "未发现零宽、bidi、tag、私用区等不可见字符" if not report.invisible_total
                else f"检出 {report.invisible_total} 个：{report.codepoints()}"))
    return out


def _group_hits(report: GateReport) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for hit in report.phrasing:
        grouped.setdefault(int(hit["line"]), []).append(hit)
    for hits in grouped.values():
        hits.sort(key=lambda hit: (int(hit["col"]), -len(hit.get("text", ""))))
    return grouped


def _annotate_line(line: str, hits: list[dict], theme: Theme) -> str:
    if not hits:
        return html.escape(line)
    mark = theme.color("mark_bg")
    rule = theme.color("gate_warn")
    parts: list[str] = []
    cursor = 0
    for hit in hits:
        wanted = hit.get("text", "")
        if not wanted:
            continue
        start = max(0, int(hit["col"]) - 1)
        if line[start:start + len(wanted)] != wanted:
            found = line.find(wanted, start)
            if found < 0:
                found = line.find(wanted)
            if found < 0:
                continue
            start = found
        end = start + len(wanted)
        if start < cursor:
            continue
        tip = html.escape(f"{hit['label']}：{hit.get('fix', '')}", quote=True)
        parts.append(html.escape(line[cursor:start]))
        parts.append(
            f'<span style="background-color:{mark};border-bottom:2px solid {rule};" '
            f'title="{tip}">{html.escape(line[start:end])}</span>'
        )
        cursor = end
    parts.append(html.escape(line[cursor:]))
    return "".join(parts)


def render_annotated_html(report: GateReport, source: str,
                          theme: Theme | None = None) -> str:
    """整段视图：原文按段落排版，词表命中就地着色，不改动一个可见字符。"""
    theme = theme or load_theme()
    grouped = _group_hits(report)
    paragraphs: list[str] = []
    block: list[str] = []
    for lineno, line in enumerate(source.splitlines(), 1):
        if line.strip():
            block.append(_annotate_line(line, grouped.get(lineno, []), theme))
        elif block:
            paragraphs.append("<br>".join(block))
            block = []
    if block:
        paragraphs.append("<br>".join(block))
    body = "".join(f'<p style="margin:0 0 10px 0;">{text}</p>' for text in paragraphs)
    return (
        f"<div style=\"font-family:'Microsoft YaHei UI';font-size:{theme.size('body')}pt;"
        f"color:{theme.color('text')};line-height:150%;\">{body}</div>"
    )


def render_html(report: GateReport, source: str, theme: Theme | None = None,
                limit: int = LIMIT) -> str:
    theme = theme or load_theme()
    c = theme.color
    body = theme.size("body")
    styles = {
        "head": f"font-size:{theme.size('emphasis')}pt;font-weight:700;color:{c('text')};margin-top:2px",
        "sub": f"font-size:{theme.size('meta')}pt;color:{c('text_secondary')};margin-bottom:6px",
        "group": f"font-size:{theme.size('meta')}pt;font-weight:700;color:{c('text_muted')};"
                 f"letter-spacing:1px;margin-top:14px;border-bottom:1px solid {c('divider')};padding-bottom:2px",
        "item": f"font-size:{body}pt;color:{c('text')};margin-top:6px;line-height:150%",
        "fix": f"font-size:{theme.size('meta')}pt;color:{c('text_muted')};margin-left:22px;line-height:145%",
        "more": f"font-size:{theme.size('meta')}pt;color:{c('text_secondary')};margin-left:22px",
        "note": f"font-size:{body}pt;color:{c('text_secondary')}",
    }
    parts = [f"<div style=\"font-family:'Microsoft YaHei UI';line-height:150%\">"]
    for kind, text in blocks(report, source, limit):
        prefix = "改法：" if kind == "fix" else ("· " if kind == "more" else "")
        parts.append(f"<p style=\"{styles[kind]}\">{prefix}{html.escape(text)}</p>")
    parts.append("</div>")
    return "".join(parts)
