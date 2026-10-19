"""motion — 动效的时长、缓动、降级与滚轮步长。

只做三类动效：状态切换（分段控件药丸）、出现（窗口淡入）、反馈（悬停底色）。
时长压在 100–300ms 且一律缓出；系统关闭「显示动画」时全部退化为瞬时。
"""
from __future__ import annotations

import ctypes

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QWidget

FAST_MS = 120      # 悬停、按下反馈
NORMAL_MS = 180    # 药丸滑动、窗口淡入
WHEEL_STEP_PX = 120
EASE_OUT = QEasingCurve.Type.OutCubic
SPI_GETCLIENTAREAANIMATION = 0x1042

__all__ = ["FAST_MS", "NORMAL_MS", "WHEEL_STEP_PX", "EASE_OUT", "enabled", "fade_in",
           "animate_value", "wheel_target"]


def enabled() -> bool:
    """读 Windows 的「显示动画」开关；读不到就当作开启动画。"""
    try:
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except Exception:  # noqa: BLE001 - 非 Windows 或不支持时不影响功能
        return True


def fade_in(widget: QWidget, duration: int = NORMAL_MS) -> None:
    """窗口出现时从 0 淡到 1；动画引用挂在 widget 上，避免被 GC 掉。"""
    if not enabled():
        widget.setWindowOpacity(1.0)
        return
    widget.setWindowOpacity(0.0)
    animation = QPropertyAnimation(widget, b"windowOpacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASE_OUT)
    widget._fade_in = animation  # noqa: SLF001 - 生命周期锚点
    animation.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)


def animate_value(widget: QWidget, name: str, start: float, end: float,
                  duration: int = NORMAL_MS) -> QPropertyAnimation | None:
    """给任意 Qt 属性做数值补间；关闭动画时直接落到终点。

    返回 None 不代表失败：系统关闭动画时属性已经到位，调用方无需再判断。
    """
    if not enabled():
        widget.setProperty(name, end)
        return None
    animation = QPropertyAnimation(widget, name.encode(), widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(EASE_OUT)
    animation.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)
    return animation


def wheel_target(current: int, angle_delta: int, maximum: int,
                 step: int = WHEEL_STEP_PX) -> int:
    """滚轮落点：方向与系统一致，距离按格数折算，夹在 [0, maximum] 内。

    触控板会送来 120 的零头（甚至 pixelDelta 的小值），按比例折算才不会一格跳满。
    """
    if angle_delta == 0:
        return max(0, min(current, maximum))
    delta = -angle_delta * step / 120.0
    return max(0, min(int(round(current + delta)), maximum))
