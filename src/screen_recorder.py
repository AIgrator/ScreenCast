import time
import threading
import os
import subprocess
import logging
import platform
import numpy as np
import cv2
import mss
import soundcard as sc
import soundfile as sf
import imageio_ffmpeg

from PyQt6.QtCore import QObject, pyqtSignal

from src.ui.settings_dialog import RESOLUTION_PRESETS
from src.ui.file_page import parse_filename_pattern
from src import translation_manager as tr

HW_ENCODERS = [
    {"key": "h264_nvenc", "label": "NVIDIA NVENC"},
    {"key": "h264_amf",   "label": "AMD AMF"},
    {"key": "h264_qsv", "label": "Intel Quick Sync"},
]


def detect_hw_encoder(ffmpeg_bin=None):
    if ffmpeg_bin is None:
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    for enc in HW_ENCODERS:
        try:
            cmd = [
                ffmpeg_bin, "-y",
                "-f", "lavfi", "-i", "nullsrc=s=320x240:d=0.1",
                "-c:v", enc["key"], "-f", "null", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0:
                logging.info(f"HW encoder found: {enc['label']} ({enc['key']})")
                return enc["key"]
        except Exception:
            pass
    logging.info("No HW encoder found, using libx264")
    return "libx264"


class AudioDevices:
    @staticmethod
    def get_loopback_devices():
        devices_map = []
        try:
            speakers = sc.all_speakers()
            for sp in speakers:
                devices_map.append((sp.id, sp.name))
        except Exception as e:
            logging.error(tr.t("log.speakers_error", error=e))
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
            logging.error(tr.t("log.output_dir_error", path=self.output_dir, error=e), exc_info=True)

        pattern = self.sm.get("filename_pattern", "%Y%m%d-%H%M%S") if self.sm else "%Y%m%d-%H%M%S"
        base_name = parse_filename_pattern(pattern, self.output_dir)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.video_temp = os.path.join(self.output_dir, f"temp_video_{timestamp}.avi")
        self.audio_temp = os.path.join(self.output_dir, f"temp_audio_{timestamp}.wav")
        self.output_file = os.path.join(self.output_dir, f"{base_name}.mp4")

        self.stop_event = threading.Event()
        self.video_thread = None
        self.audio_thread = None
        self.is_recording = False

    def _record_video(self):
        logging.info(tr.t("log.video_thread_started"))
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadPriority(
                    ctypes.windll.kernel32.GetCurrentThread(), -1
                )
            except Exception:
                pass
        try:
            backend = self.sm.get("capture_backend", "mss")
            if backend == "dxcam":
                self._record_video_dxcam()
            else:
                self._record_video_mss()
        except Exception as e:
            logging.error(tr.t("log.video_thread_error", error=e), exc_info=True)

    def _record_video_mss(self):
        with mss.MSS() as sct:
            if self.monitor_index < len(sct.monitors):
                monitor = sct.monitors[self.monitor_index]
            else:
                logging.warning(tr.t("log.monitor_not_found", index=self.monitor_index))
                monitor = sct.monitors[1]

            src_w = monitor["width"]
            src_h = monitor["height"]

            res_key = self.sm.get("video_resolution", "720p")
            preset = RESOLUTION_PRESETS.get(res_key, RESOLUTION_PRESETS["720p"])
            out_w = preset["width"]
            out_h = preset["height"]
            fps = self.sm.get("video_fps", 15)

            need_resize = (src_w != out_w or src_h != out_h)
            logging.info(tr.t("log.monitor_capture", index=self.monitor_index, src_w=src_w, src_h=src_h, out_w=out_w, out_h=out_h, fps=fps))

            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            writer = cv2.VideoWriter(self.video_temp, fourcc, fps, (out_w, out_h))

            if not writer.isOpened():
                raise RuntimeError(tr.t("log.videowriter_failed", path=self.video_temp))

            frame_interval = 1.0 / fps
            next_frame_time = time.time()

            while not self.stop_event.is_set():
                try:
                    img = sct.grab(monitor)
                    frame = np.array(img)[:, :, :3]
                    if need_resize:
                        frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                    writer.write(frame)
                except Exception as e:
                    logging.error(tr.t("log.frame_error", error=e), exc_info=True)

                next_frame_time += frame_interval
                sleep_time = next_frame_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_frame_time = time.time()

            writer.release()
            logging.info(tr.t("log.video_writer_closed"))

    def _record_video_dxcam(self):
        import dxcam

        res_key = self.sm.get("video_resolution", "720p")
        preset = RESOLUTION_PRESETS.get(res_key, RESOLUTION_PRESETS["720p"])
        out_w = preset["width"]
        out_h = preset["height"]
        fps = self.sm.get("video_fps", 15)

        camera = dxcam.create(output_idx=self.monitor_index, backend="dxgi")
        info = camera.info
        src_w = info["width"]
        src_h = info["height"]
        need_resize = (src_w != out_w or src_h != out_h)
        logging.info(tr.t("log.monitor_capture", index=self.monitor_index, src_w=src_w, src_h=src_h, out_w=out_w, out_h=out_h, fps=fps))

        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        writer = cv2.VideoWriter(self.video_temp, fourcc, fps, (out_w, out_h))

        if not writer.isOpened():
            raise RuntimeError(tr.t("log.videowriter_failed", path=self.video_temp))

        camera.start(target_fps=fps, video_mode=True)

        while not self.stop_event.is_set():
            try:
                frame = camera.get_latest_frame()
                if frame is None:
                    time.sleep(0.005)
                    continue
                frame = frame[:, :, :3]
                if need_resize:
                    frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                writer.write(frame)
            except Exception as e:
                logging.error(tr.t("log.frame_error", error=e), exc_info=True)

        camera.stop()
        writer.release()
        logging.info(tr.t("log.video_writer_closed"))

    def _record_audio(self):
        logging.info(tr.t("log.audio_thread_started"))
        try:
            sp = None
            if self.audio_device_id is not None:
                try:
                    sp = sc.get_speaker(str(self.audio_device_id))
                except Exception as e:
                    logging.warning(tr.t("log.speaker_error", device=self.audio_device_id, error=e))
            if sp is None:
                sp = sc.default_speaker()

            mic = sc.get_microphone(id=str(sp.id), include_loopback=True)
            samplerate = self.sm.get("audio_sample_rate", 48000)
            out_channels = 2

            logging.info(tr.t("log.loopback_info", name=sp.name, channels=sp.channels, samplerate=samplerate))

            with mic.recorder(samplerate=samplerate, channels=sp.channels, blocksize=4096) as recorder, \
                 sf.SoundFile(self.audio_temp, mode='w', samplerate=samplerate, channels=out_channels, subtype='PCM_16') as file:
                while not self.stop_event.is_set():
                    try:
                        data = recorder.record(numframes=4096)
                        if data.shape[1] > 2:
                            data = data[:, :2]
                        file.write(data)
                    except Exception as e:
                        logging.error(tr.t("log.audio_frame_error", error=e), exc_info=True)
                        time.sleep(0.01)
            logging.info(tr.t("log.audio_finished"))
        except Exception as e:
            logging.error(tr.t("log.audio_thread_error", error=e), exc_info=True)

    def start(self):
        if self.is_recording:
            return
        logging.info(tr.t("log.starting_recording"))
        self.is_recording = True
        self.stop_event.clear()
        self.video_thread = threading.Thread(target=self._record_video, daemon=True)
        self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.video_thread.start()
        self.audio_thread.start()

    def stop(self):
        if not self.is_recording:
            return
        logging.info(tr.t("log.stopping_recording"))
        self.stop_event.set()
        if self.video_thread:
            self.video_thread.join()
        if self.audio_thread:
            self.audio_thread.join()
        self.is_recording = False
        threading.Thread(target=self._mux_files, daemon=True).start()

    def _get_duration(self, filepath):
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ffmpeg_bin, "-i", filepath, "-f", "null", "-"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            for line in result.stderr.splitlines():
                if "Duration:" in line:
                    dur_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = dur_str.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
        return None

    def _mux_files(self):
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            has_audio = os.path.exists(self.audio_temp) and os.path.getsize(self.audio_temp) > 0
            vbr = self.sm.get("video_bitrate", 1500)
            abr = self.sm.get("audio_bitrate", 256)

            encoder = self.sm.get("video_encoder", "auto")
            if encoder == "auto":
                vcodec = detect_hw_encoder(ffmpeg_bin)
            else:
                vcodec = encoder

            duration = self._get_duration(self.video_temp)
            logging.info(tr.t("log.video_duration", duration=duration))
            logging.info(f"Using encoder: {vcodec}")

            if has_audio:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp, "-i", self.audio_temp,
                    "-c:v", vcodec, "-b:v", f"{vbr}k",
                    "-c:a", "aac", "-b:a", f"{abr}k",
                    "-shortest", "-progress", "pipe:1",
                    self.output_file
                ]
            else:
                logging.warning(tr.t("log.no_audio"))
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", self.video_temp,
                    "-c:v", vcodec, "-b:v", f"{vbr}k",
                    "-progress", "pipe:1",
                    self.output_file
                ]

            logging.info(tr.t("log.ffmpeg_cmd", cmd=" ".join(cmd)))
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stderr_lines = []
            def read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line.decode("utf-8", errors="ignore").strip())

            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()

            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                        current = us / 1_000_000
                        if duration and duration > 0:
                            pct = min(int(current / duration * 100), 99)
                            self.progress.emit(pct)
                            logging.info(tr.t("log.ffmpeg_progress", current=current, duration=duration, pct=pct))
                    except (ValueError, ZeroDivisionError):
                        pass

            proc.wait()
            stderr_thread.join(timeout=5)

            if proc.returncode != 0:
                stderr_text = "\n".join(stderr_lines)
                logging.error(tr.t("log.ffmpeg_stderr", text=stderr_text))
                raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=stderr_text)

            self.progress.emit(100)
            logging.info(tr.t("log.mux_done", path=self.output_file))
            self.finished.emit(self.output_file)
        except subprocess.CalledProcessError as e:
            logging.error(tr.t("log.ffmpeg_stderr", text=e.stderr), exc_info=True)
            self.finished.emit("")
        except Exception as e:
            logging.error(tr.t("log.mux_error", error=e), exc_info=True)
            self.finished.emit("")
        finally:
            for f in [self.video_temp, self.audio_temp]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
