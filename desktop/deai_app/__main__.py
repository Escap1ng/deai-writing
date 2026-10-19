"""deai_app 命令行入口。

    python3 -m deai_app                 # 开无边框主窗口
    python3 -m deai_app --sample F      # 开窗口并把 F 灌进输入栏（看版式撑不撑）
    python3 -m deai_app --checkup FILE  # 不开窗口，直接输出三关体检报告
    python3 -m deai_app --version
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deai_app import VERSION


def _checkup(paths: list[str], lang: str) -> int:
    from deai_app.bridge import EngineError
    from deai_app.core import checkup

    code = 0
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            sys.stderr.write(f"读不了 {path}：{exc}\n")
            code = 2
            continue
        report = checkup.run(text, lang)
        print(checkup.render(report, text))
        code = code or (1 if not report.clean else 0)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deai_app", description="降 AI 写作工作台")
    parser.add_argument("--version", action="store_true", help="打印版本后退出")
    parser.add_argument("--sample", metavar="FILE", help="启动时把该文件载入输入栏")
    parser.add_argument("--checkup", metavar="FILE", nargs="+", help="无界面跑三关体检并打印报告")
    parser.add_argument("--lang", default="自动", choices=["自动", "zh", "en"], help="检查提示语言")
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0
    if args.checkup:
        return _checkup(args.checkup, args.lang)

    from deai_app.ui.app import DeaiApp, ensure_app
    from deai_app.ui.theme import load_theme

    ensure_app(load_theme())  # QApplication 必须先于任何 QWidget 存在
    DeaiApp(sample=args.sample).launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
