from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


_MODE_CONFIG = {
    "analyze":  ("👃", "正在闻屎中",  "#cba6f7"),
    "summarize": ("📝", "正在总结中",  "#a6e3a1"),
    "explain":  ("❓", "正在解释中",  "#89b4fa"),
}


class LoadingOverlay(QWidget):
    """屏幕右下角的加载动画小窗口，根据模式显示不同图标和文字。"""

    _DOTS = [".", "..", "..."]
    _INTERVAL_MS = 400
    _W, _H = 270, 72

    def __init__(self, mode: str = "analyze", parent=None):
        super().__init__(parent)
        self._dot_index = 0
        icon_char, text, color = _MODE_CONFIG.get(mode, _MODE_CONFIG["analyze"])
        self._base_text = text
        self._icon_char = icon_char
        self._color = color
        self._setup_window()
        self._setup_ui()
        self._setup_timer()
        self._position_to_corner()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("")
        self.setFixedSize(self._W, self._H)
        self.winId()
        self.setWindowOpacity(0.0)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)

        icon = QLabel(self._icon_char)
        icon.setFont(QFont("Segoe UI Emoji", 22))
        icon.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(icon)

        layout.addSpacing(8)

        self._label = QLabel(f"{self._base_text}.")
        self._label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {self._color};")
        self._label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._label)

        # 整体背景卡片样式
        self.setStyleSheet(
            "QWidget {"
            "  background: rgba(24, 24, 37, 230);"
            "  border-radius: 14px;"
            "  border: 1px solid #45475a;"
            "}"
        )


    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)

    def _setup_timer(self):
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._dot_index = (self._dot_index + 1) % len(self._DOTS)
        self._label.setText(f"{self._base_text}{self._DOTS[self._dot_index]}")

    def _position_to_corner(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self._W - 24
            y = geo.y() + geo.height() - self._H - 24
            self.move(x, y)
