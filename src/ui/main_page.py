import logging
import os

from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QCheckBox
)

from .hotkey_line_edit import HotkeyLineEdit

logger = logging.getLogger(__name__)


class MainPageWidget(QWidget):
    """Main settings page: output directory and hotkeys."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        dir_group = QGroupBox("Папка для сохранения записей")
        dir_layout = QHBoxLayout()

        self.dir_input = QLineEdit()
        self.dir_input.setReadOnly(True)
        self.dir_input.setText(self.sm.get("output_dir", ""))
        dir_layout.addWidget(self.dir_input)

        btn_browse = QPushButton("Обзор...")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self.browse_output_dir)
        dir_layout.addWidget(btn_browse)

        dir_group.setLayout(dir_layout)
        layout.addRow(dir_group)

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

    def browse_output_dir(self):
        current = self.dir_input.text()
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", current)
        if directory:
            self.dir_input.setText(directory)

    def get_settings(self):
        return {
            "output_dir": self.dir_input.text(),
            "hotkeys": {
                "toggle_recording": self.hotkey_toggle.text(),
            },
            "show_notifications": self.notify_checkbox.isChecked(),
        }
