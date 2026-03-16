import sys
import threading
import logging
import traceback
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal, Qt
import keyboard

from config import SCREENSHOT_HOTKEY, IMAGE_HOTKEY
from config.manager import load as load_config, save as save_config, get_active_provider_cfg
from ai.prompts import TONE_LABELS
from screenshot.capture import ScreenshotOverlay, image_to_base64
from ai.analyzer import analyze_screenshot, analyze_text
from ui.text_input_dialog import TextInputDialog
from ui.image_input_dialog import ImageInputDialog
from ui.screenshot_confirm_dialog import ScreenshotConfirmDialog
from ui.result_window import ResultWindow
from ui.loading_overlay import LoadingOverlay


class SignalBridge(QObject):
    trigger_capture = pyqtSignal()
    trigger_image = pyqtSignal()
    show_result = pyqtSignal(dict, object)  # result_dict, position


class BullshitDetectorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.signals = SignalBridge()
        self.signals.trigger_capture.connect(self._start_capture)
        self.signals.trigger_image.connect(self._start_image_input)
        self.signals.show_result.connect(self._show_result)
        self._overlay = None
        self._result_window = None
        self._loading = None
        self._capture_position = None
        self._capture_image = None
        self._busy = False  # 截图/确认/分析任意一个阶段进行中时为 True
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

        text_action = QAction("文字/链接分析", menu)
        text_action.triggered.connect(self._start_text_input)
        menu.addAction(text_action)

        image_action = QAction(f"图片分析  ({IMAGE_HOTKEY.upper()})", menu)
        image_action.triggered.connect(self._start_image_input)
        menu.addAction(image_action)

        menu.addSeparator()

        # 回复风格子菜单
        tone_menu = QMenu("回复风格", menu)
        self._tone_actions: dict[str, QAction] = {}
        current_tone = load_config().get("response_tone", "toxic")
        for tone_key, tone_label in TONE_LABELS.items():
            action = QAction(tone_label, tone_menu)
            action.setCheckable(True)
            action.setChecked(tone_key == current_tone)
            action.triggered.connect(lambda checked, k=tone_key: self._set_tone(k))
            tone_menu.addAction(action)
            self._tone_actions[tone_key] = action
        menu.addMenu(tone_menu)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _set_tone(self, tone_key: str):
        cfg = load_config()
        cfg["response_tone"] = tone_key
        save_config(cfg)
        for k, action in self._tone_actions.items():
            action.setChecked(k == tone_key)

    def _on_capture_cancelled(self):
        self._busy = False

    def _start_capture(self):
        if self._busy:
            return
        self._busy = True
        self._overlay = ScreenshotOverlay(self._on_screenshot_taken, on_cancel=self._on_capture_cancelled)

    def _on_screenshot_taken(self, image, position=None):
        dlg = ScreenshotConfirmDialog(image)
        if position:
            dlg.move(position[0], max(0, position[1] - 20))
        if not dlg.exec():
            self._busy = False
            return  # 用户取消，不消耗 token
        self._capture_position = position
        self._capture_image = image
        b64 = image_to_base64(image)
        self._loading = LoadingOverlay()
        self._loading.show()
        thread = threading.Thread(target=self._run_analysis, args=(b64,), daemon=True)
        thread.start()

    def _run_analysis(self, image_base64: str):
        result = analyze_screenshot(image_base64)
        self._busy = False
        self.signals.show_result.emit(result, self._capture_position)

    def _start_image_input(self):
        dlg = ImageInputDialog()
        # 居中显示
        screen = self.app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            dlg.move(geo.center() - dlg.rect().center())
        if dlg.exec():
            image = dlg.get_image()
            if image:
                self._capture_image = image
                b64 = image_to_base64(image)
                self._loading = LoadingOverlay()
                self._loading.show()
                threading.Thread(target=self._run_analysis, args=(b64,), daemon=True).start()

    def _start_text_input(self):
        dlg = TextInputDialog()
        if dlg.exec():
            text = dlg.get_content()
            self._loading = LoadingOverlay()
            self._loading.show()
            threading.Thread(target=self._run_article_analysis, args=(text,), daemon=True).start()

    def _run_article_analysis(self, text: str):
        result = analyze_text(text)
        self.signals.show_result.emit(result, None)

    def _show_result(self, result: dict, position):
        if self._loading:
            self._loading.close()
            self._loading = None
        image = self._capture_image
        self._capture_image = None
        self._result_window = ResultWindow(result, position, image=image)
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
        keyboard.add_hotkey(IMAGE_HOTKEY, lambda: self.signals.trigger_image.emit())
        self._tray.showMessage(
            "BullshitDetector",
            f"已启动！按 {SCREENSHOT_HOTKEY} 截图分析",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        return self.app.exec()


def _setup_logging():
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "bullshit.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # 捕获未处理的主线程异常
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _excepthook
    # 捕获子线程异常
    def _thread_excepthook(args):
        logging.critical("子线程未捕获异常", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _thread_excepthook
    return log_file


def main():
    log_file = _setup_logging()
    logging.info("BullshitDetector 启动，日志写入: %s", log_file)
    app = BullshitDetectorApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
