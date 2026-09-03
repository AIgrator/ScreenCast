import json
import logging
import os

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class SettingsManager(QObject):
    DEFAULTS = {
        "output_dir": os.path.join(os.getcwd(), "videos"),
        "filename_pattern": "{date:YYYYMMDD}-{time:HHMMSS}",
        "hotkeys": {
            "toggle_recording": "Ctrl+Shift+R",
        },
        "show_notifications": True,
        "tray_colors": {
            "idle": [50, 150, 250],
            "recording": [220, 50, 50],
            "saving": [230, 180, 30],
        },
        "video_resolution": "720p",
        "video_fps": 15,
        "video_bitrate": 1500,
        "audio_bitrate": 256,
        "audio_sample_rate": 48000,
        "selected_monitor": 1,
        "selected_audio_device": None,
    }

    settings_changed = pyqtSignal(dict)

    def __init__(self, settings_file='settings.json'):
        super().__init__()
        self.SETTINGS_FILE = settings_file
        self._settings = self._load_settings()

    def _load_settings(self):
        if not os.path.exists(self.SETTINGS_FILE):
            return self.DEFAULTS.copy()
        try:
            with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = self.DEFAULTS.copy()
            for k, v in self.DEFAULTS.items():
                if k in data:
                    result[k] = data[k]
                elif isinstance(v, dict):
                    result[k] = {**v, **data.get(k, {})}
            return result
        except Exception as e:
            logger.warning(f"Ошибка загрузки настроек: {e}. Используем дефолтные.")
            return self.DEFAULTS.copy()

    def get(self, key, default=None):
        return self._settings.get(key, default)

    def set(self, key, value):
        self.set_many({key: value})

    def set_many(self, settings_dict: dict):
        self._settings.update(settings_dict)
        for key, value in settings_dict.items():
            logger.info(f"Setting '{key}' = '{value}'")
        self.save()

    def update(self, data: dict):
        self._settings.update(data)
        self.save()

    def save(self):
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            self.settings_changed.emit(self._settings)
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")

    def all(self):
        return self._settings
