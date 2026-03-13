"""
Step 1 验证脚本：仅测试截图流程，不依赖 AI 模块。
用法：在 src/ 目录下运行，或直接 python tests/test_screenshot_only.py
按 Alt+Q 唤起框选遮罩，松手后截图保存到项目根目录 temp_capture.png
"""
import sys
import os
import pathlib

# 把 src/ 加入 path，让 screenshot 模块可被导入
_src_dir = pathlib.Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_src_dir))

import keyboard
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from screenshot.capture import ScreenshotOverlay


_OUTPUT = pathlib.Path(__file__).parent.parent / "temp_capture.png"


class _Bridge(QObject):
    trigger = pyqtSignal()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    bridge = _Bridge()
    overlay_holder = [None]

    def _start():
        def _on_capture(image, position=None):
            image.save(str(_OUTPUT))
            print(f"[OK] 截图已保存：{_OUTPUT.resolve()}")
            print(f"     尺寸：{image.size}  位置参考：{position}")
            app.quit()

        overlay_holder[0] = ScreenshotOverlay(_on_capture)

    bridge.trigger.connect(_start)
    keyboard.add_hotkey("alt+q", lambda: bridge.trigger.emit())

    print("已就绪。按 Alt+Q 唤起框选，松手后自动保存截图。按 Ctrl+C 退出。")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
