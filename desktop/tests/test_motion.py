"""动效层的行为与降级：时长在 HIG 区间、缓出、系统关闭动画时瞬时到位。

这里不需要人眼看窗口：药丸位置、滚动落点、属性终点都是可量的数值。
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEasingCurve, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from deai_app.ui import motion  # noqa: E402
from deai_app.ui.segmented import INSET, SegmentedControl  # noqa: E402
from deai_app.ui.theme import load_theme  # noqa: E402

QAPP = QApplication.instance() or QApplication([])


class TestMotionSpec(unittest.TestCase):
    def test_durations_stay_inside_100_to_300ms(self) -> None:
        for value in (motion.FAST_MS, motion.NORMAL_MS):
            self.assertGreaterEqual(value, 100)
            self.assertLessEqual(value, 300)
        self.assertLess(motion.FAST_MS, motion.NORMAL_MS)

    def test_easing_is_ease_out(self) -> None:
        self.assertEqual(motion.EASE_OUT, QEasingCurve.Type.OutCubic)

    def test_system_animation_flag_is_readable(self) -> None:
        self.assertIsInstance(motion.enabled(), bool)


class TestWheelTarget(unittest.TestCase):
    def test_direction_matches_native_scrolling(self) -> None:
        self.assertEqual(motion.wheel_target(500, 120, 1000), 380)
        self.assertEqual(motion.wheel_target(500, -120, 1000), 620)

    def test_high_resolution_delta_scrolls_proportionally(self) -> None:
        self.assertEqual(motion.wheel_target(500, 60, 1000), 440)
        self.assertEqual(motion.wheel_target(500, 20, 1000), 480)

    def test_clamped_at_both_ends(self) -> None:
        self.assertEqual(motion.wheel_target(50, 120, 1000), 0)
        self.assertEqual(motion.wheel_target(990, -240, 1000), 1000)
        self.assertEqual(motion.wheel_target(500, 0, 1000), 500)

    def test_current_beyond_maximum_is_clamped_even_without_wheel(self) -> None:
        self.assertEqual(motion.wheel_target(1200, 0, 1000), 1000)


class TestDegradation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()

    def test_animate_value_lands_immediately_when_animation_off(self) -> None:
        widget = QWidget()
        with patch.object(motion, "enabled", return_value=False):
            animation = motion.animate_value(widget, "probe", 0.0, 7.0, motion.NORMAL_MS)
        self.assertIsNone(animation)
        self.assertEqual(widget.property("probe"), 7.0)

    def test_segmented_pill_jumps_when_animation_off(self) -> None:
        control = SegmentedControl(self.theme, ("降 AI 味", "学术翻译"), lambda _i: None)
        control.resize(260, control.height())
        with patch.object(motion, "enabled", return_value=False):
            control.select(1)
        self.assertAlmostEqual(control.pill, INSET + (260 - 2 * INSET) * 0.5, delta=0.01)

    def test_compact_mode_keeps_hit_target_and_pill_geometry(self) -> None:
        control = SegmentedControl(self.theme, ("逐条", "整段"), lambda _i: None, compact=True)
        self.assertGreaterEqual(control.height(), 24)
        control.resize(120, control.height())
        with patch.object(motion, "enabled", return_value=False):
            control.select(1)
        expected = control.inset + (120 - 2 * control.inset) * 0.5
        self.assertAlmostEqual(control.pill, expected, delta=0.01)

    def test_fade_in_is_instant_when_animation_off(self) -> None:
        widget = QWidget()
        widget.setWindowOpacity(0.25)
        with patch.object(motion, "enabled", return_value=False):
            motion.fade_in(widget)
        self.assertEqual(widget.windowOpacity(), 1.0)


class TestAnimatedEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.theme = load_theme()

    def test_segmented_pill_reaches_selected_segment(self) -> None:
        control = SegmentedControl(self.theme, ("降 AI 味", "学术翻译"), lambda _i: None)
        control.resize(260, control.height())
        control.show()
        if not motion.enabled():
            self.skipTest("本机关闭了显示动画")
        control.select(1)
        QTest.qWait(motion.NORMAL_MS + 120)
        self.assertAlmostEqual(control.pill, INSET + (260 - 2 * INSET) * 0.5, delta=1.0)
        self.assertEqual(control.index, 1)

    def test_fade_in_reaches_full_opacity(self) -> None:
        widget = QWidget()
        widget.resize(120, 80)
        widget.show()
        if not motion.enabled():
            self.skipTest("本机关闭了显示动画")
        motion.fade_in(widget)
        QTest.qWait(motion.NORMAL_MS + 120)
        self.assertGreater(widget.windowOpacity(), 0.95)

    def test_keyboard_selection_notifies_once(self) -> None:
        seen: list[int] = []
        control = SegmentedControl(self.theme, ("降 AI 味", "学术翻译"), seen.append)
        control.resize(260, control.height())
        control.show()
        control.setFocus()
        QTest.keyClick(control, Qt.Key.Key_Right)
        self.assertEqual(control.index, 1)
        self.assertEqual(seen, [1])


if __name__ == "__main__":
    unittest.main()
