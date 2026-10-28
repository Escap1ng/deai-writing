"""build — 用 PyInstaller 把桌面端打成 exe；清单一律来自 bundle.py。

    python3 build/build.py                 # 目录版：build/dist/deai/deai.exe
    python3 build/build.py --onefile       # 单文件版：build/dist/deai.exe
    python3 build/build.py --dry-run       # 只打印命令，不装不跑

默认出目录版：启动不用先解包，杀软误报也少。`--onefile` 只有一个文件好分发，
代价是每次启动要把 bundle 解到临时目录，冷启动明显更慢。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bundle import EXE_NAME, pyinstaller_args  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build", description="打 deai 桌面端 exe")
    parser.add_argument("--onefile", action="store_true", help="打成单个 exe（启动需解包）")
    parser.add_argument("--dry-run", action="store_true", help="只打印 PyInstaller 命令")
    args = parser.parse_args(argv)

    command = pyinstaller_args(onefile=args.onefile)
    if args.dry_run:
        print("\n".join(command))
        return 0
    print(" ".join(command[:12]), "…")
    completed = subprocess.run(command, check=False)
    target = f"dist/{EXE_NAME}.exe" if args.onefile else f"dist/{EXE_NAME}/{EXE_NAME}.exe"
    print(f"退出码 {completed.returncode}；产物在 {Path(__file__).resolve().parent / target}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
