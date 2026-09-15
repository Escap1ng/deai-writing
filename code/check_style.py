#!/usr/bin/env python3
"""check_style.py — 去 AI 痕迹检查器（降 AI 技能的第二道表述级关卡：结构级）。

    python3 code/check_style.py draft/draft.tex            # 只报不改，命中即退出 1
    python3 code/check_style.py draft/*.tex --json         # 机器可读输出（含风险等级）
    python3 code/check_style.py --list-metrics             # 查看指标与阈值
    python3 code/check_style.py draft.md --lang en         # 英文提示、英文指标标签与改法

`check_phrasing.py` 管「词汇与句式」，本脚本管「句子、段落、数据」的结构节奏，覆盖：
  M1 long-passive        过长被动句（>25 字且含被动标记）——须拆分
  M2 repeated-opening    句式重复（连续 ≥4 句同一开头）——同类表述连续不超过 3 次
  M3 transition-density  过渡词密度（每段 >2 个）——每段过渡词不超过 2 个
  M4 sentence-rhythm     长短句比例（长句占比偏离 1:2）——仅在句数 ≥12 时统计
  M5 paragraph-rhythm    相邻段落字数差异（<20%）——仅在合格段落 ≥4 时统计
  M6 decimal-precision   结果小数位（>4 位）——统一保留 2-4 位

统计类指标（M4/M5）在样本过小时自动跳过，避免对短文本误报。列表项、表格行、编号分点
（「假设 X」「（1）」「①」「步骤 X」等）、清单块的换行续行与 README 类 HTML 区块均不参与统计——
清单类同形开头是格式要求，不是句式单调。退出码 0 通过 / 1 有命中 / 2 用法或环境错误。

指标条目除 `label`/`why`/`fix` 外另有 `label_en`/`why_en`/`fix_en`，由 `--lang` 选择，缺失时回退中文。
`--json` 的 `risk` 字段恒为中文本地化等级（低/中/高/极高），不随 `--lang` 变化，便于脚本稳定匹配。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEXT_SUFFIXES = {".tex", ".md", ".txt", ".bib", ".typ"}

LONG_SENTENCE = 25          # 长句阈值（字）
MIN_SENTENCE = 8            # 过短的分句不计入节奏统计
MIN_PARAGRAPH = 60          # 参与段落节奏统计的最小段长（字）
MIN_RHYTHM_SENTENCES = 12   # 长短句比例统计的最少句数
MIN_RHYTHM_PARAGRAPHS = 4   # 相邻段落节奏统计的最少合格段数
RHYTHM_BAND = (0.20, 0.50)  # 长句占比合理区间（目标 1:2）
PARA_DIFF_MIN = 0.20        # 相邻段落字数差异下限
MAX_DECIMALS = 4            # 结果小数位上限

TRANSITIONS = [
    "首先", "其次", "再次", "再者", "最后", "此外", "另外", "然而", "因此", "所以",
    "综上所述", "总而言之", "总的来说", "总体而言", "整体而言", "值得注意的是",
    "需要指出的是", "另一方面", "与此同时", "同时", "进而", "由此可见", "由此可知",
    "在此基础上", "更进一步", "更一般地", "与之相对", "简而言之", "不得不说",
]

PASSIVE_RE = re.compile(r"被|受到|为[^。；！？\n]{1,8}所")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z0-9]+")
DECIMAL_RE = re.compile(r"\d+\.(\d+)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*$")
MATH_INLINE_RE = re.compile(r"\$[^$]*\$")
TEX_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?")
SECTION_RE = re.compile(
    r"^\s*(?:#+|\\section\b|\\subsection\b|\\subsubsection\b|\\chapter\b|\\paragraph\b)")
# 列表项、编号分点与表格行按边界处理（本检查器面向论文、报告等长文的连续叙述段，清单类文本不参与统计）
# 编号分点必须排除：章节结构规范通常要求把假设分点列出、符号说明用三线表，
# 这类同形开头是格式要求而非句式单调。
LIST_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")
ENUM_RE = re.compile(
    r"^\s*(?:假设\s*[0-9０-９一二三四五六七八九十]+"
    r"|[（(]\s*[0-9０-９]+\s*[)）]"
    r"|\[\s*[0-9０-９]+\s*\]"          # 参考文献条目 [1] 属清单，不计入行文节奏
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"
    r"|步骤\s*[0-9０-９]+"
    r"|第\s*[0-9０-９一二三四五六七八九十]+\s*步"
    r"|(?:Step|step)\s*\d+)"
)


def is_list_like(line: str) -> bool:
    """是否为清单类行（列表项、表格行或编号分点）。"""
    return bool(LIST_RE.match(line) or ENUM_RE.match(line))


HTML_OPEN_RE = re.compile(r"^\s*<[a-zA-Z]")
HTML_CLOSE_RE = re.compile(r"</(?:p|div|h[1-6]|table|ul|ol|blockquote|details|summary)>\s*$")

MSG = {
    "zh": {
        "no_files": "没有可检查的文件",
        "skip": "跳过非文本文件：{path}",
        "hit": "{path}:{line} [{metric}] {text}",
        "detail": "    → {fix}",
        "summary": "检查 {files} 个文件，结构级命中 {hits} 处；AI 痕迹风险：{risk}",
        "summary_ok": "检查 {files} 个文件，未命中任何结构级痕迹（风险：低）",
        "risk": "低",
        "risk_names": {"低": "低", "中": "中", "高": "高", "极高": "极高"},
        "list_header": "结构级指标（{count} 项）",
        "severity_note": "（{severity}）",
        "fix_label": "改法：",
        "m3_text": "本段过渡词 {count} 个",
        "m4_text": "长句占比 {ratio}（目标约 33%）",
        "m5_text": "相邻段落字数差异 {diff}（下限 20%）",
    },
    "en": {
        "no_files": "No files to check",
        "skip": "Skipping non-text file: {path}",
        "hit": "{path}:{line} [{metric}] {text}",
        "detail": "    → {fix}",
        "summary": "Checked {files} file(s); {hits} structural hit(s); AI-slop risk: {risk}",
        "summary_ok": "Checked {files} file(s); no structural AI-slop patterns (risk: low)",
        "risk": "low",
        "risk_names": {"低": "low", "中": "medium", "高": "high", "极高": "very high"},
        "list_header": "Structural metrics ({count})",
        "severity_note": " ({severity})",
        "fix_label": "Fix: ",
        "m3_text": "{count} transition words in this paragraph",
        "m4_text": "long sentences {ratio} (target about 33%)",
        "m5_text": "adjacent paragraph length difference {diff} (floor 20%)",
    },
}

METRICS = [
    {"id": "long-passive", "severity": "high", "label": "过长被动句",
     "label_en": "Over-long passive sentence",
     "why": "超过 25 字的被动句读起来费劲，是机器行文的典型特征",
     "why_en": "A passive sentence past 25 characters is hard to read, and it is a typical machine-writing trait.",
     "fix": "拆成 2-3 个短句，主动语态优先（「本文以…为约束求解」替代「…被…所…」）",
     "fix_en": "Split it into 2-3 short sentences and favour the active voice."},
    {"id": "repeated-opening", "severity": "medium", "label": "句式重复",
     "label_en": "Repeated sentence opening",
     "why": "连续 4 句以上用同一开头，句式单调、缺乏长短变化",
     "why_en": "Four or more consecutive sentences starting the same way read as monotone and lose the long/short variation.",
     "fix": "改写开头，让相邻句子以不同成分起句（数据、结论、方法交替）",
     "fix_en": "Rewrite the openings so adjacent sentences start on different elements (data, conclusion, method)."},
    {"id": "transition-density", "severity": "medium", "label": "过渡词过密",
     "label_en": "Transition words too dense",
     "why": "同一段落过渡词超过 2 个，靠连接词堆砌行文",
     "why_en": "More than two transition words in one paragraph means it leans on connectors instead of content.",
     "fix": "每段过渡词不超过 2 个，删除后信息量不变的过渡词直接去掉",
     "fix_en": "Keep transitions to two per paragraph and delete any whose removal leaves the information unchanged."},
    {"id": "sentence-rhythm", "severity": "low", "label": "长短句比例失衡",
     "label_en": "Long/short sentence ratio off",
     "why": "长句占比偏离 1:2（长:短），读起来或喘不过气或过于零碎",
     "why_en": "The share of long sentences drifts away from one in three, so the text either runs on or reads as fragments.",
     "fix": "拆分过长句、合并过短句，使长句占比落在 20%-50%",
     "fix_en": "Split long sentences and merge short ones until long sentences fall between 20% and 50%."},
    {"id": "paragraph-rhythm", "severity": "low", "label": "段落节奏单一",
     "label_en": "Flat paragraph rhythm",
     "why": "相邻段落字数接近（差异 <20%），呈机械等长的模板感",
     "why_en": "Adjacent paragraphs sit within 20% of each other in length, which reads as mechanical, equal-sized blocks.",
     "fix": "按内容需要拉开段落长短，重点段落展开、次要内容从简",
     "fix_en": "Let length follow content: expand what matters and shorten what does not."},
    {"id": "decimal-precision", "severity": "low", "label": "小数位超标",
     "label_en": "Too many decimal places",
     "why": "结果小数位超过 4 位，未按数据类型统一保留 2-4 位",
     "why_en": "Results carry more than four decimal places instead of the two to four the data type justifies.",
     "fix": "统一保留 2-4 位小数，并在关键数据后补误差范围（如 ±X%）",
     "fix_en": "Keep 2-4 decimal places and add an error range such as ±X% after key numbers."},
]

METRICS_BY_ID = {metric["id"]: metric for metric in METRICS}


def localized(entry: dict, key: str, lang: str) -> str:
    """取条目的本地化字段：lang=en 时优先 <key>_en，缺失则回退中文 <key>。"""
    if lang == "en":
        value = entry.get(f"{key}_en")
        if value:
            return value
    return entry.get(key, "")


def token_len(text: str) -> int:
    """字数：CJK 逐字计 1，连续拉丁/数字串计 1，忽略空白与标点。"""
    return len(CJK_RE.findall(text)) + len(LATIN_RE.findall(text))


def strip_markup(line: str) -> str:
    """去掉 LaTeX 命令、行内公式、注释与行内代码，只留自然语言。"""
    s = TEX_COMMENT_RE.sub("", line)
    s = INLINE_CODE_RE.sub(" ", s)
    s = MATH_INLINE_RE.sub(" ", s)
    s = TEX_CMD_RE.sub(" ", s)
    return s.replace("{", " ").replace("}", " ")


def iter_paragraphs(lines: list[tuple[int, str]]):
    """按空行/标题/清单切段：标题、清单块（含其换行续行）与 HTML 区块不计入段落。"""
    buf: list[tuple[int, str]] = []
    in_list = False
    in_html = False
    for lineno, raw in lines:
        if not raw.strip():
            in_list = False
            if buf:
                yield buf
                buf = []
            continue
        if HTML_OPEN_RE.match(raw):
            in_html = True
        if in_html:
            if HTML_CLOSE_RE.search(raw):
                in_html = False
            continue
        if SECTION_RE.match(raw) or is_list_like(raw):
            in_list = True
            if buf:
                yield buf
                buf = []
            continue
        if in_list:
            # 清单块的换行续行（markdown 软换行 / 手工折行）同属清单，不按正文统计
            continue
        buf.append((lineno, raw))
    if buf:
        yield buf


def split_sentences(text: str, line_of: list[int]):
    """切句，产出 (sentence, start_line)；只认以句末标点结束的完整句，过滤碎片。"""
    out = []
    for match in re.finditer(r"[^。！？!?\n]+[。！？!?]", text):
        sent = match.group(0).strip()
        if token_len(sent) >= MIN_SENTENCE:
            out.append((sent, line_of[match.start()]))
    return out


def _paragraph_text(para: list[tuple[int, str]]):
    parts: list[str] = []
    line_of: list[int] = []
    for lineno, raw in para:
        stripped = strip_markup(raw)
        parts.append(stripped)
        line_of.extend([lineno] * len(stripped))
        parts.append(" ")
        line_of.append(lineno)
    return "".join(parts), line_of


def check_file(path: Path, lang: str) -> tuple[list[dict], int]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return [], 0

    def fix_of(metric_id: str) -> str:
        return localized(METRICS_BY_ID[metric_id], "fix", lang)

    in_fence = False
    lines: list[tuple[int, str]] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((lineno, line))

    hits: list[dict] = []
    total_chars = 0
    all_sentences: list[tuple[str, int]] = []
    para_info: list[tuple[int, int]] = []

    for para in iter_paragraphs(lines):
        text, line_of = _paragraph_text(para)
        sentences = split_sentences(text, line_of)
        all_sentences.extend(sentences)
        length = token_len(text)
        total_chars += length
        if length >= MIN_PARAGRAPH:
            para_info.append((para[0][0], length))

        # M1 过长被动句
        for sent, line in sentences:
            if token_len(sent) > LONG_SENTENCE and PASSIVE_RE.search(sent):
                hits.append({"metric": "long-passive", "line": line, "text": sent,
                             "fix": fix_of("long-passive")})
        # M2 句式重复（连续 ≥4 句同一开头）
        opens = ["".join(CJK_RE.findall(s.replace(" ", ""))[:2]) for s, _ in sentences]
        run = 1
        for i in range(1, len(sentences)):
            if opens[i] and opens[i] == opens[i - 1]:
                run += 1
                if run > 3:
                    hits.append({"metric": "repeated-opening", "line": sentences[i][1],
                                 "text": sentences[i][0], "fix": fix_of("repeated-opening")})
            else:
                run = 1
        # M3 过渡词密度（每段 >2）
        count = sum(text.count(word) for word in TRANSITIONS)
        if count > 2:
            hits.append({"metric": "transition-density", "line": para[0][0],
                         "text": MSG[lang]["m3_text"].format(count=count),
                         "fix": fix_of("transition-density")})

    # M6 小数位（在原始行上统计，含公式内的数值）
    for lineno, line in lines:
        if SECTION_RE.match(line) or is_list_like(line):
            continue
        for match in DECIMAL_RE.finditer(TEX_COMMENT_RE.sub("", line)):
            if len(match.group(1)) > MAX_DECIMALS:
                hits.append({"metric": "decimal-precision", "line": lineno,
                             "text": match.group(0), "fix": fix_of("decimal-precision")})

    # M4 长短句比例（句数足够时）
    if len(all_sentences) >= MIN_RHYTHM_SENTENCES:
        long_n = sum(1 for s, _ in all_sentences if token_len(s) > LONG_SENTENCE)
        ratio = long_n / len(all_sentences)
        if not RHYTHM_BAND[0] <= ratio <= RHYTHM_BAND[1]:
            hits.append({"metric": "sentence-rhythm", "line": all_sentences[0][1],
                         "text": MSG[lang]["m4_text"].format(ratio=f"{ratio:.0%}"),
                         "fix": fix_of("sentence-rhythm")})

    # M5 相邻段落字数差异（合格段落足够时）
    if len(para_info) >= MIN_RHYTHM_PARAGRAPHS:
        for (_, prev), (line, cur) in zip(para_info, para_info[1:]):
            diff = abs(prev - cur) / max(prev, cur)
            if diff < PARA_DIFF_MIN:
                hits.append({"metric": "paragraph-rhythm", "line": line,
                             "text": MSG[lang]["m5_text"].format(diff=f"{diff:.0%}"),
                             "fix": fix_of("paragraph-rhythm")})

    return hits, total_chars


def risk_level(hits: list[dict], chars: int) -> str:
    weights = {"high": 3.0, "medium": 1.0, "low": 0.5}
    score = sum(weights.get(h["severity"], 1.0) for h in hits)
    highs = sum(1 for h in hits if h["severity"] == "high")
    density = score / max(chars / 1000.0, 1.0)
    if density >= 6 or highs >= 8:
        return "极高"
    if density >= 3 or highs >= 4:
        return "高"
    if hits:
        return "中"
    return "低"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check sentence/paragraph structure for AI-slop patterns.")
    parser.add_argument("paths", nargs="*", help="Files to check (.tex/.md/.txt/.bib/.typ)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--list-metrics", action="store_true", help="Print metrics and thresholds")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="Message language")
    args = parser.parse_args()
    lang = args.lang

    if args.list_metrics:
        if args.json:
            print(json.dumps({"thresholds": {
                "long_sentence": LONG_SENTENCE, "min_sentence": MIN_SENTENCE,
                "min_paragraph": MIN_PARAGRAPH, "min_rhythm_sentences": MIN_RHYTHM_SENTENCES,
                "min_rhythm_paragraphs": MIN_RHYTHM_PARAGRAPHS, "rhythm_band": list(RHYTHM_BAND),
                "para_diff_min": PARA_DIFF_MIN, "max_decimals": MAX_DECIMALS},
                "metrics": [dict(m) for m in METRICS]},
                ensure_ascii=False, indent=2))
            return
        print(MSG[lang]["list_header"].format(count=len(METRICS)))
        for metric in METRICS:
            note = MSG[lang]["severity_note"].format(severity=metric["severity"])
            print(f"- {metric['id']:<20} {localized(metric, 'label', lang)}{note}")
            print(f"    {localized(metric, 'why', lang)}")
            print(f"    {MSG[lang]['fix_label']}{localized(metric, 'fix', lang)}")
        return

    if not args.paths:
        sys.stderr.write(MSG[lang]["no_files"] + "\n")
        raise SystemExit(2)

    targets: list[Path] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            sys.stderr.write(MSG[lang]["skip"].format(path=path) + "\n")
            continue
        targets.append(path)
    if not targets:
        sys.stderr.write(MSG[lang]["no_files"] + "\n")
        raise SystemExit(2)

    severity = {m["id"]: m["severity"] for m in METRICS}
    all_hits: list[dict] = []
    total_chars = 0
    for path in targets:
        hits, chars = check_file(path, lang)
        total_chars += chars
        for hit in hits:
            hit["path"] = str(path)
            hit["severity"] = severity.get(hit["metric"], "low")
            all_hits.append(hit)
    all_hits.sort(key=lambda item: (item["path"], item["line"]))

    risk = risk_level(all_hits, total_chars)
    if args.json:
        print(json.dumps({"files": len(targets), "chars": total_chars, "risk": risk,
                          "hits": all_hits}, ensure_ascii=False, indent=2))
    else:
        for hit in all_hits:
            print(MSG[lang]["hit"].format(path=hit["path"], line=hit["line"],
                                          metric=hit["metric"], text=hit["text"]))
            print(MSG[lang]["detail"].format(fix=hit["fix"]))
        template = "summary" if all_hits else "summary_ok"
        print(MSG[lang][template].format(files=len(targets), hits=len(all_hits),
                                         risk=MSG[lang]["risk_names"].get(risk, risk)))

    raise SystemExit(1 if all_hits else 0)


if __name__ == "__main__":
    main()
