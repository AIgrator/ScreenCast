import time
import threading
import os
import subprocess
import logging
import platform
import ctypes
import ctypes.wintypes
import numpy as np
import cv2
import mss
import soundcard as sc
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

_kernel32 = ctypes.windll.kernel32


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


class _NamedPipe:
    def __init__(self):
        self._handle = None
        self._name = f"\\\\.\\pipe\\sc_{os.getpid()}_{time.time_ns()}"

    @property
    def path(self):
        return self._name

    def open(self):
        self._handle = _kernel32.CreateNamedPipeW(
            self._name,
            0x00000002,
            0x00000000,
            1,
            1024 * 1024,
            1024 * 1024,
            0,
            None,
        )
        if self._handle in (None, -1, 0xFFFFFFFFFFFFFFFF):
            raise OSError(f"CreateNamedPipeW failed: {ctypes.get_last_error()}")

    def wait_for_client(self):
        result = _kernel32.ConnectNamedPipe(self._handle, None)
        err = ctypes.get_last_error()
        if not result and err != 535:
            raise OSError(f"ConnectNamedPipe failed: {err}")

    def write(self, data: bytes):
        written = ctypes.wintypes.DWORD()
        buf = ctypes.create_string_buffer(data)
        result = _kernel32.WriteFile(self._handle, buf, len(data), ctypes.byref(written), None)
        if not result:
            raise OSError(f"WriteFile failed: {ctypes.get_last_error()}")
        return written.value

    def close(self):
        if self._handle is not None:
            _kernel32.DisconnectNamedPipe(self._handle)
            _kernel32.CloseHandle(self._handle)
            self._handle = None


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
        self.output_file = os.path.join(self.output_dir, f"{base_name}.mp4")

        self.stop_event = threading.Event()
        self.video_thread = None
        self.audio_thread = None
        self.is_recording = False

        self._ffmpeg_proc = None
        self._audio_pipe = None

    def start(self):
        if self.is_recording:
            return
        logging.info(tr.t("log.starting_recording"))

        res_key = self.sm.get("video_resolution", "720p")
        preset = RESOLUTION_PRESETS.get(res_key, RESOLUTION_PRESETS["720p"])
        self._out_w = preset["width"]
        self._out_h = preset["height"]
        self._fps = self.sm.get("video_fps", 30)
        self._samplerate = self.sm.get("audio_sample_rate", 48000)

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        encoder = self.sm.get("video_encoder", "auto")
        vcodec = detect_hw_encoder(ffmpeg_bin) if encoder == "auto" else encoder
        vbr = self.sm.get("video_bitrate", 1500)
        abr = self.sm.get("audio_bitrate", 256)

        self._audio_pipe = _NamedPipe()
        self._audio_pipe.open()

        cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-pix_fmt", "rgb24", "-s", f"{self._out_w}x{self._out_h}",
            "-r", str(self._fps),
            "-i", "pipe:0",
            "-f", "s16le",
            "-sample_rate", str(self._samplerate),
            "-ch_layout", "stereo",
            "-i", self._audio_pipe.path,
            "-c:v", vcodec, "-b:v", f"{vbr}k",
            "-c:a", "aac", "-b:a", f"{abr}k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            self.output_file,
        ]

        logging.info(f"FFmpeg combined: {' '.join(cmd)}")
        self._ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        self.is_recording = True
        self.stop_event.clear()
        self.video_thread = threading.Thread(target=self._record_video, daemon=True)
        self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.video_thread.start()
        self.audio_thread.start()

    def _record_video(self):
        logging.info(tr.t("log.video_thread_started"))
        if platform.system() == "Windows":
            try:
                ctypes.windll.kernel32.SetThreadPriority(
                    ctypes.windll.kernel32.GetCurrentThread(), -1
                )
            except Exception:
                pass
        try:
            backend = self.sm.get("capture_backend", "mss")
            if backend == "dxcam":
                try:
                    self._record_video_dxcam()
                except Exception as e:
                    logging.warning(f"DXcam failed ({e}), falling back to MSS")
                    self._record_video_mss()
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
            out_w = self._out_w
            out_h = self._out_h
            fps = self._fps
            need_resize = (src_w != out_w or src_h != out_h)

            logging.info(tr.t("log.monitor_capture", index=self.monitor_index, src_w=src_w, src_h=src_h, out_w=out_w, out_h=out_h, fps=fps))

            stdin = self._ffmpeg_proc.stdin
            frame_interval = 1.0 / fps
            next_frame_time = time.time()

            prof_t0 = time.perf_counter()
            prof_frames = 0
            prof_capture = 0.0
            prof_resize = 0.0
            prof_write = 0.0

            try:
                while not self.stop_event.is_set():
                    try:
                        t1 = time.perf_counter()
                        img = sct.grab(monitor)
                        t2 = time.perf_counter()
                        frame = np.array(img)[:, :, :3]
                        prof_capture += t2 - t1
                        if need_resize:
                            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                            prof_resize += time.perf_counter() - t2
                        t3 = time.perf_counter()
                        stdin.write(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).tobytes())
                        prof_write += time.perf_counter() - t3
                        prof_frames += 1

                        now = time.perf_counter()
                        if now - prof_t0 >= 5.0:
                            total = prof_capture + prof_resize + prof_write
                            logging.info(
                                f"[PROF] {prof_frames} frames in {now - prof_t0:.1f}s | "
                                f"capture: {prof_capture/total*100:.0f}% ({prof_capture/prof_frames*1000:.1f}ms) | "
                                f"resize: {prof_resize/total*100:.0f}% ({prof_resize/prof_frames*1000:.1f}ms) | "
                                f"write: {prof_write/total*100:.0f}% ({prof_write/prof_frames*1000:.1f}ms)"
                            )
                            prof_t0 = now
                            prof_frames = 0
                            prof_capture = 0.0
                            prof_resize = 0.0
                            prof_write = 0.0
                    except Exception as e:
                        logging.error(tr.t("log.frame_error", error=e), exc_info=True)

                    next_frame_time += frame_interval
                    sleep_time = next_frame_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        next_frame_time = time.time()
            except (BrokenPipeError, OSError):
                pass
            logging.info(tr.t("log.video_writer_closed"))

    def _record_video_dxcam(self):
        import dxcam

        out_w = self._out_w
        out_h = self._out_h
        fps = self._fps

        camera = dxcam.create(output_idx=self.monitor_index - 1, backend="dxgi")
        src_w = camera.width
        src_h = camera.height
        need_resize = (src_w != out_w or src_h != out_h)

        logging.info(tr.t("log.monitor_capture", index=self.monitor_index, src_w=src_w, src_h=src_h, out_w=out_w, out_h=out_h, fps=fps))

        stdin = self._ffmpeg_proc.stdin
        camera.start(target_fps=fps, video_mode=True)

        prof_t0 = time.perf_counter()
        prof_frames = 0
        prof_capture = 0.0
        prof_resize = 0.0
        prof_write = 0.0

        try:
            while not self.stop_event.is_set():
                try:
                    t1 = time.perf_counter()
                    frame = camera.get_latest_frame()
                    t2 = time.perf_counter()
                    if frame is None:
                        time.sleep(0.005)
                        continue
                    prof_capture += t2 - t1
                    if need_resize:
                        frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                        prof_resize += time.perf_counter() - t2
                    t3 = time.perf_counter()
                    stdin.write(frame.tobytes())
                    prof_write += time.perf_counter() - t3
                    prof_frames += 1

                    now = time.perf_counter()
                    if now - prof_t0 >= 5.0:
                        total = prof_capture + prof_resize + prof_write
                        logging.info(
                            f"[PROF] {prof_frames} frames in {now - prof_t0:.1f}s | "
                            f"capture: {prof_capture/total*100:.0f}% ({prof_capture/prof_frames*1000:.1f}ms) | "
                            f"resize: {prof_resize/total*100:.0f}% ({prof_resize/prof_frames*1000:.1f}ms) | "
                            f"write: {prof_write/total*100:.0f}% ({prof_write/prof_frames*1000:.1f}ms)"
                        )
                        prof_t0 = now
                        prof_frames = 0
                        prof_capture = 0.0
                        prof_resize = 0.0
                        prof_write = 0.0
                except Exception as e:
                    logging.error(tr.t("log.frame_error", error=e), exc_info=True)
        except (BrokenPipeError, OSError):
            pass
        finally:
            camera.stop()
            logging.info(tr.t("log.video_writer_closed"))

    def _record_audio(self):
        logging.info(tr.t("log.audio_thread_started"))
        pipe = self._audio_pipe
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

            logging.info(tr.t("log.loopback_info", name=sp.name, channels=sp.channels, samplerate=samplerate))

            pipe.wait_for_client()

            with mic.recorder(samplerate=samplerate, channels=sp.channels, blocksize=4096) as recorder:
                while not self.stop_event.is_set():
                    try:
                        data = recorder.record(numframes=4096)
                        if data.shape[1] > 2:
                            data = data[:, :2]
                        pcm = (data * 32767).clip(-32768, 32767).astype(np.int16)
                        pipe.write(pcm.tobytes())
                    except Exception as e:
                        logging.error(tr.t("log.audio_frame_error", error=e), exc_info=True)
                        time.sleep(0.01)
            logging.info(tr.t("log.audio_finished"))
        except OSError:
            pass
        except Exception as e:
            logging.error(tr.t("log.audio_thread_error", error=e), exc_info=True)

    def stop(self):
        if not self.is_recording:
            return
        logging.info(tr.t("log.stopping_recording"))
        self.stop_event.set()
        threading.Thread(target=self._finalize, daemon=True).start()

    def _finalize(self):
        if self.video_thread:
            self.video_thread.join()
        if self.audio_thread:
            self.audio_thread.join()

        if self._ffmpeg_proc and self._ffmpeg_proc.stdin:
            try:
                self._ffmpeg_proc.stdin.close()
            except OSError:
                pass

        if self._audio_pipe:
            self._audio_pipe.close()
            self._audio_pipe = None

        if self._ffmpeg_proc:
            logging.info("FFmpeg: waiting for finish...")
            self._ffmpeg_proc.wait()
            if self._ffmpeg_proc.returncode != 0:
                logging.error(f"FFmpeg exited with code {self._ffmpeg_proc.returncode}")
            else:
                logging.info(tr.t("log.mux_done", path=self.output_file))
            self._ffmpeg_proc = None

        self.is_recording = False
        self.finished.emit(self.output_file)
