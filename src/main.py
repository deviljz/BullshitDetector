import sys
import threading

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal, Qt
import keyboard

from config import SCREENSHOT_HOTKEY
from config.manager import load as load_config, get_active_provider_cfg
from screenshot.capture import ScreenshotOverlay, image_to_base64
from ai.analyzer import analyze_screenshot
from ui.result_window import ResultWindow
from ui.loading_overlay import LoadingOverlay


class SignalBridge(QObject):
    trigger_capture = pyqtSignal()
    show_result = pyqtSignal(dict, object)  # result_dict, position


class BullshitDetectorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.signals = SignalBridge()
        self.signals.trigger_capture.connect(self._start_capture)
        self.signals.show_result.connect(self._show_result)
        self._overlay = None
        self._result_window = None
        self._loading = None
        self._capture_position = None
        self._setup_tray()

    @staticmethod
    def _make_tray_icon() -> QIcon:
        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#1e1e2e"))
        p.setPen(QColor("#cba6f7"))
        p.drawEllipse(1, 1, 30, 30)
        p.setFont(QFont("Segoe UI Emoji", 16))
        p.setPen(QColor("#f9e2af"))
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "💩")
        p.end()
        return QIcon(px)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(self._make_tray_icon())
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

    def _on_screenshot_taken(self, image, position=None):
        self._capture_position = position
        b64 = image_to_base64(image)
        self._loading = LoadingOverlay()
        self._loading.show()
        thread = threading.Thread(target=self._run_analysis, args=(b64,), daemon=True)
        thread.start()

    def _run_analysis(self, image_base64: str):
        result = analyze_screenshot(image_base64)
        self.signals.show_result.emit(result, self._capture_position)

    def _show_result(self, result: dict, position):
        if self._loading:
            self._loading.close()
            self._loading = None
        self._result_window = ResultWindow(result, position)
        self._result_window.show()

    def run(self):
        api_key = get_active_provider_cfg().get("api_key", "")
        if not api_key or api_key.startswith("YOUR_"):
            QMessageBox.critical(
                None,
                "配置错误",
                "请在 config.json 中填入有效的 API Key。\n"
                "参考 config.json.example 文件完成配置。",
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
