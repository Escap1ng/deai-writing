"""style — 把 theme.json 的 token 翻成一份 QSS。

界面代码只引用 token 或 objectName，不出现裸色值与裸字号。
滚动条也在这里重画：Qt 默认的凹陷 groove 是"老对话框感"的主要来源。
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
    background: {c('card_bg')};
    border: 1px solid {c('divider')};
    border-radius: {s('card_radius')}px;
}}
#brand {{ font-size: {f('title')}pt; font-weight: 700; color: {c('text')}; }}
QToolButton {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('body')}pt; border-radius: 6px;
}}
#pane {{
    background: {c('panel_bg')};
    border: 1px solid {c('divider')};
    border-radius: {s('pane_radius')}px;
}}
#paneTitle {{ font-size: {f('emphasis')}pt; font-weight: 700; }}
#pane[dragOver="true"] {{ border: 2px solid {c('focus_ring')}; }}
#meta, #hint {{ font-size: {f('meta')}pt; color: {c('text_muted')}; }}
QPushButton#text {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('meta')}pt; padding: 6px 10px; border-radius: 6px;
}}
QPushButton#text:hover {{ background: {c('surface_hover')}; color: {c('text')}; }}
QPushButton#text:disabled {{ color: {c('text_muted')}; }}
QPushButton#ink {{
    background: {c('ink_bg')}; color: {c('ink_fg')}; border: none;
    border-radius: 8px; padding: 0 22px; min-height: {s('button_height')}px;
    font-size: {f('body')}pt; font-weight: 600;
}}
QPushButton#ink:hover {{ background: {c('ink_hover')}; }}
QPushButton#ink:disabled {{ background: {c('surface_selected')}; color: {c('text_muted')}; }}
QPushButton#ghost {{
    background: transparent; border: 1px solid {c('divider')}; color: {c('text_secondary')};
    padding: 0 14px; min-height: {s('button_height')}px; border-radius: 8px;
    font-size: {f('body')}pt;
}}
QPushButton#ghost:hover {{ background: {c('surface_hover')}; border-color: {c('divider_strong')}; color: {c('text')}; }}
QPushButton#ghost:disabled {{ color: {c('text_muted')}; border-color: {c('divider')}; }}
QPlainTextEdit, QTextEdit {{
    background: {c('editor_bg')}; border: none;
    font-size: {f('body')}pt; color: {c('text')};
    selection-background-color: {c('selection_bg')};
    selection-color: {c('text')};
}}
QPlainTextEdit:read-only, QTextEdit:read-only {{ background: {c('editor_bg')}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c('editor_bg')}; border: 1px solid {c('divider')};
    border-radius: 8px; padding: 6px 10px; min-height: 20px;
    font-size: {f('meta')}pt; color: {c('text')};
    selection-background-color: {c('selection_bg')}; selection-color: {c('text')};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {c('focus_ring')};
}}
QLineEdit:disabled {{ color: {c('text_muted')}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c('card_bg')}; border: 1px solid {c('divider')};
    border-radius: 8px; padding: 4px;
    selection-background-color: {c('selection_bg')}; selection-color: {c('text')};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px; border: none; background: transparent;
}}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {c('surface_hover')}; }}
#dialogCard {{
    background: {c('card_bg')}; border: 1px solid {c('divider')};
    border-radius: {s('card_radius')}px;
}}
#dialogTitle {{ font-size: {f('title')}pt; font-weight: 700; }}
#sectionTitle {{ font-size: {f('meta')}pt; font-weight: 700; color: {c('text_muted')}; }}
#fieldLabel {{ font-size: {f('meta')}pt; color: {c('text_secondary')}; }}
#dialogError {{ font-size: {f('meta')}pt; color: {c('gate_block')}; }}
#band {{ background: {c('band_bg')}; border-top: 1px solid {c('divider')}; }}
#busyDot {{ background: {c('ink_bg')}; border-radius: 5px; }}
#banner {{
    background: {c('band_bg')}; border: 1px solid {c('divider')};
    border-left: 3px solid {c('gate_warn')};
    border-radius: {s('pane_radius')}px; padding: 8px 12px;
    font-size: {f('meta')}pt; color: {c('text_secondary')};
}}
#metricNum {{ font-size: {f('number')}pt; font-weight: 700; color: {c('text')}; }}
#metricLab {{ font-size: {f('caption')}pt; color: {c('text_muted')}; }}
#dot {{ border-radius: 4px; }}
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 6px 3px 6px 0;
}}
QScrollBar::handle:vertical {{
    background: {c('divider_strong')}; border-radius: 3px; min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: {c('text_muted')}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
QToolTip {{
    background: {c('card_bg')}; color: {c('text')};
    border: 1px solid {c('divider_strong')}; padding: 4px 8px;
}}
"""
