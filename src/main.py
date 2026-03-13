import sys
import threading

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal
import keyboard

from config import SCREENSHOT_HOTKEY, OPENAI_API_KEY
from screenshot.capture import ScreenshotOverlay, image_to_base64
from ai.analyzer import analyze_screenshot
from ui.result_window import ResultWindow


class SignalBridge(QObject):
    trigger_capture = pyqtSignal()
    show_result = pyqtSignal(str)
    show_loading = pyqtSignal()


class BullshitDetectorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.signals = SignalBridge()
        self.signals.trigger_capture.connect(self._start_capture)
        self.signals.show_result.connect(self._show_result)
        self._overlay = None
        self._result_window = None
        self._setup_tray()

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("BullshitDetector")
        menu = QMenu()
        capture_action = QAction("截图分析", menu)
        capture_action.triggered.connect(self._start_capture)
        menu.addAction(capture_action)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _start_capture(self):
        self._overlay = ScreenshotOverlay(self._on_screenshot_taken)

    def _on_screenshot_taken(self, image):
        b64 = image_to_base64(image)
        self._tray.showMessage(
            "BullshitDetector", "正在分析中，请稍候...", QSystemTrayIcon.MessageIcon.Information, 3000
        )
        thread = threading.Thread(target=self._run_analysis, args=(b64,), daemon=True)
        thread.start()

    def _run_analysis(self, image_base64: str):
        try:
            result = analyze_screenshot(image_base64)
            self.signals.show_result.emit(result)
        except Exception as e:
            self.signals.show_result.emit(f"分析失败：{e}")

    def _show_result(self, text: str):
        self._result_window = ResultWindow(text)
        self._result_window.show()

    def run(self):
        if not OPENAI_API_KEY:
            QMessageBox.critical(
                None,
                "配置错误",
                "请在 .env 文件中设置 OPENAI_API_KEY。\n参考 .env.example 文件。",
            )
            return 1

        keyboard.add_hotkey(SCREENSHOT_HOTKEY, lambda: self.signals.trigger_capture.emit())
        self._tray.showMessage(
            "BullshitDetector",
            f"已启动！按 {SCREENSHOT_HOTKEY} 截图分析",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        return self.app.exec()


def main():
    app = BullshitDetectorApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
