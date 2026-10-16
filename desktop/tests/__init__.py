"""桌面应用测试包。

做成包是为了让 `unittest discover` 先执行本文件、把 desktop/ 塞进 sys.path，
测试里才能直接 `from deai_app... import ...`。
"""
import sys
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
if str(DESKTOP_ROOT) not in sys.path:
    sys.path.insert(0, str(DESKTOP_ROOT))
