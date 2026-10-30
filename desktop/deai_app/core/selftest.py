"""selftest — exe 与源码共用的无界面自检，不依赖窗口与 stdout。

windowed 构建里 `sys.stdout` 是 None，`print` 会静默丢弃；
`--smoke --out FILE` 把结论写进文件，才能证明 bundle 里的引擎与主题真的可读。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from deai_app import VERSION, paths
from deai_app.bridge import engines
from deai_app.core import config

SLOP_PHRASING = ("综上所述，随着人工智能技术的快速发展，本文对数据治理问题进行了深入研究。"
                 "研究表明，这一工作至关重要，有效提升了治理水平。")
SLOP_STYLE = (
    "本研究的基线模型在 120 份卷面上给出误差率 3.14159265 的实测记录。"
    "本研究的对照组在同一批样本上复跑了三轮，把漏检数从 18 个压到 7 个。"
    "本研究的复核环节由两名标注员独立完成，分歧条目按事先约定的一致规则处理。\n\n"
    "本研究的误差分布集中在中等长度样本，短句与长句两端都保持较低水平。\n"
)
CLEAN = "误差从 4.8% 降到 1.9%，来自 3 个班级共 120 份卷面复核。\n"
INVISIBLE = "方\u200b法"


@dataclass(frozen=True)
class Item:
    name: str
    ok: bool
    detail: str


def _check(name: str, probe) -> Item:
    try:
        ok, detail = probe()
    except Exception as exc:  # noqa: BLE001 - 自检要把异常变成一条可读结论
        return Item(name, False, f"{type(exc).__name__}: {exc}")
    return Item(name, ok, detail)


def _phrasing() -> tuple[bool, str]:
    data = engines.phrasing_scan(SLOP_PHRASING)
    ok = data["rules"] >= 20 and len(data["hits"]) > 0
    return ok, f"{data['rules']} 条规则 · 反例命中 {len(data['hits'])} 处"


def _style() -> tuple[bool, str]:
    slop = engines.style_scan(SLOP_STYLE)
    clean = engines.style_scan(CLEAN)
    ok = len(slop["hits"]) > 0 and not clean["hits"] and clean["risk"] == "低"
    return ok, f"反例 {len(slop['hits'])} 处（风险 {slop['risk']}） · 正例 0 处"


def _invisible() -> tuple[bool, str]:
    found = sum(engines.invisible_scan(INVISIBLE).values())
    cleaned, removed = engines.invisible_clean(INVISIBLE)
    ok = found == 1 and cleaned == "方法" and sum(removed.values()) == 1
    return ok, f"检出 {found} 个 · 清理后 {sum(engines.invisible_scan(cleaned).values())} 个"


def _theme() -> tuple[bool, str]:
    path = paths.ASSETS_DIR / "theme.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = [data.get(name) for name in ("color", "font", "shell")]
    sizes = (data.get("font") or {}).get("size") or {}
    ok = all(isinstance(section, dict) and section for section in sections) and bool(sizes)
    return ok, f"{len(data.get('color') or {})} 色值 · {len(sizes)} 字号 · 3 个必需段"


def _example_config() -> tuple[bool, str]:
    data = json.loads(config.example_path().read_text(encoding="utf-8"))
    providers = data.get("providers") if isinstance(data, dict) else None
    ok = isinstance(providers, list) and len(providers) > 0
    return ok, f"{len(providers or [])} 个示例供应商"


def run() -> list[Item]:
    return [
        _check("词表级", _phrasing),
        _check("结构级", _style),
        _check("字符级", _invisible),
        _check("主题", _theme),
        _check("示例配置", _example_config),
    ]


def render(items: list[Item]) -> str:
    mode = "frozen" if paths.is_frozen() else "源码"
    lines = [f"deai {VERSION} · {mode}"]
    lines += [f"[{'PASS' if item.ok else 'FAIL'}] {item.name} · {item.detail}" for item in items]
    passed = sum(1 for item in items if item.ok)
    verdict = "全部通过" if passed == len(items) else "有失败项"
    lines.append(f"结论：{verdict}（{passed}/{len(items)}）")
    return "\n".join(lines)


def ok(items: list[Item]) -> bool:
    return all(item.ok for item in items)
