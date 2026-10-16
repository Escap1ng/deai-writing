"""依赖方向与越界检查：ui → core → bridge → code/，且只有 ui 能碰 tkinter。

这套规则本身要能失败：test_synthetic_violation_is_caught 用一段假源码验证探测器会报，
否则探测器可能是个永远绿的摆设。
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

import deai_app

APP_DIR = Path(deai_app.__file__).resolve().parent
LAYERS = ("ui", "core", "bridge")

#: 每个层允许向上依赖哪些层；集合外的 deai_app 子包即为违例
FORBIDDEN_TARGETS = {
    "infra": {"ui", "core", "bridge"},
    "bridge": {"ui", "core"},
    "core": {"ui"},
    "ui": set(),
}

#: 无界面可执行的文件，即使位于 ui/ 也不许 import tkinter
TKINTER_FREE_FILES = {"ui/theme.py"}

#: 引擎模块只能由 bridge 用 importlib 按路径载入，不许出现在静态 import 里
ENGINE_MODULES = {"check_phrasing", "check_style", "strip_invisible"}

#: bridge 不许落盘：任何写文件/临时文件的调用都会破坏"内存文本单一口径"
BRIDGE_FILESYSTEM_TOKENS = ("open(", ".write_text(", ".write_bytes(", "tempfile", "mkdir", "shutil")


def rel_path(path: Path) -> str:
    return path.relative_to(APP_DIR).as_posix()


def layer_of(rel: str) -> str:
    top = rel.split("/", 1)[0]
    return top if top in LAYERS else "infra"


def resolve_target(own_layer: str, module: str | None, level: int, name: str | None) -> str | None:
    """把一条 import 语句解析成 deai_app 下的层名；非 deai_app 的返回 None。"""
    if level == 0:
        if module == "deai_app":
            return "infra"
        if module and module.startswith("deai_app."):
            return module.split(".")[1] if module.split(".")[1] in LAYERS else "infra"
        return None
    # 相对导入：level=1 是当前包，level=2 是 deai_app
    if level >= 2:
        return (name or "").split(".")[0] or own_layer
    base = own_layer if own_layer != "infra" else "deai_app"
    return base if not name else own_layer


def imports_of(source: str, filename: str) -> list[tuple[str, str]]:
    """返回 (层名或库名, 说明) 列表——只关心会触发规则的 import。"""
    own = layer_of(filename)
    found: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((resolve_target(own, alias.name, 0, None) or alias.name, alias.name))
        elif isinstance(node, ast.ImportFrom):
            target = resolve_target(own, node.module, node.level, node.module if node.level == 0 else node.module)
            found.append((target or (node.module or ""), node.module or f".{'/' * node.level}{node.names[0].name}"))
    return found


def layering_violations(graph: dict[str, list[tuple[str, str]]]) -> list[str]:
    """graph: 文件相对路径 → imports_of() 结果。返回人可读的违例清单。"""
    problems: list[str] = []
    for filename, imports in graph.items():
        own = layer_of(filename)
        for target, spelled in imports:
            if target in FORBIDDEN_TARGETS.get(own, set()):
                problems.append(f"{filename}（{own} 层）依赖 {spelled}：{own} 不许引用 {target}")
            if spelled.startswith("tkinter") or spelled == "tkinter":
                if filename not in TKINTER_FREE_FILES and own != "ui":
                    problems.append(f"{filename}（{own} 层）import tkinter：只有 ui 层可以")
            if spelled in ENGINE_MODULES:
                problems.append(f"{filename} 直接 import 引擎模块 {spelled}：应经 bridge 载入")
    return problems


def source_graph() -> dict[str, list[tuple[str, str]]]:
    graph: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        graph[rel_path(path)] = imports_of(path.read_text(encoding="utf-8"), rel_path(path))
    return graph


class TestLayering(unittest.TestCase):
    def test_real_tree_has_no_violation(self) -> None:
        self.assertEqual(layering_violations(source_graph()), [])

    def test_synthetic_violation_is_caught(self) -> None:
        """探测器必须能报出假源码里的越界，否则本测试是空的。"""
        bad = "from deai_app.ui import theme\nimport tkinter\nimport check_style\n"
        problems = layering_violations({"core/pipeline.py": imports_of(bad, "core/pipeline.py")})
        self.assertEqual(len(problems), 3, problems)

    def test_ui_may_import_core_and_bridge(self) -> None:
        good = "from deai_app.core import jobs\nfrom deai_app.bridge import engines\nimport tkinter\n"
        self.assertEqual(layering_violations({"ui/frame.py": imports_of(good, "ui/frame.py")}), [])

    def test_bridge_does_not_touch_filesystem(self) -> None:
        for path in (APP_DIR / "bridge").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in BRIDGE_FILESYSTEM_TOKENS:
                self.assertNotIn(token, text, f"{rel_path(path)} 含落盘调用 {token}")

    def test_only_expected_packages_exist(self) -> None:
        dirs = {p.name for p in APP_DIR.iterdir() if p.is_dir() and not p.name.startswith("__")}
        self.assertEqual(dirs, {"ui", "core", "bridge", "assets"})


if __name__ == "__main__":
    unittest.main()
