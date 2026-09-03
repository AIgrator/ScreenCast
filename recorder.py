import sys
import time
import threading
import os
import subprocess
import logging
import warnings
import platform
import numpy as np
import cv2
import mss
import soundcard as sc
import soundfile as sf
import imageio_ffmpeg
from pynput import keyboard

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from src.settings_manager import SettingsManager
from src.ui.settings_dialog import SettingsDialog, RESOLUTION_PRESETS
from src.ui.file_page import parse_filename_pattern

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


class HotkeyManager:
    """Manages global hotkeys via pynput."""

    def __init__(self, settings_manager, toggle_callback):
        self.sm = settings_manager
        self.toggle_callback = toggle_callback
        self.listener = None
        self._last_hotkey = None
        self.register_hotkey()
        self.sm.settings_changed.connect(self._on_settings_changed)

    def _on_settings_changed(self, new_settings):
        new_hk = new_settings.get("hotkeys", {}).get("toggle_recording", "")
        if new_hk != self._last_hotkey:
            self.register_hotkey()

    def _to_pynput_format(self, key_str):
        if not key_str:
            return None
        keys = key_str.lower().split("+")
        result = []
        key_map = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "cmd": "cmd", "win": "cmd"}
        for k in keys:
            k = k.strip()
            result.append(f"<{key_map[k]}>" if k in key_map else k)
        return "+".join(result)

    def register_hotkey(self):
        self.stop()
        hk_str = self.sm.get("hotkeys", {}).get("toggle_recording", "")
        pynput_hk = self._to_pynput_format(hk_str)
        if not pynput_hk:
            return
        try:
            self.listener = keyboard.GlobalHotKeys({pynput_hk: self.toggle_callback})
            self.listener.start()
            self._last_hotkey = hk_str
            logging.info(f"Hotkey зарегистрирован: {hk_str}")
        except Exception as e:
            logging.error(f"Ошибка регистрации hotkey: {e}", exc_info=True)
            self.listener = None

    def stop(self):
        if self.listener and self.listener.is_alive():
            self.listener.stop()
            self.listener.join()
        self.listener = None

    def __del__(self):
        self.stop()


class AudioDevices:
    @staticmethod
    def get_loopback_devices():
        devices_map = []
        try:
            speakers = sc.all_speakers()
            for sp in speakers:
                devices_map.append((sp.id, sp.name))
        except Exception as e:
            logging.error(f"Ошибка получения динамиков: {e}")
        return devices_map


class ScreenRecorder(QObject):
    finished = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, output_dir="videos", monitor_index=1, audio_device_id=None, settings_manager=None):
        super().__init__()
        self.output_dir = output_dir
        self.monitor_index = monitor_index
        self.audio_device_id = audio_device_id
        self.sm = settings_manager

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"Ошибка создания папки {self.output_dir}: {e}", exc_info=True)

        pattern = self.sm.get("filename_pattern", "%Y%m%d-%H%M%S") if self.sm else "%Y%m%d-%H%M%S"
        base_name = parse_filename_pattern(pattern, self.output_dir)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.video_temp = os.path.join(self.output_dir, f"temp_video_{timestamp}.mp4")
        self.audio_temp = os.path.join(self.output_dir, f"temp_audio_{timestamp}.wav")
        self.output_file = os.path.join(self.output_dir, f"{base_name}.mp4")

        self.stop_event = threading.Event()
        self.video_thread = None
        self.audio_thread = None
        self.is_recording = False

    def _record_video(self):
        logging.info("Поток записи видео запущен.")
        try:
            with mss.MSS() as sct:
                if self.monitor_index < len(sct.monitors):
                    monitor = sct.monitors[self.monitor_index]
                else:
                    logging.warning(f"Монитор #{self.monitor_index} не найден, основной.")
                    monitor = sct.monitors[1]

                src_w = monitor["width"]
                src_h = monitor["height"]

                res_key = self.sm.get("video_resolution", "720p")
                preset = RESOLUTION_PRESETS.get(res_key, RESOLUTION_PRESETS["720p"])
                out_w = preset["width"]
                out_h = preset["height"]
                fps = self.sm.get("video_fps", 15)

                need_resize = (src_w != out_w or src_h != out_h)
                logging.info(f"Захват монитора #{self.monitor_index}: {src_w}x{src_h} -> {out_w}x{out_h}, {fps} FPS")

                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(self.video_temp, fourcc, fps, (out_w, out_h))

                if not writer.isOpened():
                    raise RuntimeError(f"VideoWriter не открылся: {self.video_temp}")

                frame_interval = 1.0 / fps
                next_frame_time = time.time()

                while not self.stop_event.is_set():
                    try:
                        img = sct.grab(monitor)
                        frame = np.array(img)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        if need_resize:
                            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
                        writer.write(frame)
                    except Exception as e:
                        logging.error(f"Ошибка кадра: {e}", exc_info=True)

                    next_frame_time += frame_interval
                    sleep_time = next_frame_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        next_frame_time = time.time()

                writer.release()
                logging.info("Видео writer закрыт.")
        except Exception as e:
            logging.error(f"Ошибка потока видео: {e}", exc_info=True)

    def _record_audio(self):
        logging.info("Поток записи системного аудио запущен.")
        try:
            sp = None
            if self.audio_device_id is not None:
                try:
                    sp = sc.get_speaker(str(self.audio_device_id))
                except Exception as e:
                    logging.warning(f"Динамик {self.audio_device_id}: {e}")
            if sp is None:
                sp = sc.default_speaker()

            mic = sc.get_microphone(id=str(sp.id), include_loopback=True)
            samplerate = self.sm.get("audio_sample_rate", 48000)
            out_channels = 2

            logging.info(f"Loopback: {sp.name}, каналов {sp.channels}, {samplerate} Hz")

            with mic.recorder(samplerate=samplerate, channels=sp.channels, blocksize=1024) as recorder, \
                 sf.SoundFile(self.audio_temp, mode='w', samplerate=samplerate, channels=out_channels, subtype='PCM_16') as file:
                while not self.stop_event.is_set():
                    try:
                        data = recorder.record(numframes=1024)
                        if data.shape[1] > 2:
                            data = data[:, :2]
                        file.write(data)
                    except Exception as e:
                        logging.error(f"Аудиокадр: {e}", exc_info=True)
                        time.sleep(0.01)
            logging.info("Аудио завершено.")
        except Exception as e:
            logging.error(f"Ошибка потока аудио: {e}", exc_info=True)

    def start(self):
        if self.is_recording:
            return
        logging.info("Запуск записи...")
        self.is_recording = True
        self.stop_event.clear()
        self.video_thread = threading.Thread(target=self._record_video, daemon=True)
        self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.video_thread.start()
        self.audio_thread.start()

    def stop(self):
        if not self.is_recording:
            return
        logging.info("Остановка записи...")
        self.stop_event.set()
        if self.video_thread:
            self.video_thread.join()
        if self.audio_thread:
            self.audio_thread.join()
        self.is_recording = False
        self._mux_files()

    def _get_duration(self, filepath):
        try:
            ffprobe_bin = imageio_ffmpeg.get_ffmpeg_exe().replace("ffmpeg", "ffprobe")
            if not os.path.exists(ffprobe_bin):
                ffprobe_bin = imageio_ffmpeg.get_ffmpeg_exe()
                cmd = [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", filepath]
                result = subprocess.run(cmd, capture_output=True, text=True)
                return float(result.stdout.strip())
            cmd = [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except Exception:
            return None

    def _mux_files(self):
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            has_audio = os.path.exists(self.audio_temp) and os.path.getsize(self.audio_temp) > 0
            vbr = self.sm.get("video_bitrate", 1500)
            abr = self.sm.get("audio_bitrate", 256)

            duration = self._get_duration(self.video_temp)
            logging.info(f"Длительность видео: {duration} сек")

            if has_audio:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp, "-i", self.audio_temp,
                    "-c:v", "libx264", "-b:v", f"{vbr}k", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", f"{abr}k",
                    "-shortest", "-progress", "pipe:1",
                    self.output_file
                ]
            else:
                logging.warning("Аудио отсутствует, видео без звука.")
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp,
                    "-c:v", "libx264", "-b:v", f"{vbr}k", "-preset", "veryfast",
                    "-progress", "pipe:1",
                    self.output_file
                ]

            logging.info(f"FFmpeg: {' '.join(cmd)}")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stderr_lines = []
            def read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line.decode("utf-8", errors="ignore").strip())

            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()

            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                logging.info(f"FFmpeg progress: {line}")
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                        current = us / 1_000_000
                        if duration and duration > 0:
                            pct = min(int(current / duration * 100), 99)
                            self.progress.emit(pct)
                            logging.info(f"FFmpeg progress: {current:.1f}s / {duration:.1f}s = {pct}%")
                    except (ValueError, ZeroDivisionError):
                        pass

            proc.wait()
            stderr_thread.join(timeout=5)

            if proc.returncode != 0:
                stderr_text = "\n".join(stderr_lines)
                logging.error(f"FFmpeg stderr: {stderr_text}")
                raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=stderr_text)

            self.progress.emit(100)
            logging.info(f"Готово: {self.output_file}")
            self.finished.emit(self.output_file)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg: {e.stderr}", exc_info=True)
            self.finished.emit("")
        except Exception as e:
            logging.error(f"Сведение: {e}", exc_info=True)
            self.finished.emit("")
        finally:
            for f in [self.video_temp, self.audio_temp]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass


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
        painter.setBrush(QColor(rgb[0], rgb[1], rgb[2]))

        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawEllipse(4, 4, 24, 24)

        if self._state == "saving" and self._save_percent > 0:
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Arial", 7, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(4, 4, 24, 24, Qt.AlignmentFlag.AlignCenter, f"{self._save_percent}%")

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
