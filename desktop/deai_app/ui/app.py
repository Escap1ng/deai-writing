"""app — Qt 无边框外壳与装配：标题栏、两栏、工具行、状态。

无边框靠三件事：WA_TranslucentBackground + 圆角卡片 + QGraphicsDropShadowEffect；
拖拽与缩放交给 startSystemMove / startSystemResize，因此 Aero 贴边分屏与任务栏行为都是原生的。
窗口四周 canvas_margin 的透明边既是投影留白，也是缩放的抓取区。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Property, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from deai_app import VERSION
from deai_app.bridge import EngineError, engines
from deai_app.core import checkup
from deai_app.ui import motion, report, style
from deai_app.ui.panes import Pane
from deai_app.ui.segmented import SegmentedControl
from deai_app.ui.theme import Theme, load_theme

MODES = ("降 AI 味", "学术翻译")
VIEW_MODES = ("逐条", "整段")
HINTS = {
    0: "Ctrl+Enter 体检 · Ctrl+O 载入 · Ctrl+S 存报告",
    1: "学术翻译的模型调用在 M4 接入；三关体检对任何文本都可用",
}
INPUT_PLACEHOLDER = "把稿子贴在这里……（Ctrl+O 可载入 .md / .txt / .tex）"
OUTPUT_PLACEHOLDER = "体检报告与改写结果出现在这里"
READ_SUFFIXES = {".md", ".txt", ".tex", ".bib", ".typ"}
CAPTION_KINDS = ("min", "max", "close")


class CaptionButton(QToolButton):
    """窗口三键：QPainter 画 10×10 的几何图形，不用文字字形。

    文字字形（长横、方框、叉号）的字重、字宽与次像素边各不相同，缩到 28px 高时看起来像三种语言；
    这里统一 1.25px 描边、圆角端点，关闭键悬停转红底白图标。
    """

    def __init__(self, theme: Theme, kind: str, on_click) -> None:
        super().__init__()
        self.theme = theme
        self.kind = kind
        self.setObjectName("close" if kind == "close" else "")
        self.setFixedSize(40, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip({"min": "最小化", "max": "最大化", "close": "关闭"}[kind])
        self._hover = 0.0
        self._hover_animation = None
        self.clicked.connect(on_click)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def _animate_hover(self, target: float) -> None:
        if self._hover_animation is not None:
            self._hover_animation.stop()
        self._hover_animation = motion.animate_value(self, "hover", self._hover, target,
                                                     motion.FAST_MS)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().enterEvent(event)
        self._animate_hover(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._animate_hover(0.0)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover > 0:
            background = QColor(self.theme.color(
                "gate_block" if self.kind == "close" else "surface_hover"))
            background.setAlphaF(self._hover)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 6, 6)
        color = self.theme.color(
            "ink_fg" if (self.kind == "close" and self._hover > 0.5) else "text")
        pen = QPen(QColor(color))
        pen.setWidthF(1.25)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        cx, cy, half = self.width() / 2, self.height() / 2, 5.0
        if self.kind == "min":
            painter.drawLine(QPointF(cx - half, cy), QPointF(cx + half, cy))
        elif self.kind == "max":
            painter.drawRoundedRect(QRectF(cx - half, cy - half, half * 2, half * 2), 1.5, 1.5)
        else:
            painter.drawLine(QPointF(cx - half, cy - half), QPointF(cx + half, cy + half))
            painter.drawLine(QPointF(cx - half, cy + half), QPointF(cx + half, cy - half))
        painter.end()


def ensure_app(theme: Theme) -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont(theme.family("cjk"), theme.size("body")))
    app.setStyleSheet(style.stylesheet(theme))
    return app


class TitleBar(QWidget):
    def __init__(self, theme: Theme, on_tab, on_minimize, on_maximize, on_close) -> None:
        super().__init__()
        self.setFixedHeight(int(theme.shell("titlebar_height")))
        self.setStyleSheet("background: transparent;")
        row = QHBoxLayout(self)
        # 左边距 = 栏内容边距 + 文档边距，品牌与两栏标题同一条左缘线
        row.setContentsMargins(int(theme.shell("content_padding")) + int(theme.shell("document_margin")),
                               0, 0, 0)
        row.setSpacing(4)
        self.brand_label = QLabel("降 AI 工作台")
        self.brand_label.setObjectName("brand")
        row.addWidget(self.brand_label)
        row.addSpacing(24)
        self.tabs = SegmentedControl(theme, MODES, on_tab)
        self.tabs.setToolTip("切换模式（Ctrl+1 / Ctrl+2）")
        row.addWidget(self.tabs)
        row.addStretch()
        for kind, handler in (("min", on_minimize), ("max", on_maximize), ("close", on_close)):
            row.addWidget(CaptionButton(theme, kind, handler))

    def select_tab(self, index: int) -> None:
        self.tabs.select(index, notify=False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.window().toggle_maximize()


class DeaiApp(QWidget):
    def __init__(self, theme: Theme | None = None, sample: str | None = None) -> None:
        super().__init__()
        self.theme = theme or load_theme()
        self.setObjectName("shell")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("降 AI 工作台")
        shell = self.theme.shell
        self.resize(int(shell("width")), int(shell("height")))
        self.setMinimumSize(int(shell("min_width")), int(shell("min_height")))

        outer = QVBoxLayout(self)
        margin = int(shell("canvas_margin"))
        outer.setContentsMargins(margin, margin, margin, margin)
        card = QFrame(); card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(blurRadius=int(shell("shadow_blur")),
                                           xOffset=0, yOffset=int(shell("shadow_y")))
        shadow.setColor(QColor(20, 20, 22, int(shell("shadow_alpha"))))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        column = QVBoxLayout(card)
        column.setContentsMargins(margin, 10, margin - 4, 0); column.setSpacing(10)
        self.titlebar = TitleBar(self.theme, self._switch_mode, self.showMinimized,
                                 self.toggle_maximize, self.close)
        column.addWidget(self.titlebar)

        row = QHBoxLayout(); row.setSpacing(int(shell("pane_gap")))
        self.input = Pane("输入", self.theme, actions=[("清空", self._clear), ("载入", self._load)])
        self.output_view = SegmentedControl(
            self.theme, VIEW_MODES, self._switch_output_view,
            compact=True, accessible_name="输出视图",
        )
        self.output_view.setToolTip("切换逐条报告与整段原文")
        self.output = Pane("输出", self.theme, readonly=True, band="metrics",
                           actions=[("复制", self._copy), ("存为文件", self._save)],
                           header_extra=self.output_view)
        row.addWidget(self.input, 1); row.addWidget(self.output, 1)
        column.addLayout(row, 1)

        bar = QHBoxLayout(); bar.setSpacing(6)
        self.check_button = QPushButton("本地三关体检"); self.check_button.setObjectName("ink")
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_button.clicked.connect(self.run_check)
        bar.addWidget(self.check_button)
        strip = QPushButton("清除不可见字符"); strip.setObjectName("ghost")
        strip.setCursor(Qt.CursorShape.PointingHandCursor)
        strip.clicked.connect(self.strip_invisible)
        bar.addWidget(strip)
        self.hint = QLabel(HINTS[0]); self.hint.setObjectName("hint")
        bar.addSpacing(8); bar.addWidget(self.hint); bar.addStretch()
        self.status = QLabel(f"就绪 · v{VERSION}"); self.status.setObjectName("hint")
        bar.addWidget(self.status)
        band = QWidget(); band.setFixedHeight(int(shell("toolbar_height")))
        band.setLayout(bar)
        column.addWidget(band)

        self._mode = 0
        self._output_view = 0
        self._last_gate: checkup.GateReport | None = None
        self._last_source = ""
        self.input.set_placeholder(INPUT_PLACEHOLDER)
        self.output.set_placeholder(OUTPUT_PLACEHOLDER)
        self.input.refresh_meta()
        for sequence, handler in (
            ("Ctrl+Return", self.run_check), ("Ctrl+1", lambda: self._select_tab(0)),
            ("Ctrl+2", lambda: self._select_tab(1)), ("Ctrl+O", self._load), ("Ctrl+S", self._save),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
        if sample:
            self._read_into(self.input, Path(sample))

    # ---------- 动作 ----------

    def run_check(self) -> None:
        text = self.input.text()
        if not text.strip():
            self._say("输入是空的：先贴一段稿子")
            return
        started = time.perf_counter()
        try:
            gate = checkup.run(text, "自动")
        except EngineError as exc:
            self._say(f"检查失败：{exc}")
            return
        self._last_gate = gate
        self._last_source = text
        self._render_output()
        state = (len(gate.phrasing), gate.style_risk, gate.invisible_total)
        self.input.set_gate(*state)
        verdict = "通过" if gate.clean else ("阻断" if gate.blocked else "待改")
        self.output.set_metrics(len(gate.phrasing) + len(gate.style), gate.style_risk, verdict)
        self._say(f"体检完成 · 用时 {time.perf_counter() - started:.2f}s · 词表 {state[0]} 处 · "
                  f"结构 {state[1]} · 字符 {state[2]} 个 · 门禁：{verdict}")

    def strip_invisible(self) -> None:
        text = self.input.text()
        if not text:
            self._say("没有可清理的文本")
            return
        cleaned, removed = engines.invisible_clean(text)
        count = sum(removed.values())
        if count:
            self.input.set_text(cleaned)
        gate = checkup.run(self.input.text(), "自动")
        self.input.set_gate(len(gate.phrasing), gate.style_risk, gate.invisible_total)
        if self._last_gate is not None:
            self._last_gate = gate
            self._last_source = self.input.text()
            self._render_output()
        self._say(f"已清除 {count} 个不可见字符" if count else "未发现不可见字符，正文未改动")

    def _copy(self) -> None:
        payload = self.output.text()
        if not payload.strip():
            self._say("输出为空，没有可复制的内容")
            return
        QApplication.clipboard().setText(payload)
        self._say(f"已复制 {checkup.visible_chars(payload)} 字到剪贴板")

    def _save(self) -> None:
        payload = self.output.text()
        if not payload.strip():
            self._say("输出为空，没有可保存的内容")
            return
        target, _ = QFileDialog.getSaveFileName(self, "保存体检报告", "降AI体检.md",
                                                "Markdown (*.md);;纯文本 (*.txt)")
        if not target:
            return
        Path(target).write_text(payload + "\n", encoding="utf-8")
        self._say(f"已写入 {target}")

    def _load(self) -> None:
        target, _ = QFileDialog.getOpenFileName(self, "载入稿子", "",
                                                "文稿 (*.md *.txt *.tex *.bib *.typ);;所有文件 (*)")
        if target:
            self._read_into(self.input, Path(target))

    def _read_into(self, pane: Pane, path: Path) -> None:
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            self._say(f"读不了 {path.name}：{exc}")
            return
        pane.set_text(text)
        pane.scroll_to_top()
        if path.suffix.lower() not in READ_SUFFIXES:
            self._say(f"{path.name}：后缀不在检查器口径内，仍已载入")

    def _clear(self) -> None:
        self.input.set_text("")
        self.input.set_gate(None, None, None)
        self._say("已清空输入")

    def _switch_mode(self, index: int) -> None:
        self._mode = index
        self.hint.setText(HINTS[index])

    def _select_tab(self, index: int) -> None:
        self.titlebar.select_tab(index)
        self._switch_mode(index)

    def _render_output(self) -> None:
        if self._last_gate is None:
            return
        renderer = (report.render_annotated_html if self._output_view == 1
                    else report.render_html)
        self.output.set_html(renderer(self._last_gate, self._last_source, self.theme))

    def _switch_output_view(self, index: int) -> None:
        self._output_view = index
        if self._last_gate is None:
            self._say("先跑一次体检，再切换输出视图")
            return
        self._render_output()
        self._say("输出视图：逐条（规则与改法）" if index == 0
                  else "输出视图：整段（底色标出词表命中）")

    def _say(self, text: str) -> None:
        self.status.setText(text)

    # ---------- 窗口 ----------

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _resize_edges(self, x: int, y: int) -> Qt.Edge:
        margin = int(self.theme.shell("canvas_margin"))
        edges = Qt.Edge(0)
        if x <= margin:
            edges |= Qt.Edge.LeftEdge
        if x >= self.width() - margin:
            edges |= Qt.Edge.RightEdge
        if y <= margin:
            edges |= Qt.Edge.TopEdge
        if y >= self.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        point = event.position().toPoint()
        edges = self._resize_edges(point.x(), point.y())
        if edges and event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemResize(edges)

    def launch(self) -> int:
        ensure_app(self.theme)
        if motion.enabled():
            self.setWindowOpacity(0.0)  # 先透明再 show，避免淡入前闪一帧实心窗口
        self.show()
        motion.fade_in(self)
        return QApplication.exec()
