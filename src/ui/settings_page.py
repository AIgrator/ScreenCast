import logging

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QGroupBox, QFormLayout, QWidget
)

from src import translation_manager as tr

logger = logging.getLogger(__name__)

RESOLUTION_PRESETS = {
    "480p":  {"label": "480p (854x480)",   "width": 854,  "height": 480},
    "720p":  {"label": "720p (1280x720)",  "width": 1280, "height": 720},
    "1080p": {"label": "1080p (1920x1080)", "width": 1920, "height": 1080},
}

VIDEO_BITRATE_OPTIONS = [500, 1000, 1500, 2000, 3000, 5000]
AUDIO_BITRATE_OPTIONS = [128, 192, 256, 320]
AUDIO_SAMPLE_RATE_OPTIONS = [44100, 48000]
FPS_OPTIONS = [10, 15, 20, 25, 30]


class SettingsPageWidget(QWidget):
    """Quality settings page: resolution, FPS, video/audio bitrate."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        video_group = QGroupBox(tr.t("quality.video"))
        video_layout = QVBoxLayout(video_group)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel(tr.t("quality.resolution")))
        self.res_combo = QComboBox()
        for key, preset in RESOLUTION_PRESETS.items():
            self.res_combo.addItem(preset["label"], key)
        idx = self.res_combo.findData(self.sm.get("video_resolution"))
        if idx >= 0:
            self.res_combo.setCurrentIndex(idx)
        res_row.addWidget(self.res_combo)
        video_layout.addLayout(res_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel(tr.t("quality.fps")))
        self.fps_combo = QComboBox()
        for fps in FPS_OPTIONS:
            self.fps_combo.addItem(f"{fps} FPS", fps)
        idx = self.fps_combo.findData(self.sm.get("video_fps"))
        if idx >= 0:
            self.fps_combo.setCurrentIndex(idx)
        fps_row.addWidget(self.fps_combo)
        video_layout.addLayout(fps_row)

        vbr_row = QHBoxLayout()
        vbr_row.addWidget(QLabel(tr.t("quality.video_bitrate")))
        self.vbitrate_combo = QComboBox()
        for br in VIDEO_BITRATE_OPTIONS:
            self.vbitrate_combo.addItem(f"{br} kbps", br)
        idx = self.vbitrate_combo.findData(self.sm.get("video_bitrate"))
        if idx >= 0:
            self.vbitrate_combo.setCurrentIndex(idx)
        vbr_row.addWidget(self.vbitrate_combo)
        video_layout.addLayout(vbr_row)

        layout.addRow(video_group)

        audio_group = QGroupBox(tr.t("quality.audio"))
        audio_layout = QVBoxLayout(audio_group)

        abr_row = QHBoxLayout()
        abr_row.addWidget(QLabel(tr.t("quality.audio_bitrate")))
        self.abitrate_combo = QComboBox()
        for br in AUDIO_BITRATE_OPTIONS:
            self.abitrate_combo.addItem(f"{br} kbps", br)
        idx = self.abitrate_combo.findData(self.sm.get("audio_bitrate"))
        if idx >= 0:
            self.abitrate_combo.setCurrentIndex(idx)
        abr_row.addWidget(self.abitrate_combo)
        audio_layout.addLayout(abr_row)

        asr_row = QHBoxLayout()
        asr_row.addWidget(QLabel(tr.t("quality.sample_rate")))
        self.asr_combo = QComboBox()
        for sr in AUDIO_SAMPLE_RATE_OPTIONS:
            self.asr_combo.addItem(f"{sr} Hz", sr)
        idx = self.asr_combo.findData(self.sm.get("audio_sample_rate"))
        if idx >= 0:
            self.asr_combo.setCurrentIndex(idx)
        asr_row.addWidget(self.asr_combo)
        audio_layout.addLayout(asr_row)

        layout.addRow(audio_group)

    def get_settings(self):
        return {
            "video_resolution": self.res_combo.currentData(),
            "video_fps": self.fps_combo.currentData(),
            "video_bitrate": self.vbitrate_combo.currentData(),
            "audio_bitrate": self.abitrate_combo.currentData(),
            "audio_sample_rate": self.asr_combo.currentData(),
        }
