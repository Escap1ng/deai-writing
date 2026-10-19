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
    QDialog,
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
from deai_app.core import checkup, config
from deai_app.ui import motion, report, style
from deai_app.ui.panes import Pane
from deai_app.ui.rewrite import RewriteWorker
from deai_app.ui.segmented import SegmentedControl
from deai_app.ui.settings import SettingsDialog
from deai_app.ui.theme import Theme, load_theme

MODES = ("降 AI 味", "学术翻译")
VIEW_MODES = ("逐条", "整段")
HINTS = {
    0: "Ctrl+Enter 改写 · Ctrl+O 载入",
    1: "学术翻译将在 M4 接入；改写与体检照常可用",
}
INPUT_PLACEHOLDER = "把稿子贴在这里……（Ctrl+O 可载入 .md / .txt / .tex）"
OUTPUT_PLACEHOLDER = "改写结果与体检报告出现在这里"
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
        self.rewrite_button = QPushButton("AI 改写"); self.rewrite_button.setObjectName("ink")
        self.rewrite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rewrite_button.setToolTip("调用已配置的模型改写，并在每轮后跑本地三关（Ctrl+Enter）")
        self.rewrite_button.clicked.connect(self.start_rewrite)
        bar.addWidget(self.rewrite_button)
        self.check_button = QPushButton("本地三关体检"); self.check_button.setObjectName("ghost")
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_button.clicked.connect(self.run_check)
        bar.addWidget(self.check_button)
        strip = QPushButton("清除不可见字符"); strip.setObjectName("ghost")
        strip.setCursor(Qt.CursorShape.PointingHandCursor)
        strip.clicked.connect(self.strip_invisible)
        bar.addWidget(strip)
        self.strip_button = strip
        self.settings_button = QPushButton("接口设置"); self.settings_button.setObjectName("ghost")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("配置供应商、密钥与改写规则（Ctrl+,）")
        self.settings_button.clicked.connect(self._open_settings)
        bar.addWidget(self.settings_button)
        bar.addStretch()
        self.status = QLabel(""); self.status.setObjectName("hint")
        self.status.setMinimumWidth(0)
        bar.addWidget(self.status)
        band = QWidget(); band.setFixedHeight(int(shell("toolbar_height")))
        band.setLayout(bar)
        column.addWidget(band)

        self._mode = 0
        self._output_view = 0
        self._last_gate: checkup.GateReport | None = None
        self._last_source = ""
        self._last_result: str | None = None
        self._stream_text = ""
        self._worker: RewriteWorker | None = None
        self._providers: list[config.Provider] = []
        self._settings = config.Settings()
        self._active_provider: config.Provider | None = None
        self.input.set_placeholder(INPUT_PLACEHOLDER)
        self.output.set_placeholder(OUTPUT_PLACEHOLDER)
        self.input.refresh_meta()
        self._reload_config()
        for sequence, handler in (
            ("Ctrl+Return", self.start_rewrite), ("Ctrl+Shift+Return", self.run_check),
            ("Ctrl+1", lambda: self._select_tab(0)),
            ("Ctrl+2", lambda: self._select_tab(1)), ("Ctrl+O", self._load), ("Ctrl+S", self._save),
            ("Ctrl+,", self._open_settings),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
        if sample:
            self._read_into(self.input, Path(sample))

    # ---------- 接口与改写 ----------

    def _reload_config(self) -> None:
        try:
            self._settings = config.load_settings()
            self._providers = config.load_providers()
        except (config.ConfigError, OSError) as exc:
            self._providers = []
            self.status.setText(f"配置读取失败：{exc}")
            self._active_provider = None
            return
        self._active_provider = self._pick_provider()
        self.status.setText(self._idle_status())

    def _pick_provider(self) -> config.Provider | None:
        if not self._providers:
            return None
        for provider in self._providers:
            if provider.name == self._settings.active_provider:
                return provider
        return self._providers[0]

    def _provider_error(self, provider: config.Provider | None) -> str:
        if provider is None:
            return "还没有接口配置，先点“接口设置”"
        try:
            provider.validate()
        except config.ConfigError as exc:
            return str(exc)
        return ""

    def _local_check(self, text: str) -> checkup.GateReport | None:
        try:
            return checkup.run(text, self._settings.lang)
        except EngineError as exc:
            self._say(f"检查失败：{exc}")
            return None

    def _idle_status(self) -> str:
        base = f"就绪 · v{VERSION}"
        if self._active_provider is None:
            return f"{base} · 接口未配置"
        state = "未就绪" if self._provider_error(self._active_provider) else self._active_provider.model
        return f"{base} · {self._active_provider.name} · {state}"

    def _open_settings(self, message: str = "") -> None:
        if self._worker is not None:
            self._say("改写进行中：等结束或先停止再改接口设置")
            return
        dialog = SettingsDialog(self.theme, self._providers, self._settings, self)
        if message:
            dialog.set_message(message)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._providers = dialog.providers_out
            self._settings = dialog.settings_out
            self._active_provider = self._pick_provider()
            self._say(f"接口已保存 · {self._active_provider.name} · {self._active_provider.model}")
        else:
            self.status.setText(self._idle_status())

    def start_rewrite(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.rewrite_button.setEnabled(False)
            self._say("正在停止生成……")
            return
        text = self.input.text()
        if not text.strip():
            self._say("输入是空的：先贴一段稿子")
            return
        error = self._provider_error(self._active_provider)
        if error:
            self._open_settings(f"先配置接口：{error}")
            return

        local = self._local_check(text)
        if local is None:
            return
        self.input.set_gate(len(local.phrasing), local.style_risk, local.invisible_total)
        self._last_gate = None
        self._last_source = ""
        self._last_result = None
        self._stream_text = ""
        self._output_view = 1
        self.output_view.select(1, notify=False)
        self.output.set_text("")
        self.output.set_metrics("—", "—", "生成中")

        self.rewrite_button.setText("停止生成")
        self.check_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self._worker = RewriteWorker(text, self._active_provider, self._settings, self)
        self._worker.round_started.connect(self._on_round_start)
        self._worker.delta.connect(self._on_delta)
        self._worker.round_done.connect(self._on_round_done)
        self._worker.done.connect(self._on_rewrite_done)
        self._worker.failed.connect(self._on_rewrite_failed)
        self._worker.cancelled.connect(self._on_rewrite_cancelled)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
        self._say(f"改写中 · {self._active_provider.name} · {self._active_provider.model}")

    def _on_round_start(self, index: int) -> None:
        if index > 1:
            self._stream_text = ""
            self.output.set_text("")
        self._say(f"第 {index} 轮生成中……")

    def _on_delta(self, piece: str) -> None:
        self._stream_text += piece
        self.output.append_text(piece)

    def _on_round_done(self, index: int, result) -> None:
        gate = result.gate
        verdict = "通过" if gate.clean else ("阻断" if gate.blocked else "待改")
        self.output.set_metrics(len(gate.phrasing) + len(gate.style), gate.style_risk, verdict)
        self._say(f"第 {index} 轮复检 · 词表 {len(gate.phrasing)} 处 · 结构 {gate.style_risk}"
                  f"（{len(gate.style)} 处） · 字符 {gate.invisible_total} 个")

    def _on_rewrite_done(self, result) -> None:
        self._last_gate = result.gate
        self._last_source = result.text
        self._last_result = result.text
        self._stream_text = result.text
        self.output.set_text(result.text)
        self._render_output()
        verdict = "通过" if result.clean else ("阻断" if result.gate.blocked else "待改")
        self.output.set_metrics(len(result.gate.phrasing) + len(result.gate.style),
                                result.gate.style_risk, verdict)
        self._say(f"改写完成 · {len(result.rounds)} 轮 · 词表 {len(result.gate.phrasing)} 处 · "
                  f"结构 {result.gate.style_risk} · 门禁：{verdict}")

    def _on_rewrite_failed(self, message: str) -> None:
        self.output.set_metrics("—", "—", "失败")
        self._say(f"改写失败：{message}")

    def _on_rewrite_cancelled(self) -> None:
        self.output.set_metrics("—", "—", "已停止")
        self._say("已停止生成：当前是半成品，未作为结果交付")

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.rewrite_button.setText("AI 改写")
        self.rewrite_button.setEnabled(True)
        self.check_button.setEnabled(True)
        self.settings_button.setEnabled(True)

    # ---------- 动作 ----------

    def run_check(self) -> None:
        if self._worker is not None:
            self._say("改写进行中：等结束或先停止再体检")
            return
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
        self._last_result = None
        self._render_output()
        state = (len(gate.phrasing), gate.style_risk, gate.invisible_total)
        self.input.set_gate(*state)
        verdict = "通过" if gate.clean else ("阻断" if gate.blocked else "待改")
        self.output.set_metrics(len(gate.phrasing) + len(gate.style), gate.style_risk, verdict)
        self._say(f"体检完成 · 用时 {time.perf_counter() - started:.2f}s · 词表 {state[0]} 处 · "
                  f"结构 {state[1]} · 字符 {state[2]} 个 · 门禁：{verdict}")

    def strip_invisible(self) -> None:
        if self._worker is not None:
            self._say("改写进行中：等结束或先停止再清理")
            return
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
        if self._last_gate is not None and self._last_result is None:
            self._last_gate = gate
            self._last_source = self.input.text()
            self._render_output()
        self._say(f"已清除 {count} 个不可见字符" if count else "未发现不可见字符，正文未改动")

    def _copy(self) -> None:
        if self._last_result is not None:
            payload = self._last_result
            label = "改写结果"
        else:
            payload = self.output.text()
            label = "输出"
        if not payload.strip():
            self._say("输出为空，没有可复制的内容")
            return
        QApplication.clipboard().setText(payload)
        self._say(f"已复制{label} {checkup.visible_chars(payload)} 字到剪贴板")

    def _save(self) -> None:
        if self._last_result is not None:
            payload, title, default = self._last_result, "保存改写结果", "降AI改写.md"
        else:
            payload, title, default = self.output.text(), "保存体检报告", "降AI体检.md"
        if not payload.strip():
            self._say("输出为空，没有可保存的内容")
            return
        target, _ = QFileDialog.getSaveFileName(self, title, default,
                                                "Markdown (*.md);;纯文本 (*.txt)")
        if not target:
            return
        Path(target).write_text(payload + "\n", encoding="utf-8")
        self._say(f"已写入 {target}")

    def _load(self) -> None:
        if self._worker is not None:
            self._say("改写进行中：等结束或先停止再载入")
            return
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
        if self._worker is not None:
            self._say("改写进行中：等结束或先停止再清空")
            return
        self.input.set_text("")
        self.input.set_gate(None, None, None)
        self._say("已清空输入")

    def _switch_mode(self, index: int) -> None:
        self._mode = index
        self._say(HINTS[index])

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

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)

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
