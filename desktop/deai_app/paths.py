"""paths — 定位 code/ 引擎目录与 assets/ 资源目录。

源码运行（python -m deai_app）与 exe 运行（PyInstaller frozen）走同一组入口，
调用方不许自己拼相对路径，也不许读 sys._MEIPASS。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"

#: 三关检查器的单一来源；打包时由 desktop/build/build.py 以 code/ 同名目录放入 bundle。
CODE_DIR = APP_DIR.parent.parent / "code"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def code_dir() -> Path:
    """返回检查器目录；exe 模式下指向 bundle 内的 code/。"""
    if is_frozen():
        bundle = getattr(sys, "_MEIPASS", "")
        return Path(bundle) / "code"
    return CODE_DIR


def require_code_dir() -> Path:
    path = code_dir()
    if not path.is_dir():
        raise LookupError(f"引擎目录不存在：{path}")
    return path
