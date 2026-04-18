"""Self-test script: automates Flutter app testing with screenshots."""
import subprocess, time, ctypes, ctypes.wintypes, win32gui, win32ui, sys
from PIL import Image
import pyautogui

pyautogui.FAILSAFE = False

EXE = r'F:\Project\BullshitDetector\flutter_app\build\windows\x64\runner\Release\bullshit_detector.exe'

# ── helpers ────────────────────────────────────────────────────────────────────

def kill_app():
    subprocess.run(['taskkill', '/F', '/IM', 'bullshit_detector.exe'], capture_output=True)
    time.sleep(1.5)

def set_clipboard(text):
    """Set Unicode text to clipboard with retry."""
    import win32clipboard
    for i in range(10):
        try:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            print(f'  clipboard set: {text[:40]}')
            return True
        except Exception as e:
            print(f'  clipboard retry {i}: {e}')
            time.sleep(0.5)
    return False

def find_main_window():
    """Find the Flutter main window (largest FLUTTER class window)."""
    results = []
    def cb(hwnd, _):
        cls = win32gui.GetClassName(hwnd)
        if 'FLUTTER' not in cls.upper():
            return
        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        results.append((w, hwnd, rect))
    win32gui.EnumWindows(cb, None)
    results.sort(reverse=True)
    return results[0][1] if results else None

def capture(hwnd, path):
    rect = win32gui.GetWindowRect(hwnd)
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    hdc = win32gui.GetWindowDC(hwnd)
    mdc = win32ui.CreateDCFromHandle(hdc)
    cdc = mdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w * 2, h * 2)
    cdc.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, cdc.GetSafeHdc(), 2)
    tmp = path.replace('.png', '.bmp')
    bmp.SaveBitmapFile(cdc, tmp)
    mdc.DeleteDC(); cdc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    img = Image.open(tmp)
    img.save(path)
    print(f'  screenshot: {path} ({w}x{h} logical, {img.size} px)')
    return rect, img.size

# ── Test 1: Analyze window appears with text from clipboard ────────────────────
print('\n=== TEST 1: Analyze window with clipboard text ===')
kill_app()

TEST_TEXT = 'Apple revenue 394 billion dollars 2023. Record breaking year according to CEO Cook.'
if not set_clipboard(TEST_TEXT):
    print('FAIL: could not set clipboard'); sys.exit(1)

subprocess.Popen([EXE])
print('  app launched, waiting 5s...')
time.sleep(5)

# Send Alt+V to show analyze window (and reload clipboard)
pyautogui.hotkey('alt', 'v')
time.sleep(2)

hwnd = find_main_window()
if not hwnd:
    print('FAIL: window not found'); sys.exit(1)

rect, sz = capture(hwnd, r'F:\Project\BullshitDetector\tests\test1_analyze.png')
print(f'  window size: {rect[2]-rect[0]}x{rect[3]-rect[1]}')

# ── Test 2: Click analyze → loading overlay ────────────────────────────────────
print('\n=== TEST 2: Loading overlay ===')
# Window logical coords (no DPI awareness): window at (rect[0], rect[1]) size 520x700
# Button 鉴屎官 is rightmost at ~x=461, y=662 from client top-left
# Screen coords = window_left + client_x, window_top + client_y
lx = rect[0] + 461
ly = rect[1] + 662
print(f'  clicking 鉴屎官 at screen ({lx}, {ly})')
pyautogui.click(lx, ly)
time.sleep(1.5)

# Check window size - should be 390x72 if loading triggered
hwnd2 = find_main_window()
rect2 = win32gui.GetWindowRect(hwnd2) if hwnd2 else None
if rect2:
    w2, h2 = rect2[2]-rect2[0], rect2[3]-rect2[1]
    print(f'  window size after click: {w2}x{h2}')
    if w2 < 450 and h2 < 120:
        print('  PASS: window resized to overlay size!')
        capture(hwnd2, r'F:\Project\BullshitDetector\tests\test2_overlay.png')
    else:
        print('  window NOT resized - button click may have failed (disabled)')
        capture(hwnd2, r'F:\Project\BullshitDetector\tests\test2_not_triggered.png')

print('\nDone.')
