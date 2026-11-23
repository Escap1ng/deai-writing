"""style — 把 theme.json 的 token 翻成一份 QSS。

界面代码只引用 token 或 objectName，不出现裸色值与裸字号。
v4 视觉：浅灰工作区 + 白色面板 + 单一蓝色强调；次级按钮白底细描边，
主按钮只留一个；滚动条画成细圆条，避免 Qt 默认的凹陷 groove。
"""
from __future__ import annotations

from deai_app.ui.theme import Theme, load_theme

__all__ = ["stylesheet"]


def stylesheet(theme: Theme | None = None) -> str:
    theme = theme or load_theme()
    c = theme.color
    s = theme.shell
    f = theme.size
    return f"""
* {{ outline: 0; }}
QWidget {{
    background: transparent;
    color: {c('text')};
    font-family: "{theme.family('cjk')}";
    font-size: {f('body')}pt;
}}
#shell {{ background: {c('canvas_bg')}; }}
#card {{
    background: {c('canvas_bg')};
    border: none;
    border-radius: {s('card_radius')}px;
}}
#brand {{ font-size: {f('title')}pt; font-weight: 700; color: {c('text')}; }}

QToolButton {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('meta')}pt; border-radius: 8px;
}}

#pane {{
    background: {c('panel_bg')};
    border: 1px solid {c('divider')};
    border-radius: {s('pane_radius')}px;
}}
#pane[dragOver="true"] {{ border: 2px solid {c('focus_ring')}; }}
#paneTitle {{ font-size: {f('emphasis')}pt; font-weight: 600; }}
#meta {{ font-size: {f('meta')}pt; color: {c('text_muted')}; }}
#hint {{ font-size: {f('meta')}pt; color: {c('text_secondary')}; }}

QPushButton {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('body')}pt; border-radius: 8px;
}}
QPushButton#text {{
    color: {c('text_secondary')}; font-size: {f('meta')}pt;
    padding: 6px 10px; border-radius: 7px;
}}
QPushButton#text:hover {{ background: {c('surface_hover')}; color: {c('text')}; }}
QPushButton#text:pressed {{ background: {c('surface_selected')}; }}
QPushButton#text:disabled {{ color: {c('text_muted')}; background: transparent; }}

QPushButton#ink {{
    background: {c('ink_bg')}; color: {c('ink_fg')}; border: none;
    border-radius: 9px; padding: 0 22px; min-height: {s('button_height')}px;
    font-size: {f('body')}pt; font-weight: 600;
}}
QPushButton#ink:hover {{ background: {c('ink_hover')}; }}
QPushButton#ink:pressed {{ background: {c('ink_hover')}; }}
QPushButton#ink:disabled {{ background: {c('surface_selected')}; color: {c('text_muted')}; }}

QPushButton#ghost {{
    background: {c('panel_bg')}; border: 1px solid {c('divider')};
    color: {c('text_secondary')}; padding: 0 16px;
    min-height: {s('button_height')}px; border-radius: 9px;
    font-size: {f('input')}pt;
}}
QPushButton#ghost:hover {{
    background: {c('surface_hover')}; border-color: {c('divider_strong')}; color: {c('text')};
}}
QPushButton#ghost:pressed {{ background: {c('surface_selected')}; }}
QPushButton#ghost:disabled {{
    color: {c('text_muted')}; border-color: {c('divider')}; background: transparent;
}}

QPlainTextEdit, QTextEdit {{
    background: {c('editor_bg')}; border: none;
    font-size: {f('body')}pt; color: {c('text')};
    selection-background-color: {c('selection_bg')};
    selection-color: {c('text')};
}}
QPlainTextEdit:read-only, QTextEdit:read-only {{ background: {c('editor_bg')}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c('panel_bg')}; border: 1px solid {c('divider')};
    border-radius: 9px; padding: 7px 10px; min-height: 22px;
    font-size: {f('input')}pt; color: {c('text')};
    selection-background-color: {c('selection_bg')}; selection-color: {c('text')};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {c('divider_strong')};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {c('focus_ring')};
}}
QLineEdit:disabled {{ color: {c('text_muted')}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {c('panel_bg')}; border: 1px solid {c('divider')};
    border-radius: 9px; padding: 6px;
    selection-background-color: {c('selection_bg')}; selection-color: {c('text')};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent;
}}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {c('surface_selected')}; }}

#dialogCard {{
    background: {c('card_bg')}; border: 1px solid {c('divider')};
    border-radius: {s('card_radius')}px;
}}
#dialogTitle {{ font-size: {f('title')}pt; font-weight: 700; }}
#sectionTitle {{
    font-size: {f('meta')}pt; font-weight: 700; color: {c('text_muted')};
}}
#fieldLabel {{ font-size: {f('meta')}pt; color: {c('text_secondary')}; }}
#dialogError {{ font-size: {f('input')}pt; color: {c('gate_block')}; }}

#band {{
    background: {c('band_bg')};
    border-top: 1px solid {c('divider')};
}}
#busyDot {{ background: {c('ink_bg')}; border-radius: 4px; }}
#banner {{
    background: {c('banner_bg')}; border: 1px solid {c('divider')};
    border-left: 3px solid {c('gate_warn')};
    border-radius: 10px; padding: 10px 14px;
    font-size: {f('input')}pt; color: {c('text_secondary')};
}}
#metricNum {{ font-size: {f('number')}pt; font-weight: 600; color: {c('text')}; }}
#metricLab {{ font-size: {f('caption')}pt; color: {c('text_muted')}; }}
#dot {{ border-radius: 4px; }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {c('divider_strong')}; border-radius: 4px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: {c('text_muted')}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QToolTip {{
    background: {c('tooltip_bg')}; color: {c('tooltip_fg')};
    border: none; padding: 6px 9px; border-radius: 6px;
    font-size: {f('meta')}pt;
}}
"""
