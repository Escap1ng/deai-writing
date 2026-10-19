"""segmented — macOS 式分段控件：灰底槽 + 白色药丸随选择滑动。

规格取自 HIG 的控件尺寸：灰色底座、内距 3px、圆角 8px，选中药丸为白底 + 1px 描边；
紧凑档用于栏头，高 26px、内距 2px。药丸滑动 180ms 缓出，系统关闭动画时瞬时到位。
选项数限定 2–5 个（这是分段控件的适用边界，不是通用 Tabs）。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Property, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from deai_app.ui import motion
from deai_app.ui.theme import Theme

INSET = 3
RADIUS = 8


class SegmentedControl(QWidget):
    def __init__(self, theme: Theme, items: Sequence[str], on_select: Callable[[int], None],
                 *, compact: bool = False, accessible_name: str = "模式") -> None:
        super().__init__()
        if not 2 <= len(items) <= 5:
            raise ValueError("分段控件只用于 2–5 个互斥选项")
        self.theme = theme
        self.items = list(items)
        self.on_select = on_select
        self.compact = compact
        self.inset = 2 if compact else INSET
        self.radius = 6 if compact else RADIUS
        self.font_size = theme.size("body") - (2.0 if compact else 0.5)
        self.min_width = 96 if compact else 220
        self.per_item = 26 if compact else 40
        self._index = 0
        self._pill = 0.0
        self._hover = -1
        self._animation = None
        self._keyboard_focus = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(26 if compact else 34)
        self.setMinimumWidth(self.min_width)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(accessible_name)

    # ---------- 状态 ----------

    @property
    def index(self) -> int:
        return self._index

    def _get_pill(self) -> float:
        return self._pill

    def _set_pill(self, value: float) -> None:
        self._pill = value
        self.update()

    pill = Property(float, _get_pill, _set_pill)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        font = QFont(self.font())
        font.setPointSizeF(self.font_size)
        metrics = QFontMetrics(font)
        width = sum(metrics.horizontalAdvance(label) for label in self.items)
        return QSize(max(self.min_width, width + self.per_item * len(self.items)), self.height())

    def _segment_width(self) -> float:
        return (self.width() - self.inset * 2) / len(self.items)

    def _pill_target(self, index: int) -> float:
        return self.inset + index * self._segment_width()

    def select(self, index: int, notify: bool = True) -> None:
        index = max(0, min(index, len(self.items) - 1))
        target = self._pill_target(index)
        if not motion.enabled() or self.width() == 0:
            self._set_pill(target)
        else:
            if self._animation is not None:
                self._animation.stop()
            self._animation = motion.animate_value(self, "pill", self._pill, target,
                                                   motion.NORMAL_MS)
        changed = index != self._index
        self._index = index
        if notify and changed:
            self.on_select(index)
        self.update()

    # ---------- 交互 ----------

    def _index_at(self, x: int) -> int:
        width = self._segment_width()
        return max(0, min(int((x - self.inset) / width), len(self.items) - 1)) if width else 0

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.select(self._index_at(int(event.position().x())))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = self._index_at(int(event.position().x()))
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.select(self._index + (-1 if key == Qt.Key.Key_Left else 1))
        elif key == Qt.Key.Key_Home:
            self.select(0)
        elif key == Qt.Key.Key_End:
            self.select(len(self.items) - 1)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._set_pill(self._pill_target(self._index))

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.theme.color("segment_track")))
        painter.drawRoundedRect(track, self.radius, self.radius)

        pill = QRectF(self._pill, self.inset, self._segment_width(),
                      self.height() - self.inset * 2)
        painter.setBrush(QColor(self.theme.color("segment_pill")))
        painter.setPen(QPen(QColor(self.theme.color("segment_border")), 1))
        painter.drawRoundedRect(pill, self.radius - self.inset + 1,
                                self.radius - self.inset + 1)

        for index, label in enumerate(self.items):
            rect = QRect(int(self.inset + index * self._segment_width()), self.inset,
                         int(self._segment_width()), self.height() - self.inset * 2)
            selected = index == self._index
            if selected:
                color = self.theme.color("segment_text")
            elif index == self._hover:
                color = self.theme.color("text")
            else:
                color = self.theme.color("text_secondary")
            font = QFont(self.font())
            font.setPointSizeF(self.font_size)
            font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(color))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        if self._keyboard_focus and self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.theme.color("focus_ring")), 1.5))
            painter.drawRoundedRect(QRectF(0.75, 0.75, self.width() - 1.5,
                                           self.height() - 1.5), self.radius, self.radius)
        painter.end()
