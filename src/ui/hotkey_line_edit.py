import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QToolButton, QVBoxLayout
)

from src import translation_manager as tr

logger = logging.getLogger(__name__)


class HotkeyLineEdit(QLineEdit):
    """Hotkey input field with a button for manual selection via dialog."""

    def __init__(self, hotkey="", parent=None):
        super().__init__(parent)
        self.hotkey_sequence = QKeySequence()
        self.set_hotkey(hotkey)
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._is_recording = False

        self.button = QToolButton(self)
        self.button.setText("\u2026")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip(tr.t("hotkey.choose_tooltip"))
        self.button.setFixedWidth(22)
        self.button.clicked.connect(self.open_hotkey_dialog)
        self.setTextMargins(0, 0, self.button.width(), 0)
        self.button.move(self.rect().right() - self.button.width(), 0)
        self.button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.button.move(self.rect().right() - self.button.width(), 0)

    def set_hotkey(self, sequence_str):
        if not sequence_str:
            self.hotkey_sequence = QKeySequence()
            self.setText("")
            return
        if 'Win' in sequence_str or 'Meta' in sequence_str:
            self.setText(sequence_str)
            self.hotkey_sequence = QKeySequence(sequence_str)
        else:
            self.hotkey_sequence = QKeySequence(sequence_str)
            self.setText(self.hotkey_sequence.toString(QKeySequence.SequenceFormat.NativeText))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._is_recording = True
        self.setText(tr.t("hotkey.press_combination"))
        self.setStyleSheet("QLineEdit { background-color: #1a1a2e; color: #e94560; }")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._is_recording = False
        self.setText(self.hotkey_sequence.toString(QKeySequence.SequenceFormat.NativeText))
        self.setStyleSheet("")

    def keyPressEvent(self, event):
        if not self._is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        special_keys = {
            Qt.Key.Key_Delete: 'Delete', Qt.Key.Key_Return: 'Enter', Qt.Key.Key_Enter: 'Enter',
            Qt.Key.Key_Insert: 'Insert', Qt.Key.Key_Tab: 'Tab', Qt.Key.Key_Escape: 'Esc',
            Qt.Key.Key_Backspace: 'Backspace', Qt.Key.Key_Home: 'Home', Qt.Key.Key_End: 'End',
            Qt.Key.Key_PageUp: 'PageUp', Qt.Key.Key_PageDown: 'PageDown',
            Qt.Key.Key_Print: 'PrintScreen', Qt.Key.Key_ScrollLock: 'ScrollLock',
            Qt.Key.Key_Pause: 'Pause', Qt.Key.Key_CapsLock: 'CapsLock',
            Qt.Key.Key_NumLock: 'NumLock', Qt.Key.Key_Space: 'Space',
            Qt.Key.Key_F1: 'F1', Qt.Key.Key_F2: 'F2', Qt.Key.Key_F3: 'F3', Qt.Key.Key_F4: 'F4',
            Qt.Key.Key_F5: 'F5', Qt.Key.Key_F6: 'F6', Qt.Key.Key_F7: 'F7', Qt.Key.Key_F8: 'F8',
            Qt.Key.Key_F9: 'F9', Qt.Key.Key_F10: 'F10', Qt.Key.Key_F11: 'F11', Qt.Key.Key_F12: 'F12',
        }

        if key == Qt.Key.Key_Escape:
            self.hotkey_sequence = QKeySequence()
            self.setText("")
            self.clearFocus()
            return

        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta,
                    Qt.Key.Key_Super_L, Qt.Key.Key_Super_R):
            return

        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append('Ctrl')
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append('Alt')
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append('Shift')
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append('Win')

        if key in special_keys:
            parts.append(special_keys[key])
        else:
            seq = QKeySequence(key | int(modifiers))
            text = seq.toString(QKeySequence.SequenceFormat.NativeText)
            if not text:
                self.clearFocus()
                return
            parts.append(text)

        hotkey_str = "+".join(parts)
        self.hotkey_sequence = QKeySequence(hotkey_str)
        self.setText(hotkey_str)
        self.clearFocus()

    def open_hotkey_dialog(self):
        dlg = HotkeyDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            hotkey_str = dlg.get_hotkey_str()
            if hotkey_str:
                self.set_hotkey(hotkey_str)


class HotkeyDialog(QDialog):
    """Dialog for selecting a hotkey combination via checkboxes and dropdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr.t("hotkey.choose_combination"))
        self.setModal(True)
        layout = QVBoxLayout(self)

        mod_layout = QHBoxLayout()
        self.ctrl_cb = QCheckBox('Ctrl')
        self.alt_cb = QCheckBox('Alt')
        self.shift_cb = QCheckBox('Shift')
        self.win_cb = QCheckBox('Win')
        mod_layout.addWidget(self.ctrl_cb)
        mod_layout.addWidget(self.alt_cb)
        mod_layout.addWidget(self.shift_cb)
        mod_layout.addWidget(self.win_cb)
        layout.addLayout(mod_layout)

        layout.addWidget(QLabel(tr.t("hotkey.key")))
        self.key_combo = QComboBox()
        self._populate_keys()
        layout.addWidget(self.key_combo)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('OK')
        cancel_btn = QPushButton(tr.t("hotkey.cancel"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _populate_keys(self):
        self.key_combo.addItem('<Unmapped>')
        for c in range(ord('A'), ord('Z') + 1):
            self.key_combo.addItem(chr(c))
        for c in range(ord('0'), ord('9') + 1):
            self.key_combo.addItem(chr(c))
        for i in range(1, 13):
            self.key_combo.addItem(f'F{i}')
        special = [
            'Delete', 'Enter', 'Insert', 'Tab', 'Esc', 'Backspace', 'Home', 'End',
            'PageUp', 'PageDown', 'PrintScreen', 'ScrollLock', 'Pause', 'CapsLock',
            'NumLock', 'Space',
        ]
        for s in special:
            self.key_combo.addItem(s)

    def get_hotkey_str(self):
        parts = []
        if self.ctrl_cb.isChecked():
            parts.append('Ctrl')
        if self.alt_cb.isChecked():
            parts.append('Alt')
        if self.shift_cb.isChecked():
            parts.append('Shift')
        if self.win_cb.isChecked():
            parts.append('Win')
        key = self.key_combo.currentText()
        if key and key != '<Unmapped>':
            parts.append(key)
        return '+'.join(parts)
