import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget
)

from .main_page import MainPageWidget
from .settings_page import SettingsPageWidget
from .file_page import FilePageWidget

logger = logging.getLogger(__name__)

RESOLUTION_PRESETS = {
    "480p":  {"label": "480p (854x480)",   "width": 854,  "height": 480},
    "720p":  {"label": "720p (1280x720)",  "width": 1280, "height": 720},
    "1080p": {"label": "1080p (1920x1080)", "width": 1920, "height": 1080},
}


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        self.main_page = MainPageWidget(self.sm)
        self.file_page = FilePageWidget(self.sm)
        self.settings_page = SettingsPageWidget(self.sm)

        tabs.addTab(self.main_page, "Главная")
        tabs.addTab(self.file_page, "Путь и имя файла")
        tabs.addTab(self.settings_page, "Качество")

        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Сохранить")
        btn_save.clicked.connect(self.on_save)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def on_save(self):
        settings = {}
        settings.update(self.main_page.get_settings())
        settings.update(self.file_page.get_settings())
        settings.update(self.settings_page.get_settings())
        self.sm.set_many(settings)
        self.settings_saved.emit()
        self.accept()

    def get_settings(self):
        settings = {}
        settings.update(self.main_page.get_settings())
        settings.update(self.file_page.get_settings())
        settings.update(self.settings_page.get_settings())
        return settings
