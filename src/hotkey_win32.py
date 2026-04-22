"""Win32 原生全局热键，替代 keyboard 库。

使用 user32.RegisterHotKey 注册线程级热键（hWnd=NULL），通过
QAbstractNativeEventFilter 捕获 WM_HOTKEY 消息。

为什么用这个：OS 层托管的热键在系统休眠/唤醒/锁屏后自动保持有效，
无需应用层定时重注册；底层 WH_KEYBOARD_LL hook 在休眠后会失效，
RegisterHotKey 不会。
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject

_user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MOD_MAP = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN,
}

_VK_EXTRA = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E,
}


def _parse_hotkey(spec: str) -> tuple[int, int]:
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty hotkey: {spec!r}")
    mods = 0
    key: str | None = None
    for p in parts:
        if p in _MOD_MAP:
            mods |= _MOD_MAP[p]
        elif key is None:
            key = p
        else:
            raise ValueError(f"multiple main keys in {spec!r}")
    if key is None:
        raise ValueError(f"no main key in {spec!r}")
    if len(key) == 1 and key.isalpha():
        vk = ord(key.upper())
    elif len(key) == 1 and key.isdigit():
        vk = ord(key)
    elif key in _VK_EXTRA:
        vk = _VK_EXTRA[key]
    else:
        raise ValueError(f"unknown key {key!r} in {spec!r}")
    return mods, vk


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "Win32HotkeyManager") -> None:
        super().__init__()
        self._manager = manager

    def nativeEventFilter(self, eventType, message):  # type: ignore[override]
        if eventType != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY:
            self._manager._dispatch(int(msg.wParam))
        return False, 0


class Win32HotkeyManager(QObject):
    """注册 / 注销线程级 Win32 全局热键。

    用法:
        mgr = Win32HotkeyManager(app)
        mgr.register(1, "alt+q", cb1)
        mgr.register(2, "alt+v", cb2)
        # app 退出前:
        mgr.shutdown()
    """

    def __init__(self, app) -> None:
        super().__init__()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._filter = _HotkeyEventFilter(self)
        app.installNativeEventFilter(self._filter)

    def register(self, hotkey_id: int, spec: str, callback: Callable[[], None]) -> bool:
        try:
            mods, vk = _parse_hotkey(spec)
        except ValueError as e:
            logging.error("热键格式错误 %r: %s", spec, e)
            return False
        ok = _user32.RegisterHotKey(None, hotkey_id, mods, vk)
        if not ok:
            err = ctypes.get_last_error()
            logging.error(
                "RegisterHotKey 失败 id=%d spec=%r winerror=%d（常见原因：该组合已被其他程序占用）",
                hotkey_id, spec, err,
            )
            return False
        self._callbacks[hotkey_id] = callback
        logging.info("注册热键 id=%d spec=%s", hotkey_id, spec)
        return True

    def _dispatch(self, hotkey_id: int) -> None:
        cb = self._callbacks.get(hotkey_id)
        if cb is None:
            return
        try:
            cb()
        except Exception:
            logging.exception("热键回调异常 id=%d", hotkey_id)

    def shutdown(self) -> None:
        for hotkey_id in list(self._callbacks.keys()):
            _user32.UnregisterHotKey(None, hotkey_id)
        self._callbacks.clear()
