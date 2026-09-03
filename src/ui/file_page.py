import logging
import os
import time

from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox
)

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = "{date:YYYYMMDD}-{time:HHMMSS}"

TOKEN_HELP = (
    "Доступные токены:\n"
    "  {date:Формат}  — дата (strftime)\n"
    "  {time:Формат}  — время (strftime)\n"
    "  {n}            — номер (авто)\n"
    "  {n:ШИРИНА}     — номер с ведущими нулями\n"
    "\n"
    "Примеры:\n"
    "  {date:YYYYMMDD}-{time:HHMMSS}  →  20260903-171530\n"
    "  {date:YYYY-MM-DD}_{time:HH-mm-ss}  →  2026-09-03_17-15-30\n"
    "  rec_{n:03}  →  rec_001, rec_002, ...\n"
    "  lecture_{date:YYYYMMDD}  →  lecture_20260903"
)

QUICK_TOKENS = [
    ("Дата YYYYMMDD", "{date:YYYYMMDD}"),
    ("Дата YYYY-MM-DD", "{date:YYYY-MM-DD}"),
    ("Дата DD.MM.YYYY", "{date:%d.%m.%Y}"),
    ("Время HHMMSS", "{time:HHMMSS}"),
    ("Время HH-mm-ss", "{time:%H-%M-%S}"),
    ("Номер", "{n}"),
    ("Номер 001", "{n:03}"),
    ("Номер 0001", "{n:04}"),
]


def parse_filename_pattern(pattern, counter):
    now = time.localtime()
    result = pattern

    import re

    def replace_date(m):
        fmt = m.group(1)
        py_fmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
        return time.strftime(py_fmt, now)

    def replace_time(m):
        fmt = m.group(1)
        py_fmt = fmt.replace("HH", "%H").replace("mm", "%M").replace("ss", "%S")
        return time.strftime(py_fmt, now)

    def replace_n(m):
        width = m.group(1)
        if width:
            return str(counter).zfill(int(width))
        return str(counter)

    result = re.sub(r"\{date:([^}]+)\}", replace_date, result)
    result = re.sub(r"\{time:([^}]+)\}", replace_time, result)
    result = re.sub(r"\{n:(\d+)\}", replace_n, result)
    result = re.sub(r"\{n\}", replace_n, result)

    return result


class FilePageWidget(QWidget):
    """Path & filename settings page."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self._counter = 0
        self.init_ui()
        self._update_preview()

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

        pattern_group = QGroupBox("Шаблон имени файла")
        pattern_layout = QVBoxLayout()

        pattern_row = QHBoxLayout()
        pattern_row.addWidget(QLabel("Шаблон:"))
        self.pattern_input = QLineEdit()
        self.pattern_input.setText(self.sm.get("filename_pattern", DEFAULT_PATTERN))
        self.pattern_input.textChanged.connect(self._update_preview)
        pattern_row.addWidget(self.pattern_input)
        pattern_layout.addLayout(pattern_row)

        tokens_row = QHBoxLayout()
        tokens_row.addWidget(QLabel("Вставить токен:"))
        self.token_combo = QComboBox()
        for label, token in QUICK_TOKENS:
            self.token_combo.addItem(label, token)
        tokens_row.addWidget(self.token_combo)

        btn_insert = QPushButton("+")
        btn_insert.setFixedWidth(30)
        btn_insert.setToolTip("Вставить токен в позицию курсора")
        btn_insert.clicked.connect(self._insert_token)
        tokens_row.addWidget(btn_insert)

        btn_reset_pattern = QPushButton("Сброс")
        btn_reset_pattern.setFixedWidth(60)
        btn_reset_pattern.clicked.connect(lambda: self.pattern_input.setText(DEFAULT_PATTERN))
        tokens_row.addWidget(btn_reset_pattern)

        tokens_row.addStretch()
        pattern_layout.addLayout(tokens_row)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet("color: #888; font-size: 11px;")
        pattern_layout.addWidget(self.preview_label)

        help_label = QLabel(TOKEN_HELP)
        help_label.setStyleSheet("color: #666; font-size: 10px;")
        help_label.setWordWrap(True)
        pattern_layout.addWidget(help_label)

        pattern_group.setLayout(pattern_layout)
        layout.addRow(pattern_group)

    def _insert_token(self):
        token = self.token_combo.currentData()
        cursor_pos = self.pattern_input.cursorPosition()
        text = self.pattern_input.text()
        new_text = text[:cursor_pos] + token + text[cursor_pos:]
        self.pattern_input.setText(new_text)
        self.pattern_input.setCursorPosition(cursor_pos + len(token))

    def _update_preview(self):
        pattern = self.pattern_input.text() or DEFAULT_PATTERN
        try:
            preview = parse_filename_pattern(pattern, 1)
            self.preview_label.setText(f"Пример: {preview}.mp4")
        except Exception:
            self.preview_label.setText("Некорректный шаблон")

    def browse_output_dir(self):
        current = self.dir_input.text()
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", current)
        if directory:
            self.dir_input.setText(directory)

    def get_settings(self):
        return {
            "output_dir": self.dir_input.text(),
            "filename_pattern": self.pattern_input.text() or DEFAULT_PATTERN,
        }
