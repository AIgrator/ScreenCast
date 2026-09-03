import logging

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QCheckBox, QColorDialog
)

from .hotkey_line_edit import HotkeyLineEdit

logger = logging.getLogger(__name__)

DEFAULT_COLORS = {
    "idle": [50, 150, 250],
    "recording": [220, 50, 50],
    "saving": [230, 180, 30],
}

COLOR_LABELS = {
    "idle": "Ожидание",
    "recording": "Запись",
    "saving": "Сохранение",
}


class MainPageWidget(QWidget):
    """Main settings page: hotkeys, notifications, tray colors."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        hotkey_group = QGroupBox("Горячие клавиши")
        hotkey_layout = QFormLayout()

        hotkeys = self.sm.get("hotkeys", {})
        self.hotkey_toggle = HotkeyLineEdit(hotkeys.get("toggle_recording", "Ctrl+Shift+R"))
        hotkey_layout.addRow("Старт/Стоп записи:", self.hotkey_toggle)

        hotkey_group.setLayout(hotkey_layout)
        layout.addRow(hotkey_group)

        notify_group = QGroupBox("Уведомления")
        notify_layout = QVBoxLayout()

        self.notify_checkbox = QCheckBox("Показывать всплывающие уведомления в трее")
        self.notify_checkbox.setChecked(self.sm.get("show_notifications", True))
        notify_layout.addWidget(self.notify_checkbox)

        notify_group.setLayout(notify_layout)
        layout.addRow(notify_group)

        colors_group = QGroupBox("Цвета иконки в трее")
        colors_layout = QHBoxLayout()

        tray_colors = self.sm.get("tray_colors", DEFAULT_COLORS)
        self._color_buttons = {}

        for key in ("idle", "recording", "saving"):
            rgb = tray_colors.get(key, DEFAULT_COLORS[key])
            btn = QPushButton(COLOR_LABELS[key])
            btn.setFixedHeight(30)
            btn.setStyleSheet(f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); color: white; border: 1px solid #888;")
            btn.clicked.connect(lambda checked, k=key, b=btn: self._pick_color(k, b))
            self._color_buttons[key] = btn
            colors_layout.addWidget(btn)

        colors_group.setLayout(colors_layout)
        layout.addRow(colors_group)

    def _pick_color(self, key, btn):
        tray_colors = self.sm.get("tray_colors", DEFAULT_COLORS).copy()
        current_rgb = tray_colors.get(key, DEFAULT_COLORS[key])
        current_color = QColor(current_rgb[0], current_rgb[1], current_rgb[2])

        color = QColorDialog.getColor(current_color, self, f"Выберите цвет: {COLOR_LABELS[key]}")
        if color.isValid():
            rgb = [color.red(), color.green(), color.blue()]
            tray_colors[key] = rgb
            self.sm.set("tray_colors", tray_colors)
            btn.setStyleSheet(
                f"background-color: {color.name()}; color: white; border: 1px solid #888;"
            )

    def get_settings(self):
        return {
            "hotkeys": {
                "toggle_recording": self.hotkey_toggle.text(),
            },
            "show_notifications": self.notify_checkbox.isChecked(),
        }
