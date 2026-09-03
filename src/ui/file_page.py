import glob
import logging
import os
import re
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox,
    QToolButton, QApplication
)

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = "%Y%m%d-%H%M%S"

TOKEN_HELP = (
    "Формат имени файла (strftime + {n}):\n\n"
    "  %Y  — год (2026)\n"
    "  %m  — месяц (01–12)\n"
    "  %d  — день (01–31)\n"
    "  %H  — час (00–23)\n"
    "  %M  — минута (00–59)\n"
    "  %S  — секунда (00–59)\n"
    "  %a  — день недели (Mon, Tue...)\n"
    "  %b  — месяц (Jan, Feb...)\n\n"
    "  {n}     — номер (авто: 1, 2, 3...)\n"
    "  {n:03}  — номер с ведущими нулями (001, 002...)\n"
    "  {n:04}  — (0001, 0002...)\n\n"
    "Примеры:\n"
    "  %Y%m%d-%H%M%S      →  20260903-171530\n"
    "  %Y-%m-%d_%H-%M-%S  →  2026-09-03_17-15-30\n"
    "  rec_{n:03}          →  rec_001, rec_002...\n"
    "  lecture_%Y%m%d      →  lecture_20260903\n"
    "  %b %d %Y {n:02}     →  Sep 03 2026 01"
)

QUICK_TOKENS = [
    ("%Y%m%d", "%Y%m%d"),
    ("%Y-%m-%d", "%Y-%m-%d"),
    ("%d.%m.%Y", "%d.%m.%Y"),
    ("%H%M%S", "%H%M%S"),
    ("%H-%M-%S", "%H-%M-%S"),
    ("%a, %d %b %Y", "%a, %d %b %Y"),
    ("{n}", "{n}"),
    ("{n:03}", "{n:03}"),
    ("{n:04}", "{n:04}"),
]


class CustomTooltip(QWidget):
    _instance = None

    def __init__(self, text, parent=None):
        super().__init__(None, Qt.WindowType.ToolTip)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._text = text
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_at(self, pos):
        label = QLabel(self._text)
        label.setStyleSheet(
            "QLabel { background: #2a2a2a; color: #e0e0e0; padding: 12px; "
            "border: 1px solid #555; border-radius: 4px; font-size: 12px; }"
        )
        label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        self.adjustSize()

        screen = QApplication.screenAt(pos)
        if screen:
            sr = screen.availableGeometry()
            w = self.width()
            h = self.height()
            x = pos.x() - w - 10
            y = pos.y() - h // 2
            if x < sr.left():
                x = pos.x() + 20
            if y < sr.top():
                y = sr.top()
            if y + h > sr.bottom():
                y = sr.bottom() - h
            self.move(x, y)

        self.show()
        self._timer.start(15000)

    def leaveEvent(self, event):
        self.hide()


class HelpButton(QToolButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText("?")
        self.setFixedSize(22, 22)
        self._tooltip_text = text
        self._tooltip = None
        self.setStyleSheet("QToolButton { font-weight: bold; border: 1px solid #888; border-radius: 10px; }")

    def enterEvent(self, event):
        pos = QCursor.pos()
        self._tooltip = CustomTooltip(self._tooltip_text, self)
        self._tooltip.show_at(pos)

    def leaveEvent(self, event):
        if self._tooltip:
            self._tooltip.hide()


def _next_counter(output_dir, pattern):
    existing = glob.glob(os.path.join(output_dir, "*.mp4"))
    max_n = 0
    for fp in existing:
        basename = os.path.splitext(os.path.basename(fp))[0]
        m = re.search(r"(\d+)$", basename)
        if m:
            try:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return max_n + 1


def parse_filename_pattern(pattern, output_dir=None):
    now = time.localtime()
    result = pattern

    counter = 1
    if output_dir and os.path.isdir(output_dir):
        counter = _next_counter(output_dir, pattern)

    def _replace_n(m):
        width = m.group(1)
        if width:
            return str(counter).zfill(int(width))
        return str(counter)

    result = re.sub(r"\{n:(\d+)\}", _replace_n, result)
    result = re.sub(r"\{n\}", _replace_n, result)

    result = time.strftime(result, now)

    return result


class FilePageWidget(QWidget):
    """Path & filename settings page."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
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
        self.dir_input.textChanged.connect(self._update_preview)
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

        btn_help = HelpButton(TOKEN_HELP)
        pattern_row.addWidget(btn_help)

        pattern_layout.addLayout(pattern_row)

        tokens_row = QHBoxLayout()
        tokens_row.addWidget(QLabel("Вставить:"))
        self.token_combo = QComboBox()
        for label, token in QUICK_TOKENS:
            self.token_combo.addItem(label, token)
        tokens_row.addWidget(self.token_combo)

        btn_insert = QPushButton("+")
        btn_insert.setFixedWidth(30)
        btn_insert.setToolTip("Вставить в позицию курсора")
        btn_insert.clicked.connect(self._insert_token)
        tokens_row.addWidget(btn_insert)

        btn_reset = QPushButton("Сброс")
        btn_reset.setFixedWidth(60)
        btn_reset.clicked.connect(lambda: self.pattern_input.setText(DEFAULT_PATTERN))
        tokens_row.addWidget(btn_reset)

        tokens_row.addStretch()
        pattern_layout.addLayout(tokens_row)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet("color: #888; font-size: 11px;")
        pattern_layout.addWidget(self.preview_label)

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
        output_dir = self.dir_input.text()
        try:
            preview = parse_filename_pattern(pattern, output_dir)
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
