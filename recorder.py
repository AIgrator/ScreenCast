import sys
import threading
import os
import logging
import warnings
import mss

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import QObject, pyqtSignal, Qt

from src.settings_manager import SettingsManager
from src.ui.settings_dialog import SettingsDialog
from src.hotkey_manager import HotkeyManager
from src.screen_recorder import ScreenRecorder, AudioDevices

warnings.filterwarnings("ignore", category=RuntimeWarning, module="soundcard")

CONFIG_FILE = os.path.join(os.getcwd(), "settings.json")


def setup_logging():
    log_file = os.path.join(os.getcwd(), "log.txt")
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    try:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Логирование настроено: {log_file}")
    except Exception as e:
        print(f"Не удалось настроить логирование: {e}")

setup_logging()


class TrayApp(QObject):
    toggle_requested = pyqtSignal()
    _save_finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        logging.info("Инициализация TrayApp...")
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.sm = SettingsManager(CONFIG_FILE)
        self.selected_monitor = self.sm.get("selected_monitor", 1)
        self.selected_audio_device = self.sm.get("selected_audio_device")
        self.recorder = None
        self._state = "idle"  # idle | recording | saving
        self._save_percent = 0

        self.tray_icon = QSystemTrayIcon()
        self.update_tray_icon()

        self.menu = QMenu()

        self.action_toggle = self.menu.addAction("Начать запись")
        self.action_toggle.triggered.connect(self.toggle_recording)

        self.menu.addSeparator()

        self.menu_monitors = self.menu.addMenu("Выбрать монитор")
        self.populate_monitors()

        self.menu_audio = self.menu.addMenu("Выбрать источник звука")
        self.populate_audio_devices()

        self.menu.addSeparator()

        self.action_settings = self.menu.addAction("Настройки...")
        self.action_settings.triggered.connect(self.open_settings)

        self.menu.addSeparator()

        self.action_quit = self.menu.addAction("Выход")
        self.action_quit.triggered.connect(self.quit_app)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

        self.toggle_requested.connect(self.toggle_recording)
        self._save_finished.connect(self._on_save_finished)
        self.sm.settings_changed.connect(self._on_settings_changed)
        self.hotkey_mgr = HotkeyManager(self.sm, self._on_hotkey_pressed)

        self._update_menu_action()
        self._notify("Lecture Recorder", "Приложение запущено в трее.")
        logging.info("TrayApp запущен.")

    def update_tray_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        default_colors = {
            "idle": [50, 150, 250],
            "recording": [220, 50, 50],
            "saving": [230, 180, 30],
        }
        tray_colors = self.sm.get("tray_colors", default_colors)
        rgb = tray_colors.get(self._state, default_colors["idle"])

        painter.setPen(Qt.PenStyle.NoPen)

        if self._state == "saving" and self._save_percent > 0:
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(4, 4, 24, 24)
            painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))
            span = int(self._save_percent / 100 * 5760)
            painter.drawPie(4, 4, 24, 24, 90 * 16, -span)
        else:
            painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))
            painter.drawEllipse(4, 4, 24, 24)

        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))

    def _make_circle_icon(self, rgb, size=12):
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))
        painter.setPen(QColor(100, 100, 100))
        painter.drawEllipse(0, 0, size, size)
        painter.end()
        return QIcon(pixmap)

    def _get_state_color(self):
        default_colors = {
            "idle": [50, 150, 250],
            "recording": [220, 50, 50],
            "saving": [230, 180, 30],
        }
        tray_colors = self.sm.get("tray_colors", default_colors)
        return tray_colors.get(self._state, default_colors[self._state])

    def _update_menu_action(self):
        texts = {
            "idle": "Начать запись",
            "recording": "Остановить запись",
            "saving": "Сохранение...",
        }
        self.action_toggle.setText(texts.get(self._state, "Начать запись"))
        self.action_toggle.setIcon(self._make_circle_icon(self._get_state_color()))

    def _on_settings_changed(self, new_settings):
        self.update_tray_icon()
        self._update_menu_action()

    def populate_monitors(self):
        self.menu_monitors.clear()
        try:
            with mss.MSS() as sct:
                for i, monitor in enumerate(sct.monitors):
                    name = "Все мониторы" if i == 0 else f"Монитор {i} ({monitor['width']}x{monitor['height']})"
                    action = self.menu_monitors.addAction(name)
                    action.setCheckable(True)
                    if i == self.selected_monitor:
                        action.setChecked(True)
                    action.triggered.connect(lambda checked, idx=i: self.set_monitor(idx))
        except Exception as e:
            logging.error(f"Мониторы: {e}", exc_info=True)

    def set_monitor(self, idx):
        self.selected_monitor = idx
        self.sm.set("selected_monitor", idx)
        self.populate_monitors()
        logging.info(f"Монитор: #{idx}")

    def populate_audio_devices(self):
        self.menu_audio.clear()
        try:
            default_action = self.menu_audio.addAction("По умолчанию")
            default_action.setCheckable(True)
            if self.selected_audio_device is None:
                default_action.setChecked(True)
            default_action.triggered.connect(lambda: self.set_audio_device(None))
            self.menu_audio.addSeparator()
            for dev_id, name in AudioDevices.get_loopback_devices():
                action = self.menu_audio.addAction(name)
                action.setCheckable(True)
                if self.selected_audio_device == dev_id:
                    action.setChecked(True)
                action.triggered.connect(lambda checked, d_id=dev_id: self.set_audio_device(d_id))
        except Exception as e:
            logging.error(f"Аудио: {e}", exc_info=True)

    def set_audio_device(self, dev_id):
        self.selected_audio_device = dev_id
        self.sm.set("selected_audio_device", dev_id)
        self.populate_audio_devices()
        logging.info(f"Аудио: {dev_id}")

    def open_settings(self):
        dlg = SettingsDialog(self.sm)
        if dlg.exec():
            self._notify("Настройки", "Настройки сохранены.")

    def _notify(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information, duration=2000):
        if self.sm.get("show_notifications", True):
            self.tray_icon.showMessage(title, message, icon, duration)

    def _on_hotkey_pressed(self):
        self.toggle_requested.emit()

    def toggle_recording(self):
        if self._state == "saving":
            logging.info("Hotkey: идёт сохранение, игнорируем.")
            return

        if self._state == "recording":
            logging.info("Hotkey: остановка записи...")
            self._state = "saving"
            self._save_percent = 0
            self.update_tray_icon()
            self._update_menu_action()
            self.action_toggle.setEnabled(False)
            threading.Thread(target=self._stop_and_save, daemon=True).start()
        else:
            logging.info("Hotkey: запуск записи...")
            output_dir = self.sm.get("output_dir", os.path.join(os.getcwd(), "videos"))
            self.recorder = ScreenRecorder(
                output_dir=output_dir,
                monitor_index=self.selected_monitor,
                audio_device_id=self.selected_audio_device,
                settings_manager=self.sm,
            )
            self.recorder.finished.connect(self._on_mux_finished)
            self.recorder.progress.connect(self._on_save_progress)
            self.recorder.start()
            self._state = "recording"
            self.update_tray_icon()
            self._update_menu_action()
            self._notify("Запись", "Запись начата")

    def _stop_and_save(self):
        self.recorder.stop()

    def _on_save_progress(self, percent):
        self._save_percent = percent
        self.update_tray_icon()

    def _on_mux_finished(self, filepath):
        self._save_finished.emit(filepath)

    def _on_save_finished(self, filepath):
        self._save_percent = 0
        self._state = "idle"
        self.update_tray_icon()
        self._update_menu_action()
        self.action_toggle.setEnabled(True)
        if filepath:
            logging.info(f"Запись сохранена: {filepath}")
            self._notify("Запись завершена", f"Файл сохранён:\n{filepath}", duration=4000)
        else:
            logging.error("Не удалось свести файлы")
            self._notify("Ошибка", "Не удалось свести файлы", QSystemTrayIcon.MessageIcon.Warning, 3000)

    def quit_app(self):
        if self.recorder and self.recorder.is_recording:
            self.recorder.stop()
        self.hotkey_mgr.stop()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    try:
        tray_app = TrayApp()
        tray_app.run()
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}", exc_info=True)
