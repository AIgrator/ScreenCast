import sys
import time
import threading
import queue
import os
import subprocess
import logging
import numpy as np
import cv2
import mss
import soundcard as sc
import soundfile as sf
import imageio_ffmpeg

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import QObject, pyqtSignal

# Настройка логирования в файл log.txt в корне проекта
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
        
    # Консольный вывод
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    
    # Файловый вывод (перезапись при каждом запуске)
    try:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Логирование успешно настроено в файл: {log_file}")
    except Exception as e:
        print(f"Не удалось настроить файловое логирование: {e}")

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
            logging.error(f"Ошибка при получении списка динамиков через soundcard: {e}")
        return devices_map


class ScreenRecorder(QObject):
    finished = pyqtSignal(str)

    def __init__(self, output_dir="videos", fps=15, monitor_index=1, audio_device_id=None, codec="libx264", crf=28, preset="veryfast"):
        super().__init__()
        self.output_dir = output_dir
        self.fps = fps
        self.monitor_index = monitor_index
        self.audio_device_id = audio_device_id
        self.codec = codec
        self.crf = crf
        self.preset = preset
        
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"Ошибка создания папки для видео {self.output_dir}: {e}", exc_info=True)
        
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
                    logging.warning(f"Монитор с индексом {self.monitor_index} не найден, переключаемся на основной (1).")
                    monitor = sct.monitors[1]
                    
                width = monitor["width"]
                height = monitor["height"]
                logging.info(f"Захват монитора #{self.monitor_index}: разрешение {width}x{height}")
                
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(self.video_temp, fourcc, self.fps, (width, height))
                
                if not writer.isOpened():
                    raise RuntimeError(f"Не удалось инициализировать OpenCV VideoWriter для файла: {self.video_temp}")
                
                frame_interval = 1.0 / self.fps
                next_frame_time = time.time()
                
                while not self.stop_event.is_set():
                    try:
                        img = sct.grab(monitor)
                        frame = np.array(img)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        writer.write(frame)
                    except Exception as frame_err:
                        logging.error(f"Ошибка при захвате или записи кадра видео: {frame_err}", exc_info=True)
                    
                    next_frame_time += frame_interval
                    sleep_time = next_frame_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        next_frame_time = time.time()
                        
                writer.release()
                logging.info("Видеоwriter успешно закрыт.")
        except Exception as e:
            logging.error(f"Критическая ошибка в потоке записи видео: {e}", exc_info=True)

    def _record_audio(self):
        logging.info("Поток записи системного аудио (soundcard WASAPI loopback) запущен.")
        try:
            sp = None
            if self.audio_device_id is not None:
                try:
                    sp = sc.get_speaker(str(self.audio_device_id))
                except Exception as e:
                    logging.warning(f"Не удалось открыть динамик по ID {self.audio_device_id}: {e}")
            if sp is None:
                sp = sc.default_speaker()
            
            mic = sc.get_microphone(id=str(sp.id), include_loopback=True)
            logging.info(f"Захват системного звука с устройства: {sp.name} (Каналов источника: {sp.channels})")
            
            samplerate = 48000
            out_channels = 2
            
            with mic.recorder(samplerate=samplerate, channels=sp.channels, blocksize=1024) as recorder, \
                 sf.SoundFile(self.audio_temp, mode='w', samplerate=samplerate, channels=out_channels, subtype='PCM_16') as file:
                while not self.stop_event.is_set():
                    try:
                        data = recorder.record(numframes=1024)
                        if data.shape[1] > 2:
                            data = data[:, :2]
                        file.write(data)
                    except Exception as rec_err:
                        logging.error(f"Ошибка при считывании аудиокадра loopback: {rec_err}", exc_info=True)
                        time.sleep(0.01)
            logging.info("Запись системного аудио успешно завершена.")
        except Exception as e:
            logging.error(f"Критическая ошибка в потоке записи системного аудио: {e}", exc_info=True)

    def start(self):
        if self.is_recording:
            logging.warning("Попытка запустить запись, когда она уже идет.")
            return
        logging.info("Запуск процессов записи...")
        self.is_recording = True
        self.stop_event.clear()
        
        self.video_thread = threading.Thread(target=self._record_video, daemon=True)
        self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        
        self.video_thread.start()
        self.audio_thread.start()

    def stop(self):
        if not self.is_recording:
            logging.warning("Попытка остановить запись, когда она не ведется.")
            return
        logging.info("Остановка процессов записи...")
        self.stop_event.set()
        
        if self.video_thread:
            self.video_thread.join()
        if self.audio_thread:
            self.audio_thread.join()
            
        self.is_recording = False
        logging.info("Потоки записи остановлены. Переходим к сведению файлов.")
        self._mux_files()

    def _mux_files(self):
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            logging.info(f"Используем FFmpeg бинарник: {ffmpeg_bin}")
            
            has_audio = os.path.exists(self.audio_temp) and os.path.getsize(self.audio_temp) > 0
            
            if has_audio:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp,
                    "-i", self.audio_temp,
                    "-c:v", self.codec,
                    "-crf", str(self.crf),
                    "-preset", self.preset,
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-shortest",
                    self.output_file
                ]
            else:
                logging.warning("Аудиофайл не найден или пуст. Сохраняем видео без звука.")
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp,
                    "-c:v", self.codec,
                    "-crf", str(self.crf),
                    "-preset", self.preset,
                    self.output_file
                ]
            
            logging.info(f"Запуск FFmpeg с командой: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"FFmpeg успешно завершил сведение. Итоговый файл: {self.output_file}")
            self.finished.emit(self.output_file)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore')
            logging.error(f"Ошибка FFmpeg при сведении файлов: {err_msg}", exc_info=True)
            self.finished.emit("")
        except Exception as e:
            logging.error(f"Непредвиденная ошибка при сведении файлов: {e}", exc_info=True)
            self.finished.emit("")
        finally:
            for temp_f in [self.video_temp, self.audio_temp]:
                if os.path.exists(temp_f):
                    try:
                        os.remove(temp_f)
                        logging.debug(f"Временный файл удален: {temp_f}")
                    except Exception as rm_err:
                        logging.warning(f"Не удалось удалить временный файл {temp_f}: {rm_err}")


class TrayApp:
    def __init__(self):
        logging.info("Инициализация графического интерфейса (TrayApp)...")
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        self.selected_monitor = 1
        self.selected_audio_device = None
        
        self.recorder = None
        
        self.tray_icon = QSystemTrayIcon()
        self.update_tray_icon(is_recording=False)
        
        self.menu = QMenu()
        
        self.action_toggle = self.menu.addAction("Начать запись")
        self.action_toggle.triggered.connect(self.toggle_recording)
        
        self.menu.addSeparator()
        
        self.menu_monitors = self.menu.addMenu("Выбрать монитор (Видео)")
        self.populate_monitors()
        
        self.menu_audio = self.menu.addMenu("Выбрать источник звука")
        self.populate_audio_devices()
        
        self.menu.addSeparator()
        
        self.action_quit = self.menu.addAction("Выход")
        self.action_quit.triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()
        
        self.tray_icon.showMessage(
            "Lecture Recorder",
            "Приложение запущенно в системном трее.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        logging.info("TrayApp успешно запущен в трее.")

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
                    if i == 0:
                        name = "Все мониторы (Виртуальный)"
                    else:
                        name = f"Монитор {i} ({monitor['width']}x{monitor['height']})"
                    
                    action = self.menu_monitors.addAction(name)
                    action.setCheckable(True)
                    if i == self.selected_monitor:
                        action.setChecked(True)
                    
                    action.triggered.connect(lambda checked, idx=i: self.set_monitor(idx))
        except Exception as e:
            logging.error(f"Ошибка при сканировании мониторов: {e}", exc_info=True)

    def set_monitor(self, idx):
        self.selected_monitor = idx
        self.populate_monitors()
        logging.info(f"Пользователь выбрал монитор #{idx}")
        self.tray_icon.showMessage("Настройки", f"Выбран монитор #{idx}", QSystemTrayIcon.MessageIcon.Information, 1500)

    def populate_audio_devices(self):
        self.menu_audio.clear()
        try:
            default_action = self.menu_audio.addAction("По умолчанию (Системный вывод)")
            default_action.setCheckable(True)
            if self.selected_audio_device is None:
                default_action.setChecked(True)
            default_action.triggered.connect(lambda: self.set_audio_device(None))
            
            self.menu_audio.addSeparator()
            
            loopback_devices = AudioDevices.get_loopback_devices()
            for dev_id, name in loopback_devices:
                action = self.menu_audio.addAction(name)
                action.setCheckable(True)
                if self.selected_audio_device == dev_id:
                    action.setChecked(True)
                action.triggered.connect(lambda checked, d_id=dev_id: self.set_audio_device(d_id))
        except Exception as e:
            logging.error(f"Ошибка при сканировании loopback устройств: {e}", exc_info=True)

    def set_audio_device(self, dev_id):
        self.selected_audio_device = dev_id
        self.populate_audio_devices()
        dev_name = "По умолчанию" if dev_id is None else f"{dev_id}"
        logging.info(f"Пользователь выбрал аудиоисточник: {dev_name}")
        self.tray_icon.showMessage("Настройки", f"Выбран аудиоисточник: {dev_name}", QSystemTrayIcon.MessageIcon.Information, 1500)

    def toggle_recording(self):
        if self.recorder and self.recorder.is_recording:
            logging.info("Пользователь запросил остановку записи через меню трея.")
            self.action_toggle.setText("Останавливается...")
            self.action_toggle.setEnabled(False)
            threading.Thread(target=self._stop_recording_async, daemon=True).start()
        else:
            logging.info("Пользователь запросил старт записи через меню трея.")
            self.recorder = ScreenRecorder(
                monitor_index=self.selected_monitor,
                audio_device_id=self.selected_audio_device
            )
            self.recorder.finished.connect(self.on_recording_finished)
            self.recorder.start()
            
            self.update_tray_icon(is_recording=True)
            self.action_toggle.setText("Остановить запись")
            self.tray_icon.showMessage("Запись", "Запись лекции начата", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _stop_recording_async(self):
        self.recorder.stop()

    def on_recording_finished(self, filepath):
        self.update_tray_icon(is_recording=False)
        self.action_toggle.setText("Начать запись")
        self.action_toggle.setEnabled(True)
        
        if filepath:
            logging.info(f"Запись успешно завершена и сведена. Файл: {filepath}")
            self.tray_icon.showMessage("Запись завершена", f"Файл сохранен:\n{filepath}", QSystemTrayIcon.MessageIcon.Information, 4000)
        else:
            logging.error("Сведение записи завершилось с ошибкой (пустой путь файла).")
            self.tray_icon.showMessage("Ошибка", "Не удалось свести аудио и видео", QSystemTrayIcon.MessageIcon.Warning, 3000)

    def quit_app(self):
        logging.info("Завершение работы приложения пользователем.")
        if self.recorder and self.recorder.is_recording:
            self.recorder.stop()
        self.app.quit()

    def run(self):
        logging.info("Запуск главного цикла приложения (event loop).")
        sys.exit(self.app.exec())

if __name__ == "__main__":
    try:
        tray_app = TrayApp()
        tray_app.run()
    except Exception as e:
        logging.critical(f"Неперехваченное исключение в главном потоке: {e}", exc_info=True)
