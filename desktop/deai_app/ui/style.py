"""style — 把 theme.json 的 token 翻成一份 QSS。

界面代码里不出现色值与字号：控件只写 objectName，样式集中在这里。
滚动条也在这里重画：Qt 默认的凹陷 groove 是"老对话框感"的主要来源。
"""
from __future__ import annotations

from deai_app.ui.theme import Theme, load_theme

__all__ = ["stylesheet", "unpolish_repolish"]


def unpolish_repolish(widget) -> None:
    """改 objectName 之后必须重抛光，否则 QSS 仍按旧名字生效。"""
    style_object = widget.style()
    style_object.unpolish(widget)
    style_object.polish(widget)
    widget.update()


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
#brand {{ font-size: {f('emphasis')}pt; font-weight: 700; color: {c('text')}; }}
QPushButton#tab, QPushButton#tabOn {{
    border: none; background: transparent; padding: 6px 14px;
    font-size: {f('body')}pt; color: {c('text_muted')};
}}
QPushButton#tab:hover {{ color: {c('text_secondary')}; }}
QPushButton#tabOn {{
    font-weight: 700; color: {c('text')};
    border-bottom: 2px solid {c('ink_bg')};
}}
QToolButton {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('body')}pt; border-radius: 6px;
}}
QToolButton:hover {{ background: {c('surface_hover')}; color: {c('text')}; }}
QToolButton#close:hover {{ background: {c('gate_block')}; color: {c('ink_fg')}; }}
#pane {{
    background: {c('card_bg')};
    border: 1px solid {c('divider')};
    border-radius: {s('pane_radius')}px;
}}
#paneTitle {{ font-size: {f('emphasis')}pt; font-weight: 700; }}
#meta, #hint {{ font-size: {f('meta')}pt; color: {c('text_muted')}; }}
QPushButton#text {{
    border: none; background: transparent; color: {c('text_secondary')};
    font-size: {f('meta')}pt; padding: 6px 10px; border-radius: 6px;
}}
QPushButton#text:hover {{ background: {c('surface_hover')}; color: {c('text')}; }}
QPushButton#ink {{
    background: {c('ink_bg')}; color: {c('ink_fg')}; border: none;
    border-radius: 7px; padding: 8px 20px;
    font-size: {f('body')}pt; font-weight: 600;
}}
QPushButton#ink:hover {{ background: {c('ink_hover')}; }}
QPushButton#ink:disabled {{ background: {c('surface_hover')}; color: {c('text_muted')}; }}
QPushButton#ghost {{
    background: transparent; border: none; color: {c('text_secondary')};
    padding: 8px 14px; border-radius: 7px; font-size: {f('body')}pt;
}}
QPushButton#ghost:hover {{ background: {c('surface_selected')}; color: {c('text')}; }}
QPlainTextEdit, QTextEdit {{
    background: {c('card_bg')}; border: none;
    font-size: {f('body')}pt; color: {c('text')};
    selection-background-color: {c('surface_selected')};
    selection-color: {c('text')};
}}
QPlainTextEdit:read-only, QTextEdit:read-only {{ background: {c('card_bg')}; }}
#band {{ background: {c('band_bg')}; border-top: 1px solid {c('divider')}; }}
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
"""
