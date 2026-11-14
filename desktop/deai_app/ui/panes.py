"""panes — 一栏：头部（标题 · 字数 · 动作）+ 正文 + 底部带（三关片或指标）。

输入栏与输出栏共用一个类，差别只在只读与底部带形态。
行距在 set_text/set_html 后整篇施加一次 block format，不做逐键处理。
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl, Qt, Signal
from PySide6.QtGui import QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from deai_app.core import checkup
from deai_app.ui import motion
from deai_app.ui.theme import Theme

GATE_LABELS = ("词表", "结构", "字符")
RISK_COLOR = {"低": "gate_pass", "中": "gate_warn", "高": "gate_block", "极高": "gate_block"}


def first_loadable_url(urls: list[QUrl], suffixes: Collection[str]) -> Path | None:
    """从拖入的 URL 里挑第一个后缀可读的本地文件；没有就返回 None。"""
    for url in urls:
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.suffix.lower() in suffixes:
            return path
    return None


class Pane(QFrame):
    #: 只读栏里点到带 href 的文字时发出（QTextEdit 没有 anchorClicked，这里自己识别）
    link_clicked = Signal(QUrl)

    def __init__(self, title: str, theme: Theme, *, readonly: bool = False,
                 actions: Sequence[tuple[str, Callable[[], None]]] = (), band: str = "chips",
                 header_extra: QWidget | None = None,
                 drop_suffixes: Collection[str] | None = None,
                 on_drop: Callable[[Path], None] | None = None) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("pane")
        self._band_mode = band
        self._drop_suffixes = drop_suffixes
        self._on_drop = on_drop
        if drop_suffixes is not None:
            self.setAcceptDrops(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(int(theme.shell("content_padding")), 12,
                                 int(theme.shell("content_padding")), 0)
        outer.setSpacing(8)

        head = QHBoxLayout(); head.setSpacing(6)
        # 标题与正文首字符同一条左缘线：头部再缩进一个 document_margin
        head.setContentsMargins(int(theme.shell("document_margin")), 0, 0, 0)
        label = QLabel(title); label.setObjectName("paneTitle"); self.title_label = label
        head.addWidget(self.title_label)
        if header_extra is not None:
            head.addSpacing(12)
            head.addWidget(header_extra)
        head.addStretch()
        self.meta = QLabel(""); self.meta.setObjectName("meta"); head.addWidget(self.meta)
        self._action_buttons: list[QPushButton] = []
        for name, callback in actions:
            button = QPushButton(name); button.setObjectName("text"); button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(callback); head.addWidget(button)
            self._action_buttons.append(button)
        head_widget = QWidget(); head_widget.setFixedHeight(int(theme.shell("pane_header_height")))
        head_widget.setLayout(head); head_widget.setStyleSheet("background: transparent;")
        outer.addWidget(head_widget)

        self.edit = QTextEdit(self)
        self.edit.setFrameShape(QFrame.Shape.NoFrame)
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setReadOnly(readonly)
        # QTextEdit 不会自动打开链接：报告里的 locate/more 锚点只发 anchorClicked，由主窗口处理
        self.edit.document().setDocumentMargin(int(theme.shell("document_margin")))
        self.edit.textChanged.connect(self.refresh_meta)
        self._wheel_animation = None
        self._readonly = readonly
        self.edit.viewport().installEventFilter(self)
        outer.addWidget(self.edit, 1)
        outer.addWidget(self._build_band())

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt 命名
        """滚轮改成 120ms 补间：默认的一格瞬移在长稿里很跳。"""
        if watched is self.edit.viewport() and event.type() == QEvent.Type.Wheel:
            bar = self.edit.verticalScrollBar()
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                target = motion.wheel_target(bar.value(), delta, bar.maximum())
                if target != bar.value():
                    if self._wheel_animation is not None:
                        self._wheel_animation.stop()
                    self._wheel_animation = motion.animate_value(
                        bar, "value", bar.value(), target, motion.FAST_MS)
                return True
        if (watched is self.edit.viewport() and self._readonly
                and event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton):
            anchor = self.edit.anchorAt(event.position().toPoint())
            if anchor:
                self.link_clicked.emit(QUrl(anchor))
                return True
        return super().eventFilter(watched, event)

    # ---------- 拖放载入 ----------

    def _set_drag_over(self, value: bool) -> None:
        if self.property("dragOver") == value:
            return
        self.setProperty("dragOver", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def _drop_target(self, event) -> Path | None:
        """事件可接受返回目标文件（顺带打高亮），否则 None。"""
        suffixes = self._drop_suffixes
        if suffixes is None or self._on_drop is None or not event.mimeData().hasUrls():
            return None
        return first_loadable_url(event.mimeData().urls(), suffixes)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._drop_target(event) is not None:
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._drop_target(event) is not None:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        target = self._drop_target(event)
        self._set_drag_over(False)
        if target is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._on_drop(target)

    # ---------- 底部带 ----------

    def _build_band(self) -> QWidget:
        band = QWidget(); band.setObjectName("band"); self.band = band
        # 底部带是面板最后一块：下缘两角跟面板同半径，避免直角从圆角里露出来
        radius = int(self.theme.shell("pane_radius")) - 1
        band.setStyleSheet(
            f"#band {{ border-bottom-left-radius: {radius}px;"
            f" border-bottom-right-radius: {radius}px; }}")
        layout = QHBoxLayout(band)
        layout.setContentsMargins(12, 8, 12, 10); layout.setSpacing(18)
        band.setFixedHeight(int(self.theme.shell("band_height")))
        self._band_layout = layout
        self.chips: list[tuple[QLabel, QLabel]] = []
        self.metrics: list[tuple[QLabel, QLabel]] = []
        if self._band_mode == "chips":
            for name in GATE_LABELS:
                dot, text = QLabel(), QLabel(f"{name} —")
                dot.setObjectName("dot"); dot.setFixedSize(8, 8)
                # 未体检时也要画出来：给一个中性底色，否则三关片只剩文字、没有圆点
                dot.setStyleSheet(f"background: {self.theme.color('divider_strong')}; border-radius: 4px;")
                text.setObjectName("meta")
                layout.addWidget(dot); layout.addWidget(text)
                self.chips.append((dot, text))
        else:
            for name in ("命中", "风险", "门禁"):
                column = QVBoxLayout(); column.setSpacing(0)
                number, label = QLabel("—"), QLabel(name)
                number.setObjectName("metricNum"); label.setObjectName("metricLab")
                number.setStyleSheet(f"color: {self.theme.color('text_muted')};")  # 未体检时别让三个长破折号变成黑杠
                column.addWidget(number); column.addWidget(label)
                layout.addLayout(column)
                self.metrics.append((number, label))
        layout.addStretch()
        return band

    def set_gate(self, phrasing: int | None, risk: str | None, invisible: int | None) -> None:
        values = (phrasing, risk, invisible)
        for (dot, text), name, value in zip(self.chips, GATE_LABELS, values):
            color = self._gate_color(name, value)
            dot.setStyleSheet(f"background: {self.theme.color(color)}; border-radius: 4px;")
            text.setText(f"{name} {'—' if value is None else value}")

    def _gate_color(self, name: str, value: object) -> str:
        if value is None:
            return "divider_strong"
        if name == "结构":
            return RISK_COLOR.get(str(value), "divider_strong")
        return "gate_pass" if value == 0 else "gate_block"

    def set_metrics(self, hits: int | str, risk: str, verdict: str) -> None:
        colors = {"通过": "gate_pass", "待改": "gate_warn", "阻断": "gate_block"}
        for (number, label), value, color_key in zip(
                self.metrics, (hits, risk, verdict), ("text", RISK_COLOR.get(risk, "text_muted"), colors.get(verdict, "text_muted"))):
            number.setText(str(value))
            number.setStyleSheet(f"color: {self.theme.color(color_key)};")

    def set_actions_enabled(self, enabled: bool) -> None:
        for button in self._action_buttons:
            button.setEnabled(enabled)

    # ---------- 文本 ----------

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, value: str) -> None:
        self.edit.setPlainText(value)
        self._apply_line_spacing()
        self.edit.moveCursor(QTextCursor.MoveOperation.Start)

    def set_html(self, markup: str) -> None:
        self.edit.setHtml(markup)
        self.edit.moveCursor(QTextCursor.MoveOperation.Start)

    def append_text(self, value: str) -> None:
        """流式增量：插到末尾并跟随光标，不重建整篇文档。"""
        cursor = self.edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(value)
        self.edit.setTextCursor(cursor)
        self.edit.ensureCursorVisible()

    def _apply_line_spacing(self) -> None:
        fmt = QTextBlockFormat()
        fmt.setLineHeight(int(self.theme.shell("line_spacing")),
                          QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor = self.edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()

    def set_placeholder(self, value: str) -> None:
        self.edit.setPlaceholderText(value)

    def refresh_meta(self) -> None:
        value = self.text()
        self.meta.setText(f"{checkup.visible_chars(value)} 字 · {len(value.splitlines())} 行")

    def scroll_to_top(self) -> None:
        self.edit.verticalScrollBar().setValue(0)

    def set_clipboard(self, payload: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(payload)
