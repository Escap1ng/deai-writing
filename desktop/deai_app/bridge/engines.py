"""bridge — 只读调用 code/ 三关检查器，输入输出都是内存里的字符串与列表。

三关的实现只有一份：本模块用 importlib 按文件路径载入 code/ 里的脚本，
再调它们自己的公开函数（load_blacklist / scan_file / apply_frequency_limit /
check_file / risk_level / scan / clean_str）。这里不复制任何匹配逻辑、不写临时文件，
所以 App 报的命中数与用户手跑 python3 code/check_*.py 的结果由构造保证一致，
tests/test_bridge_parity.py 再把这条一致性钉住。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path

from deai_app import paths

__all__ = [
    "EngineError",
    "phrasing_scan",
    "phrasing_rules",
    "style_scan",
    "style_thresholds",
    "invisible_scan",
    "invisible_clean",
]

_MODULES: dict[str, types.ModuleType] = {}

CHECK_PHRASING = "check_phrasing"
CHECK_STYLE = "check_style"
STRIP_INVISIBLE = "strip_invisible"

_UTF8_SIG = "utf-8-sig"


class EngineError(RuntimeError):
    """引擎缺失、词表损坏或调用失败；message 必须能直接给用户看。"""


class _TextSource:
    """鸭子类型的文件对象：两个检查器取文本时只调用 read_text(encoding=...)。"""

    def __init__(self, text: str, name: str = "<内存文本>") -> None:
        self._text = text
        self.name = name

    def read_text(self, encoding: str = "utf-8") -> str:
        # 真文件按 utf-8-sig 读字节会吃掉一个前置 BOM，这里保持一致
        if encoding.replace("_", "-").lower() == _UTF8_SIG and self._text.startswith("\ufeff"):
            return self._text[1:]
        return self._text


def _load(module_key: str) -> types.ModuleType:
    cached = _MODULES.get(module_key)
    if cached is not None:
        return cached
    source = paths.require_code_dir() / f"{module_key}.py"
    if not source.is_file():
        raise EngineError(f"引擎缺失：{source}")
    spec = importlib.util.spec_from_file_location(f"deai_engine_{module_key}", source)
    if spec is None or spec.loader is None:
        raise EngineError(f"引擎无法载入：{source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - 引擎自身的导入期错误要换成可读 message 再抛
        raise EngineError(f"引擎初始化失败：{source}（{exc}）") from exc
    _MODULES[module_key] = module
    return module


def _call(func, *args, **kwargs):
    """引擎在词表缺失时会 SystemExit(2)，在 App 里必须变成可捕获的错误。"""
    try:
        return func(*args, **kwargs)
    except SystemExit as exc:
        raise EngineError(f"引擎拒绝执行（退出码 {exc.code}）：请检查 code/ 是否完整") from exc


def phrasing_scan(text: str, lang: str = "zh") -> dict:
    """词表级：返回 {"rules": 条数, "hits": [命中]}；命中已按 max_per_document 频次上限过滤。"""
    engine = _load(CHECK_PHRASING)
    data = _call(engine.load_blacklist, lang)
    rules = data["rules"]
    raw_hits = engine.scan_file(_TextSource(text), rules)
    kept = engine.apply_frequency_limit(raw_hits, {rule["id"]: rule for rule in rules})
    return {"rules": len(rules), "hits": kept}


def phrasing_rules(lang: str = "zh") -> list[dict]:
    """词表规则摘要（id/label/why/fix/severity/频次上限），供提示词拼装使用。"""
    engine = _load(CHECK_PHRASING)
    rules = _call(engine.load_blacklist, lang)["rules"]
    return [
        {
            "id": rule["id"],
            "label": rule["_label"],
            "why": rule["_why"],
            "fix": rule["_fix"],
            "severity": rule["severity"],
            "max_per_document": rule.get("max_per_document", 0),
            "patterns": list(rule.get("patterns", [])),
        }
        for rule in rules
    ]


def style_scan(text: str, lang: str = "zh") -> dict:
    """结构级：返回 {"hits": [命中], "chars": 字数, "risk": 低/中/高/极高}。"""
    engine = _load(CHECK_STYLE)
    hits, chars = _call(engine.check_file, _TextSource(text), lang)
    severity = {metric["id"]: metric["severity"] for metric in engine.METRICS}
    for hit in hits:
        # check_file 不写 severity，CLI 在 main() 里补；闸门评级要用同一口径
        hit.setdefault("severity", severity.get(hit["metric"], "low"))
    return {"hits": hits, "chars": chars, "risk": engine.risk_level(hits, chars)}


def style_thresholds() -> dict:
    """六项指标的阈值与说明（单一来源仍是 code/check_style.py 的 METRICS 与常量）。"""
    engine = _load(CHECK_STYLE)
    return {
        "thresholds": {
            "long_sentence": engine.LONG_SENTENCE,
            "min_paragraph": engine.MIN_PARAGRAPH,
            "min_rhythm_sentences": engine.MIN_RHYTHM_SENTENCES,
            "min_rhythm_paragraphs": engine.MIN_RHYTHM_PARAGRAPHS,
            "rhythm_band": list(engine.RHYTHM_BAND),
            "para_diff_min": engine.PARA_DIFF_MIN,
            "max_decimals": engine.MAX_DECIMALS,
        },
        "metrics": [dict(metric) for metric in engine.METRICS],
    }


def invisible_scan(text: str) -> Counter:
    """字符级：只检测，返回不可见码位的计数。"""
    return _load(STRIP_INVISIBLE).scan(text)


def invisible_clean(text: str) -> tuple[str, Counter]:
    """字符级：清理并返回 (干净文本, 被剥离计数)。"""
    return _load(STRIP_INVISIBLE).clean_str(text)


def engine_files() -> list[Path]:
    """本桥接层依赖的引擎文件，供自检与打包清单核对。"""
    root = paths.require_code_dir()
    return [root / f"{key}.py" for key in (CHECK_PHRASING, CHECK_STYLE, STRIP_INVISIBLE)] + [
        root / "phrasing-blacklist.json"
    ]
