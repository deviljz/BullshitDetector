import sys
import threading
import logging
import traceback
import uuid
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal, Qt
import keyboard

from config import SCREENSHOT_HOTKEY, IMAGE_HOTKEY, TEXT_HOTKEY
from config.manager import load as load_config, save as save_config, get_active_provider_cfg
from ai.prompts import TONE_LABELS
from screenshot.capture import ScreenshotOverlay, image_to_base64
from ai.analyzer import analyze_screenshot, analyze_text
from ui.unified_input_dialog import UnifiedInputDialog
from ui.result_window import ResultWindow
from ui.loading_overlay import LoadingOverlay
import history as hs


class SignalBridge(QObject):
    trigger_capture = pyqtSignal()
    trigger_unified = pyqtSignal()
    show_result = pyqtSignal(dict, object, object, object)  # result_dict, position, loading_overlay, images (list)


class BullshitDetectorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.signals = SignalBridge()
        self.signals.trigger_capture.connect(self._start_capture)
        self.signals.trigger_unified.connect(self._start_unified_input)
        self.signals.show_result.connect(self._show_result)
        self._overlay = None
        self._result_windows: list = []
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
        p.setFont(QFont("Segoe UI Emoji", 18))
        p.setPen(Qt.GlobalColor.transparent)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "💩")
        p.end()
        return QIcon(px)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(self._make_tray_icon())
        self._tray.setToolTip("BullshitDetector")
        menu = QMenu()

        capture_action = QAction(f"截图分析  ({SCREENSHOT_HOTKEY.upper()})", menu)
        capture_action.triggered.connect(self._start_capture)
        menu.addAction(capture_action)

        unified_action = QAction(f"图片/文字分析  ({IMAGE_HOTKEY.upper()})", menu)
        unified_action.triggered.connect(self._start_unified_input)
        menu.addAction(unified_action)

        menu.addSeparator()

        # 搜索引擎子菜单
        search_menu = QMenu("搜索引擎", menu)
        self._search_actions: dict[str, QAction] = {}
        current_search = load_config().get("search_provider", "ddg")
        for key, label in (("ddg", "DuckDuckGo（需代理）"), ("tavily", "Tavily（国内可用）")):
            action = QAction(label, search_menu)
            action.setCheckable(True)
            action.setChecked(key == current_search)
            action.triggered.connect(lambda checked, k=key: self._set_search_provider(k))
            search_menu.addAction(action)
            self._search_actions[key] = action
        menu.addMenu(search_menu)

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

        history_action = QAction("历史记录", menu)
        history_action.triggered.connect(self._open_history)
        menu.addAction(history_action)

        usage_action = QAction("用量统计", menu)
        usage_action.triggered.connect(self._open_usage)
        menu.addAction(usage_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _set_search_provider(self, key: str):
        cfg = load_config()
        cfg["search_provider"] = key
        save_config(cfg)
        for k, action in self._search_actions.items():
            action.setChecked(k == key)

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
        from ui.unified_input_dialog import UnifiedInputDialog
        dlg = UnifiedInputDialog(preloaded_image=image)
        if position:
            dlg.move(position[0], max(0, position[1] - 20))
        if not dlg.exec():
            self._busy = False
            return
        self._capture_position = position
        b64 = image_to_base64(image)
        mode = dlg.selected_mode
        self._loading = LoadingOverlay(mode)
        self._loading.show()
        # 各线程在启动时各自捕获 images/loading/position，避免并发覆盖
        session_id = str(uuid.uuid4())
        _mode_for_usage = {"summarize": "summary", "explain": "explain", "source": "source"}.get(mode, "analyze")
        try:
            import usage
            usage.create_session(session_id, _mode_for_usage)
        except Exception:
            pass
        captured = {"images": [image], "loading": self._loading, "position": position, "session_id": session_id}
        if mode == "summarize":
            target = self._run_summary
        elif mode == "explain":
            target = self._run_explain
        elif mode == "source":
            target = self._run_source_find
        else:
            target = self._run_analysis
        threading.Thread(target=target, args=(b64, captured), daemon=True).start()

    def _run_analysis(self, image_base64: str, captured: dict):
        session_id = captured.get("session_id")
        result = analyze_screenshot([image_base64], session_id=session_id)
        self._busy = False
        self.signals.show_result.emit(result, captured["position"], captured["loading"], captured["images"])

    def _run_summary(self, image_base64: str, captured: dict):
        from ai.analyzer import summarize_screenshot
        session_id = captured.get("session_id")
        result = summarize_screenshot([image_base64], session_id=session_id)
        self._busy = False
        self.signals.show_result.emit(result, captured["position"], captured["loading"], captured["images"])

    def _run_explain(self, image_base64: str, captured: dict):
        from ai.analyzer import explain_screenshot
        session_id = captured.get("session_id")
        result = explain_screenshot([image_base64], session_id=session_id)
        self._busy = False
        self.signals.show_result.emit(result, captured["position"], captured["loading"], captured["images"])

    def _run_source_find(self, image_base64: str, captured: dict):
        from ai.analyzer import source_find_screenshot
        session_id = captured.get("session_id")
        result = source_find_screenshot([image_base64], session_id=session_id)
        self._busy = False
        self.signals.show_result.emit(result, captured["position"], captured["loading"], captured["images"])

    def _start_unified_input(self):
        dlg = UnifiedInputDialog()
        screen = self.app.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            dlg.move(geo.center() - dlg.rect().center())
        if not dlg.exec():
            return
        mode = dlg.selected_mode
        images = dlg.get_images()
        loading = LoadingOverlay(mode)
        loading.show()
        session_id = str(uuid.uuid4())
        _mode_for_usage = {"summarize": "summary", "explain": "explain", "source": "source"}.get(mode, "analyze")
        try:
            import usage
            usage.create_session(session_id, _mode_for_usage)
        except Exception:
            pass
        if images:
            from ai.analyzer import analyze_screenshot, summarize_screenshot, explain_screenshot, source_find_screenshot
            b64_list = [image_to_base64(img) for img in images]
            extra = dlg.get_text()  # 可能为空，有文字则一起发给 AI
            if mode == "summarize":
                fn = lambda: summarize_screenshot(b64_list, extra, session_id=session_id)
            elif mode == "explain":
                fn = lambda: explain_screenshot(b64_list, extra, session_id=session_id)
            elif mode == "source":
                fn = lambda: source_find_screenshot(b64_list, extra, session_id=session_id)
            else:
                fn = lambda: analyze_screenshot(b64_list, extra, session_id=session_id)
        else:
            images = None
            text = dlg.get_text()
            if not text:
                loading.close()
                return
            if mode == "summarize":
                from ai.analyzer import summarize_text
                fn = lambda: summarize_text(text, session_id=session_id)
            elif mode == "explain":
                from ai.analyzer import explain_text
                fn = lambda: explain_text(text, session_id=session_id)
            elif mode == "source":
                from ai.analyzer import source_find_text
                fn = lambda: source_find_text(text, session_id=session_id)
            else:
                fn = lambda: analyze_text(text, session_id=session_id)
        threading.Thread(
            target=lambda: self.signals.show_result.emit(fn(), None, loading, images),
            daemon=True,
        ).start()

    def _open_history(self):
        from ui.history_window import HistoryWindow
        from PyQt6.QtWidgets import QApplication
        if not hasattr(self, "_history_window") or not self._history_window.isVisible():
            self._history_window = HistoryWindow()
            screen = QApplication.primaryScreen().availableGeometry()
            hw = self._history_window
            hw.adjustSize()
            # 贴在结果窗口默认位置左侧 12px（与 _position_window 逻辑一致）
            result_default_x = screen.right() - min(1200, screen.width() - 80) - 460
            x = max(screen.left() + 8, result_default_x - hw.width() - 12)
            y = screen.top() + (screen.height() - hw.height()) // 2
            hw.move(x, max(screen.top() + 20, y))
        self._history_window.show()
        self._history_window.raise_()

    @staticmethod
    def _make_thumbnail(images) -> str | None:
        if not images:
            return None
        try:
            import base64
            from io import BytesIO
            from PIL import Image
            img = images[0]
            if not isinstance(img, Image.Image):
                return None
            thumb = img.copy()
            thumb.thumbnail((80, 80), Image.LANCZOS)
            bio = BytesIO()
            thumb.convert("RGB").save(bio, "JPEG", quality=60)
            return base64.b64encode(bio.getvalue()).decode()
        except Exception:
            return None

    def _open_usage(self):
        from ui.usage_window import UsageWindow
        from PyQt6.QtWidgets import QApplication
        if not hasattr(self, "_usage_window") or not self._usage_window.isVisible():
            self._usage_window = UsageWindow()
            screen = QApplication.primaryScreen().availableGeometry()
            uw = self._usage_window
            x = screen.left() + (screen.width() - uw.width()) // 2
            y = screen.top() + (screen.height() - uw.height()) // 2
            uw.move(x, y)
        self._usage_window.show()
        self._usage_window.raise_()

    def _show_result(self, result: dict, position, loading=None, images=None):
        if loading:
            loading.close()
        elif self._loading:
            self._loading.close()
            self._loading = None
        # 清理已关闭的旧窗口
        self._result_windows = [w for w in self._result_windows if w.isVisible()]
        history_id = hs.add(result, thumbnail=self._make_thumbnail(images))
        session_id = str(uuid.uuid4())
        win = ResultWindow(result, position, images=images, history_id=history_id, session_id=session_id)
        # 有已打开的窗口时向右下偏移，避免完全重叠
        if self._result_windows and position is None:
            last = self._result_windows[-1]
            win.move(last.x() + 30, last.y() + 30)
        self._result_windows.append(win)
        win.show()

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
        keyboard.add_hotkey(IMAGE_HOTKEY, lambda: self.signals.trigger_unified.emit())
        self._tray.showMessage(
            "BullshitDetector",
            f"{SCREENSHOT_HOTKEY.upper()} 截图  {IMAGE_HOTKEY.upper()} 图片/文字分析",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        return self.app.exec()


def _setup_logging():
    if getattr(sys, "frozen", False):
        log_dir = Path(sys.executable).parent / "logs"
    else:
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
