"""build.bundle — 打包清单：exe 里必须有什么，只在这里说一次。

build.py 与 tests/test_packaging.py 共用这份清单；
`deai_app/paths.py` 在 frozen 模式下按同一套相对位置找 code/ 引擎与 assets/ 资源，
所以这里的 dest 值改了，窗口就会立刻找不到检查器——测试把这条对应关系钉住。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent
DESKTOP_ROOT = BUILD_DIR.parent
APP_DIR = DESKTOP_ROOT / "deai_app"

if str(DESKTOP_ROOT) not in sys.path:
    sys.path.insert(0, str(DESKTOP_ROOT))

from deai_app import paths  # noqa: E402
from deai_app.bridge import engines  # noqa: E402

EXE_NAME = "deai"
ENTRY_SCRIPT = paths.APP_DIR / "__main__.py"

#: bundle 内的相对位置，必须与 paths.code_dir() / paths.ASSETS_DIR 的取法一致。
CODE_DEST = "code"
ASSETS_DEST = "deai_app/assets"

#: 界面只用这三个 Qt 模块；其余按名字排除，能明显压住体积。
ALLOWED_QT = ("QtCore", "QtGui", "QtWidgets")
EXCLUDES = [
    "tkinter",
    "PySide6.QtTest",
    "PySide6.QtNetwork",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtPdf",
    "PySide6.QtCharts",
]


def data_files() -> list[tuple[Path, str]]:
    """(源文件, bundle 内目录) 清单：引擎取自 bridge 自己的依赖列表，不手抄。"""
    files = [(path, CODE_DEST) for path in engines.engine_files()]
    files += [(path, ASSETS_DEST) for path in sorted(paths.ASSETS_DIR.iterdir()) if path.is_file()]
    return files


def add_data_args() -> list[str]:
    args: list[str] = []
    for source, dest in data_files():
        args += ["--add-data", f"{source}{os.pathsep}{dest}"]
    return args


def pyinstaller_args(onefile: bool = False) -> list[str]:
    """组装 PyInstaller 命令行；不执行，便于 --dry-run 与测试核对。"""
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--noupx",
        "--name", EXE_NAME,
        "--distpath", str(BUILD_DIR / "dist"),
        "--workpath", str(BUILD_DIR / "work"),
        "--specpath", str(BUILD_DIR),
        "--paths", str(DESKTOP_ROOT),
        "--onefile" if onefile else "--onedir",
    ]
    for module in EXCLUDES:
        args += ["--exclude-module", module]
    args += add_data_args()
    args.append(str(ENTRY_SCRIPT))
    return args
