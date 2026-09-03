import sys
import time
import threading
import os
import subprocess
import logging
import warnings
import numpy as np
import cv2
import mss
import soundcard as sc
import soundfile as sf
import imageio_ffmpeg

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import QObject, pyqtSignal

from src.settings_manager import SettingsManager
from src.ui.settings_dialog import SettingsDialog, RESOLUTION_PRESETS

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

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.video_temp = os.path.join(self.output_dir, f"temp_video_{timestamp}.mp4")
        self.audio_temp = os.path.join(self.output_dir, f"temp_audio_{timestamp}.wav")
        self.output_file = os.path.join(self.output_dir, f"lecture_{timestamp}.mp4")

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

    def _mux_files(self):
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            has_audio = os.path.exists(self.audio_temp) and os.path.getsize(self.audio_temp) > 0
            vbr = self.sm.get("video_bitrate", 1500)
            abr = self.sm.get("audio_bitrate", 256)

            if has_audio:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp, "-i", self.audio_temp,
                    "-c:v", "libx264", "-b:v", f"{vbr}k", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", f"{abr}k",
                    "-shortest", self.output_file
                ]
            else:
                logging.warning("Аудио отсутствует, видео без звука.")
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp,
                    "-c:v", "libx264", "-b:v", f"{vbr}k", "-preset", "veryfast",
                    self.output_file
                ]

            logging.info(f"FFmpeg: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"Готово: {self.output_file}")
            self.finished.emit(self.output_file)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg: {e.stderr.decode('utf-8', errors='ignore')}", exc_info=True)
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


class TrayApp:
    def __init__(self):
        logging.info("Инициализация TrayApp...")
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.sm = SettingsManager(CONFIG_FILE)
        self.selected_monitor = self.sm.get("selected_monitor", 1)
        self.selected_audio_device = self.sm.get("selected_audio_device")
        self.recorder = None

        self.tray_icon = QSystemTrayIcon()
        self.update_tray_icon(is_recording=False)

        self.menu = QMenu()

        self.action_toggle = self.menu.addAction("Начать запись")
        self.action_toggle.triggered.connect(self.toggle_recording)

        self.menu.addSeparator()

        self.menu_monitors = self.menu.addMenu("Выбрать монитор")
        self.populate_monitors()

        self.menu_audio = self.menu.addMenu("Выбрать источник звука")
        self.populate_audio_devices()

        self.menu.addSeparator()

        self.action_settings = self.menu.addAction("Настройки качества...")
        self.action_settings.triggered.connect(self.open_settings)

        self.menu.addSeparator()

        self.action_quit = self.menu.addAction("Выход")
        self.action_quit.triggered.connect(self.quit_app)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

        self.tray_icon.showMessage(
            "Lecture Recorder",
            "Приложение запущено в трее.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        logging.info("TrayApp запущен.")

    def update_tray_icon(self, is_recording=False):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(220, 50, 50) if is_recording else QColor(50, 150, 250)
        painter.setBrush(color)
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))

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
            res = RESOLUTION_PRESETS[self.sm.get("video_resolution")]["label"]
            self.tray_icon.showMessage(
                "Настройки сохранены",
                f"Видео: {res}, {self.sm.get('video_fps')} FPS, {self.sm.get('video_bitrate')} kbps\n"
                f"Аудио: {self.sm.get('audio_bitrate')} kbps, {self.sm.get('audio_sample_rate')} Hz",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )

    def toggle_recording(self):
        if self.recorder and self.recorder.is_recording:
            self.action_toggle.setText("Останавливается...")
            self.action_toggle.setEnabled(False)
            threading.Thread(target=self._stop_recording_async, daemon=True).start()
        else:
            self.recorder = ScreenRecorder(
                monitor_index=self.selected_monitor,
                audio_device_id=self.selected_audio_device,
                settings_manager=self.sm
            )
            self.recorder.finished.connect(self.on_recording_finished)
            self.recorder.start()
            self.update_tray_icon(is_recording=True)
            self.action_toggle.setText("Остановить запись")
            self.tray_icon.showMessage("Запись", "Запись начата", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _stop_recording_async(self):
        self.recorder.stop()

    def on_recording_finished(self, filepath):
        self.update_tray_icon(is_recording=False)
        self.action_toggle.setText("Начать запись")
        self.action_toggle.setEnabled(True)
        if filepath:
            self.tray_icon.showMessage("Запись завершена", f"Файл:\n{filepath}", QSystemTrayIcon.MessageIcon.Information, 4000)
        else:
            self.tray_icon.showMessage("Ошибка", "Не удалось свести файлы", QSystemTrayIcon.MessageIcon.Warning, 3000)

    def quit_app(self):
        if self.recorder and self.recorder.is_recording:
            self.recorder.stop()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    try:
        tray_app = TrayApp()
        tray_app.run()
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}", exc_info=True)
