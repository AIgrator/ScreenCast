import logging
from pynput import keyboard


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
