"""Win32 热键模块烟雾测试：parse + register + unregister 生命周期。

不启动 Qt 事件循环，只验证 ctypes 调用链通、参数解析正确。
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hotkey_win32 import _parse_hotkey, MOD_ALT, MOD_CONTROL, MOD_SHIFT
import ctypes
_user32 = ctypes.WinDLL("user32", use_last_error=True)

# ── parse 测试 ─────────────────────────────────────────────────────────────────
cases = [
    ("alt+v", MOD_ALT, 0x56),
    ("alt+q", MOD_ALT, 0x51),
    ("alt+t", MOD_ALT, 0x54),
    ("ctrl+shift+f12", MOD_CONTROL | MOD_SHIFT, 0x7B),
    ("alt+f1", MOD_ALT, 0x70),
    ("shift+1", MOD_SHIFT, 0x31),
]
for spec, exp_mods, exp_vk in cases:
    mods, vk = _parse_hotkey(spec)
    assert mods == exp_mods and vk == exp_vk, f"FAIL {spec}: got ({mods:#x},{vk:#x}), expected ({exp_mods:#x},{exp_vk:#x})"
    print(f"OK parse {spec:20} -> mods={mods:#x} vk={vk:#x}")

# 错误用例
for bad in ["", "+", "alt", "alt+v+q", "alt+🔥", "unknownkey"]:
    try:
        _parse_hotkey(bad)
        print(f"FAIL should reject: {bad!r}")
    except ValueError as e:
        print(f"OK reject {bad!r}: {e}")

# ── register / unregister 生命周期测试 ────────────────────────────────────────
# 选一个不常用的组合避免冲突：Ctrl+Alt+F9
MOD_CTRL_ALT = MOD_CONTROL | MOD_ALT
VK_F9 = 0x78
HOTKEY_ID = 9999

ok = _user32.RegisterHotKey(None, HOTKEY_ID, MOD_CTRL_ALT, VK_F9)
if not ok:
    err = ctypes.get_last_error()
    print(f"FAIL RegisterHotKey ctrl+alt+f9 winerror={err}")
    sys.exit(1)
print("OK RegisterHotKey ctrl+alt+f9")

# 重复注册同一 id 应失败
ok2 = _user32.RegisterHotKey(None, HOTKEY_ID, MOD_CTRL_ALT, VK_F9)
if ok2:
    print("FAIL duplicate register should have failed")
    _user32.UnregisterHotKey(None, HOTKEY_ID)
    sys.exit(1)
print(f"OK duplicate register rejected (winerror={ctypes.get_last_error()})")

# 注销
ok = _user32.UnregisterHotKey(None, HOTKEY_ID)
assert ok, "UnregisterHotKey failed"
print("OK UnregisterHotKey")

# 注销后可以重新注册
ok = _user32.RegisterHotKey(None, HOTKEY_ID, MOD_CTRL_ALT, VK_F9)
assert ok, "re-register after unregister failed"
_user32.UnregisterHotKey(None, HOTKEY_ID)
print("OK re-register after unregister")

print("\nAll smoke tests passed.")
