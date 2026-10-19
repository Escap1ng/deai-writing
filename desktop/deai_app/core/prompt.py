"""prompt — 把三关规则拼成改写指令，规则与阈值只从 bridge 取。

提示词里不复制正则，也不抄第二份规则表：词表用 phrasing_rules()，
结构用 style_thresholds()，引擎改了措辞，这里跟着变。
"""
from __future__ import annotations

from deai_app.bridge import engines
from deai_app.core import checkup

PRESETS = ("论文", "公文", "通用")
INTENSITIES = ("轻", "中", "重")
MAX_FEEDBACK_HITS = 40

_PRESET_TEXT = {
    "论文": "保持论文的论证结构与术语口径；方法、数据、引用和图表编号不得改动，只改表达。",
    "公文": "保持公文的事项、称谓与分条结构；语气克制明确，不增加承诺性表述。",
    "通用": "保持原文的体裁、信息密度与叙述顺序，不增删事实。",
}

_INTENSITY_TEXT = {
    "轻": "只改最明显的模板腔与空泛表达，尽量保留原句结构。",
    "中": "在保住事实与结构的前提下，重写套话、空泛衔接和单调句式。",
    "重": "允许较大幅度重写句子与段落衔接；事实、数字、引用、术语和章节结构仍不得改变。",
}

_HARD_RULES = (
    "只输出改写后的正文，不要前言、解释、对照表或 Markdown 代码围栏。",
    "保持原文语言；原文是英文就只输出英文。",
    "不得新增或编造事实、数字、文献、案例；不得删除限定条件与不确定性说明。",
    "保留 Markdown、LaTeX 命令、公式、引用标记与图表编号的原有写法。",
    "保留个人判断与局限说明，不要改成空泛升华，也不要改成口语。",
)


def _pick(metric: dict, key: str, lang: str) -> str:
    if lang == "en":
        return metric.get(f"{key}_en") or metric.get(key, "")
    return metric.get(key, "")


def rule_digest(lang: str = "zh") -> str:
    """词表与结构两份清单，按严重度排序；只写规则名与改法。"""
    lines = ["【词表级】"]
    order = {"high": 0, "medium": 1, "low": 2}
    rules = sorted(engines.phrasing_rules(lang), key=lambda rule: order.get(rule["severity"], 3))
    for rule in rules:
        lines.append(f"- {rule['label']}：{rule['fix']}")

    data = engines.style_thresholds()
    thresholds = data["thresholds"]
    hints = {
        "long-passive": f"超过 {thresholds['long_sentence']} 字",
        "repeated-opening": "连续 4 句以上同形开头",
        "transition-density": "每段超过 2 个",
        "sentence-rhythm": (f"长句占比 {int(thresholds['rhythm_band'][0] * 100)}%-"
                            f"{int(thresholds['rhythm_band'][1] * 100)}%"),
        "paragraph-rhythm": f"相邻段落字数差异低于 {int(thresholds['para_diff_min'] * 100)}%",
        "decimal-precision": f"保留 2-{thresholds['max_decimals']} 位小数",
    }
    lines.append("")
    lines.append("【结构级】")
    for metric in data["metrics"]:
        label = _pick(metric, "label", lang)
        fix = _pick(metric, "fix", lang)
        scope = hints.get(metric["id"], "")
        lines.append(f"- {label}（{scope}）：{fix}")
    return "\n".join(lines)


def _feedback(gate: checkup.GateReport, lang: str = "zh", limit: int = MAX_FEEDBACK_HITS) -> str:
    if gate is None or gate.clean:
        return ""
    labels = {metric["id"]: _pick(metric, "label", lang)
              for metric in engines.style_thresholds()["metrics"]}
    lines = ["", "上一版复检仍有以下命中，只改这些地方，其余文字保持原样："]
    budget = limit
    for hit in gate.phrasing[:budget]:
        lines.append(f"- 词表·{hit['label']}：命中「{hit.get('text', '')}」；改法：{hit.get('fix', '')}")
        budget -= 1
    if budget > 0:
        for hit in gate.style[:budget]:
            where = f"第 {hit['line']} 行" if hit.get("line") else "全文"
            label = labels.get(hit.get("metric", ""), hit.get("metric", ""))
            lines.append(f"- 结构·{label}（{where}）；改法：{hit.get('fix', '')}")
            budget -= 1
    remaining = len(gate.phrasing) + len(gate.style) - (limit - budget)
    if remaining > 0:
        lines.append(f"- 另有 {remaining} 处同类命中，按上面的改法一并处理。")
    return "\n".join(lines)


def system_prompt(lang: str = "zh", preset: str = "论文", intensity: str = "中") -> str:
    preset_text = _PRESET_TEXT.get(preset, _PRESET_TEXT["通用"])
    intensity_text = _INTENSITY_TEXT.get(intensity, _INTENSITY_TEXT["中"])
    hard = "\n".join(f"{index}. {line}" for index, line in enumerate(_HARD_RULES, 1))
    return (
        "你是中文写作编辑，负责去掉文稿里的 AI 腔，同时保住作者原意。\n"
        f"{intensity_text}\n{preset_text}\n\n"
        "硬性要求：\n"
        f"{hard}\n\n"
        "以下规则全部来自本项目的三关检查器，改写时逐条避开：\n"
        f"{rule_digest(lang)}"
    )


def messages(text: str, lang: str = "zh", preset: str = "论文", intensity: str = "中",
             gate: checkup.GateReport | None = None) -> list[dict]:
    """一次请求的消息体；gate 非空时表示这是复检后的精修轮。"""
    user = "改写下面的文稿。\n\n" + text
    feedback = _feedback(gate, lang) if gate is not None else ""
    return [
        {"role": "system", "content": system_prompt(lang, preset, intensity)},
        {"role": "user", "content": user + feedback},
    ]
