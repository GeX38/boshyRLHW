"""Клавиши и изображение окна Boshy через Windows API."""
import ctypes as C

import numpy as np

from .controls import HeldControlsMixin


# Win32 uses 32-bit LONG/DWORD even in a 64-bit Python process.
class Point(C.Structure):
    _fields_ = [("x", C.c_int32), ("y", C.c_int32)]


class Rect(C.Structure):
    _fields_ = [(name, C.c_int32) for name in ("left", "top", "right", "bottom")]


class KeyboardInput(C.Structure):
    _fields_ = [("vk", C.c_uint16), ("scan", C.c_uint16),
                ("flags", C.c_uint32), ("time", C.c_uint32),
                ("extra", C.c_size_t)]


class MouseInput(C.Structure):
    _fields_ = [("dx", C.c_int32), ("dy", C.c_int32),
                ("data", C.c_uint32), ("flags", C.c_uint32),
                ("time", C.c_uint32), ("extra", C.c_size_t)]


class HardwareInput(C.Structure):
    _fields_ = [("message", C.c_uint32), ("low", C.c_uint16),
                ("high", C.c_uint16)]


class InputData(C.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput),
                ("hardware", HardwareInput)]


class Input(C.Structure):
    _fields_ = [("type", C.c_uint32), ("data", InputData)]


class GameInterface(HeldControlsMixin):
    def __init__(self, config):
        self.config = config
        self.pressed_keys = set()
        self.user32 = C.WinDLL("user32", use_last_error=True)
        signatures = {
            "SetProcessDPIAware": ([], C.c_int),
            "FindWindowW": ([C.c_wchar_p, C.c_wchar_p], C.c_void_p),
            "GetForegroundWindow": ([], C.c_void_p),
            "GetClientRect": ([C.c_void_p, C.POINTER(Rect)], C.c_int),
            "GetWindowRect": ([C.c_void_p, C.POINTER(Rect)], C.c_int),
            "ClientToScreen": ([C.c_void_p, C.POINTER(Point)], C.c_int),
            "SetCursorPos": ([C.c_int, C.c_int], C.c_int),
            "SendInput": ([C.c_uint32, C.POINTER(Input), C.c_int], C.c_uint32),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user32, name)
            function.argtypes, function.restype = args, result
        self.user32.SetProcessDPIAware()
        self.window = self.user32.FindWindowW(None, config.window_title)
        if not self.window:
            raise RuntimeError(f'Окно "{config.window_title}" не найдено. Войди в туториал перед подключением среды.')

    def _check_focus(self):
        if self.user32.GetForegroundWindow() != self.window:
            raise RuntimeError("Переключись в окно Boshy. При потере фокуса управление останавливается.")

    def _event(self, key, down):
        # Scan codes represent physical keys, independently of the layout.
        scan_codes = {"left": (0x4B, True), "right": (0x4D, True),
                      "up": (0x48, True), "down": (0x50, True),
                      "z": (0x2C, False), "x": (0x2D, False), "r": (0x13, False),
                      "enter": (0x1C, False), "escape": (0x01, False),
                      "esc": (0x01, False), "space": (0x39, False)}
        scan, extended = scan_codes[key]
        flags = 0x0008 | int(extended) | (0 if down else 0x0002)
        event = Input(type=1, data=InputData(keyboard=KeyboardInput(scan=scan, flags=flags)))
        if self.user32.SendInput(1, C.byref(event), C.sizeof(Input)) != 1:
            raise C.WinError(C.get_last_error())

    def key_down(self, key):
        self._check_focus()
        if key not in self.pressed_keys:
            self._event(key, True)
            self.pressed_keys.add(key)

    def key_up(self, key):
        if key in self.pressed_keys:
            self._event(key, False)
            self.pressed_keys.remove(key)

    def release_all(self):
        for key in list(self.pressed_keys):
            self.key_up(key)

    def _client_box(self):
        rect, origin = Rect(), Point()
        if not self.user32.GetClientRect(self.window, C.byref(rect)):
            raise C.WinError(C.get_last_error())
        if not self.user32.ClientToScreen(self.window, C.byref(origin)):
            raise C.WinError(C.get_last_error())
        return (origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)

    def park_cursor(self):
        self._check_focus()
        rect = Rect()
        if not self.user32.GetWindowRect(self.window, C.byref(rect)):
            raise C.WinError(C.get_last_error())
        # Leave the whole window, including its title bar, without a pause.
        if not self.user32.SetCursorPos(rect.left - 10, rect.top - 10):
            raise C.WinError(C.get_last_error())

    def perform_action(self, *args, **kwargs):
        self.park_cursor()
        super().perform_action(*args, **kwargs)

    def screenshot(self):
        from PIL import ImageGrab

        self._check_focus()
        return np.array(ImageGrab.grab(bbox=self._client_box(), all_screens=True).convert("RGB"))

    def close(self):
        self.release_all()
