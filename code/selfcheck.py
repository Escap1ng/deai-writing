#!/usr/bin/env python3
"""selfcheck.py — 回归自检：把人工对照「期望结果」变成一条可执行命令。

对 `examples/` 与 `docs/` 的每个样本断言检查器的期望退出码（正例 0、反例 1），
逐项打印期望值与实际值；另加一条字符级清理器的「检出 → 清理 → 复检」闭环断言，
临时文件写在系统临时目录，不污染技能目录。全部断言通过退出 0，任一失败退出 1。

用法：
  python code/selfcheck.py                        # 逐项打印期望/实际退出码
  python code/selfcheck.py --quiet                # 只打印失败项与最终汇总
  python code/selfcheck.py --json                 # 机器可读 JSON（stdout 只输出 JSON）
  python code/selfcheck.py --skill-root <技能根>   # 对另一份副本跑同一套断言

退出码：0=全部断言通过；1=有断言失败；2=用法或环境错误（检查脚本或样例缺失）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT = 120  # 单个子进程超时（秒），超时算该断言失败
SNIPPET_LIMIT = 400  # 失败原因里子进程输出的截断长度

CHECKERS = {
    "check_phrasing": "code/check_phrasing.py",
    "check_style": "code/check_style.py",
    "strip_invisible": "code/strip_invisible.py",
}

#: 断言清单：(断言名称, 样本文件（相对技能根）, 检查器, 期望退出码)
ASSERTIONS: list[tuple[str, str, str, int]] = [
    ("中文正例·词表级", "examples/clean-sample.md", "check_phrasing", 0),
    ("中文正例·结构级", "examples/clean-sample.md", "check_style", 0),
    ("中文正例(.tex)·词表级", "examples/clean-sample.tex", "check_phrasing", 0),
    ("中文正例(.tex)·结构级", "examples/clean-sample.tex", "check_style", 0),
    ("英文正例·词表级", "examples/clean-sample-en.md", "check_phrasing", 0),
    ("英文正例·结构级", "examples/clean-sample-en.md", "check_style", 0),
    ("中文反例·词表级", "examples/slop-sample.md", "check_phrasing", 1),
    ("中文结构反例·词表级应为干净", "examples/style-slop-sample.md", "check_phrasing", 0),
    ("中文结构反例·结构级", "examples/style-slop-sample.md", "check_style", 1),
    ("英文反例·词表级", "examples/slop-sample-en.md", "check_phrasing", 1),
    ("规范文档·词表级自检", "docs/deai-rules.md", "check_phrasing", 0),
]

#: 第 12 条：字符级清理器三步闭环（检出可见 → 清理成功 → 复检干净）
INVISIBLE_NAME = "字符级清理器·检出→清理→复检"
INVISIBLE_LABEL = "<tmp>/invisible-sample.txt"
INVISIBLE_DIRTY = "甲\u200b乙\u200d丙\n"


# ---------- 子进程调用 ----------


def run_check(script: Path, args: list[str], cwd: Path) -> tuple[int | None, str, str]:
    """运行检查脚本，返回 (退出码, stdout, stderr)；超时返回 (None, 部分输出)。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(script), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        return None, _as_text(exc.stdout), _as_text(exc.stderr)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _as_text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _snippet(stdout: str, stderr: str) -> str:
    """子进程输出摘要：先 stderr 后 stdout，截断到固定长度，压成单行。"""
    merged = " | ".join(part.strip() for part in (stderr, stdout) if part.strip())
    merged = " ".join(merged.split())
    if len(merged) > SNIPPET_LIMIT:
        merged = merged[:SNIPPET_LIMIT] + "…"
    return merged


# ---------- 断言执行 ----------


def check_fixture(script: Path, rel_file: str, expected: int, cwd: Path) -> dict:
    code, out, err = run_check(script, [str(cwd / rel_file)], cwd)
    entry = {"expected": expected, "actual": code}
    if code is None:
        entry["ok"] = False
        entry["reason"] = f"超时：超过 {TIMEOUT} 秒未结束"
    elif code == expected:
        entry["ok"] = True
    else:
        entry["ok"] = False
        detail = _snippet(out, err) or "（子进程无输出）"
        entry["reason"] = f"退出码不符。{detail}"
    return entry


def check_invisible(strip: Path, cwd: Path) -> dict:
    """检出 → 清理 → 复检 三步闭环，任一步不符即失败。"""
    entry: dict = {"expected": 0, "actual": None, "ok": False}
    tmpdir = Path(tempfile.mkdtemp(prefix="deai-selfcheck-"))
    try:
        sample = tmpdir / "invisible-sample.txt"
        sample.write_text(INVISIBLE_DIRTY, encoding="utf-8")
        steps = (
            ("检出", [str(sample)], 1),
            ("清理", ["--clean", "--no-backup", str(sample)], 0),
            ("复检", [str(sample)], 0),
        )
        actual: list[int | None] = []
        for label, args, expected in steps:
            code, out, err = run_check(strip, args, cwd)
            actual.append(code)
            if code is None:
                entry["actual"] = actual
                entry["reason"] = f"{label}步骤超时：超过 {TIMEOUT} 秒未结束"
                return entry
            if code != expected:
                detail = _snippet(out, err) or "（子进程无输出）"
                entry["actual"] = actual
                entry["reason"] = (
                    f"{label}步骤期望退出码 {expected}，实际 {code}。{detail}")
                return entry
        entry["actual"] = actual
        entry["ok"] = True
        return entry
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------- 环境校验 ----------


def validate(skill_root: Path) -> list[str]:
    """返回缺失路径列表（空列表表示环境齐备）。"""
    wanted = list(CHECKERS.values()) + [rel for _, rel, _, _ in ASSERTIONS]
    seen: list[str] = []
    for rel in wanted:
        if rel not in seen and not (skill_root / rel).is_file():
            seen.append(rel)
    return seen


# ---------- 输出 ----------


def _width(text: str) -> int:
    """显示宽度：CJK 与全角字符按 2 列计，用于列对齐。"""
    total = 0
    for ch in text:
        cp = ord(ch)
        wide = (
            0x1100 <= cp <= 0x115F
            or 0x2E80 <= cp <= 0xA4CF
            or 0xAC00 <= cp <= 0xD7A3
            or 0xF900 <= cp <= 0xFAFF
            or 0xFE30 <= cp <= 0xFE6F
            or 0xFF00 <= cp <= 0xFF60
            or 0xFFE0 <= cp <= 0xFFE6
            or cp >= 0x20000
        )
        total += 2 if wide else 1
    return total


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _fmt_actual(actual: int | list[int | None] | None) -> str:
    if isinstance(actual, list):
        return "→".join("超时" if code is None else str(code) for code in actual)
    if actual is None:
        return "超时"
    return str(actual)


def report_text(items: list[dict], quiet: bool) -> None:
    for item in items:
        if quiet and item["ok"]:
            continue
        tag = "[PASS]" if item["ok"] else "[FAIL]"
        line = (
            f"{tag} {_pad(item['name'], 26)} {_pad(item['file'], 30)} "
            f"期望 {item['expected']}  实际 {_fmt_actual(item['actual'])}"
        )
        print(line)
        if not item["ok"]:
            print(f"       原因：{item.get('reason', '')}")

    total = len(items)
    failed = [item for item in items if not item["ok"]]
    if failed:
        print(f"{total} 项断言：通过 {total - len(failed)}，失败 {len(failed)}")
        print("失败项对应文件：")
        for item in failed:
            print(f"  - {item['file']}（{item['name']}）")
    else:
        print(f"{total} 项断言：通过 {total}，失败 0")


def report_json(items: list[dict]) -> None:
    failed = sum(1 for item in items if not item["ok"])
    payload = {
        "total": len(items),
        "failed": failed,
        "ok": len(items) - failed,
        "items": items,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ---------- CLI ----------


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skill-root", default=None,
                    help="技能根目录；缺省取脚本所在目录的上一级")
    ap.add_argument("--quiet", action="store_true", help="只打印失败项与最终汇总")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args()

    default_root = Path(__file__).resolve().parent.parent
    skill_root = Path(args.skill_root).expanduser() if args.skill_root else default_root
    skill_root = skill_root.resolve()

    if not skill_root.is_dir():
        print(f"技能根目录不存在：{skill_root}", file=sys.stderr)
        return 2
    missing = validate(skill_root)
    if missing:
        print(f"环境错误：技能根目录 {skill_root} 下缺失以下路径", file=sys.stderr)
        for rel in missing:
            print(f"  - {skill_root / rel}", file=sys.stderr)
        return 2

    items: list[dict] = []
    for name, rel_file, checker, expected in ASSERTIONS:
        script = skill_root / CHECKERS[checker]
        result = check_fixture(script, rel_file, expected, skill_root)
        items.append({"name": name, "file": rel_file, "checker": checker, **result})

    invisible = check_invisible(skill_root / CHECKERS["strip_invisible"], skill_root)
    items.append({
        "name": INVISIBLE_NAME,
        "file": INVISIBLE_LABEL,
        "checker": "strip_invisible",
        **invisible,
    })

    if args.json:
        report_json(items)
    else:
        report_text(items, args.quiet)

    return 1 if any(not item["ok"] for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
