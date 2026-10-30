"""deai_app 命令行入口。

    python3 -m deai_app                 # 开无边框主窗口
    python3 -m deai_app --sample F      # 开窗口并把 F 灌进输入栏（看版式撑不撑）
    python3 -m deai_app --checkup FILE  # 不开窗口，直接输出三关体检报告
    python3 -m deai_app --smoke         # 无界面自检引擎、词表、主题与示例配置
    python3 -m deai_app --version

windowed exe 没有 stdout；需要看输出时加 `--out FILE`（--smoke / --checkup 都支持）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deai_app import VERSION


def _emit(text: str, out: str | None = None) -> None:
    if out:
        Path(out).expanduser().write_text(text + "\n", encoding="utf-8")
    elif sys.stdout is not None:
        print(text)


def _checkup(paths: list[str], lang: str, out: str | None = None) -> int:
    from deai_app.core import checkup

    code = 0
    lines: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            lines.append(f"读不了 {path}：{exc}")
            code = 2
            continue
        report = checkup.run(text, lang)
        lines.append(checkup.render(report, text))
        code = code or (1 if not report.clean else 0)
    _emit("\n".join(lines), out)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deai_app", description="降 AI 写作工作台")
    parser.add_argument("--version", action="store_true", help="打印版本后退出")
    parser.add_argument("--sample", metavar="FILE", help="启动时把该文件载入输入栏")
    parser.add_argument("--checkup", metavar="FILE", nargs="+", help="无界面跑三关体检并打印报告")
    parser.add_argument("--smoke", action="store_true", help="无界面自检引擎、词表、主题与示例配置")
    parser.add_argument("--out", metavar="FILE", help="把 --smoke / --checkup 的输出写入文件")
    parser.add_argument("--lang", default="自动", choices=["自动", "zh", "en"], help="检查提示语言")
    args = parser.parse_args(argv)

    if args.version:
        _emit(VERSION, args.out)
        return 0
    if args.smoke:
        from deai_app.core import selftest

        items = selftest.run()
        _emit(selftest.render(items), args.out)
        return 0 if selftest.ok(items) else 1
    if args.checkup:
        return _checkup(args.checkup, args.lang, args.out)

    from deai_app.ui.app import DeaiApp, ensure_app
    from deai_app.ui.theme import load_theme

    ensure_app(load_theme())  # QApplication 必须先于任何 QWidget 存在
    DeaiApp(sample=args.sample).launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
