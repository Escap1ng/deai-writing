"""settings — 接口与改写设置：无边框卡片对话框，保存到 %APPDATA%\\deai\\。

供应商可增删，密钥只写本机配置文件；保存时只校验当前选中的一套，
其余备用配置允许暂时没有密钥，避免"填一个必须填满全部"。
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from deai_app.core import config, prompt
from deai_app.ui.theme import Theme

DIALOG_WIDTH = 580


class _DragBar(QWidget):
    """无边框对话框的拖动区：只接管标题行，控件点击不受影响。"""

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


class SettingsDialog(QDialog):
    def __init__(self, theme: Theme, providers: list[config.Provider],
                 settings: config.Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowTitle("接口与改写设置")
        self.theme = theme
        self.providers = [replace(provider) for provider in providers]
        if not self.providers:
            self.providers = [config.Provider(name="新供应商", base_url="", model="")]
        self._settings = settings
        self._current = 0
        self.providers_out: list[config.Provider] = []
        self.settings_out: config.Settings | None = None
        self._placed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame(); card.setObjectName("dialogCard")
        shadow = QGraphicsDropShadowEffect(blurRadius=30, xOffset=0, yOffset=8)
        shadow.setColor(QColor(20, 20, 22, 52))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        column = QVBoxLayout(card)
        column.setContentsMargins(22, 16, 22, 16)
        column.setSpacing(12)

        column.addWidget(self._build_title())
        column.addWidget(self._section("供应商"))
        column.addWidget(self._build_provider_row())
        column.addLayout(self._build_provider_form())
        column.addWidget(self._section("改写"))
        column.addLayout(self._build_rewrite_form())
        self.preset.setCurrentText(settings.preset)
        self.intensity.setCurrentText(settings.intensity)
        self.rounds.setValue(max(1, min(settings.max_rounds, 4)))

        self.error = QLabel(""); self.error.setObjectName("dialogError")
        self.error.setWordWrap(True); self.error.hide()
        column.addWidget(self.error)
        column.addStretch()
        column.addLayout(self._build_actions())

        self.setFixedWidth(DIALOG_WIDTH)
        self.adjustSize()
        active = settings.active_provider
        index = next((i for i, p in enumerate(self.providers) if p.name == active), 0)
        self._rebuild_combo(index)
        self._populate(index)

    # ---------- 结构 ----------

    def _build_title(self) -> QWidget:
        bar = _DragBar()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("接口与改写"); title.setObjectName("dialogTitle")
        row.addWidget(title); row.addStretch()
        close = QPushButton("关闭"); close.setObjectName("text")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        return bar

    def _section(self, text: str) -> QLabel:
        label = QLabel(text); label.setObjectName("sectionTitle")
        return label

    def _build_provider_row(self) -> QWidget:
        row = QWidget(); layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        self.combo = QComboBox(); self.combo.setMinimumWidth(320)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo, 1)
        add = QPushButton("新增"); add.setObjectName("text")
        add.setCursor(Qt.CursorShape.PointingHandCursor); add.clicked.connect(self._on_add)
        delete = QPushButton("删除"); delete.setObjectName("text")
        delete.setCursor(Qt.CursorShape.PointingHandCursor); delete.clicked.connect(self._on_delete)
        layout.addWidget(add); layout.addWidget(delete)
        return row

    def _build_provider_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setHorizontalSpacing(14); form.setVerticalSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.base_edit = QLineEdit(); self.base_edit.setPlaceholderText("https://api.example.com/v1")
        self.model_edit = QLineEdit(); self.model_edit.setPlaceholderText("如 deepseek-chat")
        self.key_edit = QLineEdit(); self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("本地服务可留空")
        key_row = QWidget(); key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0); key_layout.setSpacing(6)
        key_layout.addWidget(self.key_edit, 1)
        self.key_toggle = QPushButton("显示"); self.key_toggle.setObjectName("text")
        self.key_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key_toggle.clicked.connect(self._toggle_key)
        key_layout.addWidget(self.key_toggle)

        self.temp = QDoubleSpinBox(); self.temp.setRange(0.0, 2.0)
        self.temp.setSingleStep(0.1); self.temp.setDecimals(1)
        self.temp.setValue(0.3)
        self.timeout = QSpinBox(); self.timeout.setRange(10, 600)
        self.timeout.setValue(120); self.timeout.setSuffix(" 秒")
        limits = QWidget(); limits_layout = QHBoxLayout(limits)
        limits_layout.setContentsMargins(0, 0, 0, 0); limits_layout.setSpacing(8)
        limits_layout.addWidget(self.temp, 1); limits_layout.addWidget(self.timeout, 1)

        self._add_row(form, "名称", self.name_edit)
        self._add_row(form, "接口地址", self.base_edit)
        self._add_row(form, "模型", self.model_edit)
        self._add_row(form, "密钥", key_row)
        self._add_row(form, "温度与超时", limits)

        hint = QLabel("密钥只写入本机配置目录的 providers.json")
        hint.setObjectName("hint"); hint.setWordWrap(True)
        hint.setToolTip(str(config.config_dir() / config.PROVIDERS_FILE))
        form.addRow("", hint)
        return form

    def _add_row(self, form: QFormLayout, text: str, field: QWidget) -> None:
        label = QLabel(text); label.setObjectName("fieldLabel")
        form.addRow(label, field)

    def _build_rewrite_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setHorizontalSpacing(14); form.setVerticalSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.preset = QComboBox(); self.preset.addItems(prompt.PRESETS)
        self.intensity = QComboBox(); self.intensity.addItems(prompt.INTENSITIES)
        self.rounds = QSpinBox(); self.rounds.setRange(1, 4); self.rounds.setValue(2)
        self.rounds.setSuffix(" 轮")
        self._add_row(form, "预设", self.preset)
        self._add_row(form, "强度", self.intensity)
        self._add_row(form, "复检轮次", self.rounds)
        return form

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)
        row.addStretch()
        cancel = QPushButton("取消"); cancel.setObjectName("ghost")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor); cancel.clicked.connect(self.reject)
        save = QPushButton("保存并应用"); save.setObjectName("ink")
        save.setCursor(Qt.CursorShape.PointingHandCursor); save.clicked.connect(self._save)
        save.setDefault(True); cancel.setAutoDefault(False)
        row.addWidget(cancel); row.addWidget(save)
        return row

    # ---------- 数据 ----------

    def _rebuild_combo(self, index: int) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems([provider.name for provider in self.providers])
        self.combo.setCurrentIndex(max(0, min(index, len(self.providers) - 1)))
        self.combo.blockSignals(False)
        self._current = self.combo.currentIndex()

    def _populate(self, index: int) -> None:
        provider = self.providers[index]
        self.name_edit.setText(provider.name)
        self.base_edit.setText(provider.base_url)
        self.model_edit.setText(provider.model)
        self.key_edit.setText(provider.api_key)
        self.temp.setValue(provider.temperature)
        self.timeout.setValue(provider.timeout)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_toggle.setText("显示")
        self.error.hide()

    def _commit_current(self) -> None:
        index = self._current
        if not 0 <= index < len(self.providers):
            return
        provider = self.providers[index]
        name = self.name_edit.text().strip() or self.model_edit.text().strip() or f"供应商 {index + 1}"
        self.providers[index] = replace(
            provider,
            name=name,
            base_url=self.base_edit.text().strip(),
            model=self.model_edit.text().strip(),
            api_key=self.key_edit.text().strip(),
            temperature=round(self.temp.value(), 1),
            timeout=int(self.timeout.value()),
        )
        self.combo.blockSignals(True)
        self.combo.setItemText(index, name)
        self.combo.blockSignals(False)

    def _on_combo_changed(self, index: int) -> None:
        if index == self._current or index < 0:
            return
        self._commit_current()
        self._current = index
        self._populate(index)

    def _on_add(self) -> None:
        self._commit_current()
        self.providers.append(config.Provider(
            name=f"供应商 {len(self.providers) + 1}", base_url="", model=""))
        self._rebuild_combo(len(self.providers) - 1)
        self._populate(len(self.providers) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _on_delete(self) -> None:
        if len(self.providers) <= 1:
            self._show_error("至少保留一个供应商")
            return
        self._commit_current()
        del self.providers[self._current]
        self._rebuild_combo(min(self._current, len(self.providers) - 1))
        self._populate(self._current)

    def _toggle_key(self) -> None:
        showing = self.key_edit.echoMode() == QLineEdit.EchoMode.Normal
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Password if showing else QLineEdit.EchoMode.Normal)
        self.key_toggle.setText("显示" if showing else "隐藏")

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()

    def set_message(self, text: str) -> None:
        if text:
            self._show_error(text)

    def _save(self) -> None:
        self._commit_current()
        names = [provider.name for provider in self.providers]
        if len(set(names)) != len(names):
            self._show_error("供应商名称不能重复")
            return
        active = self.providers[self._current]
        try:
            active.validate()
            config.save_providers(self.providers)
            settings = config.Settings(
                active_provider=active.name,
                preset=self.preset.currentText(),
                intensity=self.intensity.currentText(),
                max_rounds=int(self.rounds.value()),
                lang=self._settings.lang,
                auto_deai_after_translate=self._settings.auto_deai_after_translate,
            )
            config.save_settings(settings)
        except (config.ConfigError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.providers_out = list(self.providers)
        self.settings_out = settings
        self.accept()

    # ---------- 窗口 ----------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        if not self._placed and self.parentWidget() is not None:
            parent = self.parentWidget()
            self.move(parent.frameGeometry().center() - self.rect().center())
            self._placed = True
