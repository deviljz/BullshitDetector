from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class LoadingOverlay(QWidget):
    """屏幕右下角的加载动画小窗口：正在闻屎中..."""

    _DOTS = [".", "..", "..."]
    _INTERVAL_MS = 400
    _W, _H = 270, 72

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot_index = 0
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

        # 鼻子图标
        icon = QLabel("👃")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        icon.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(icon)

        layout.addSpacing(8)

        # 文字
        self._label = QLabel("正在闻屎中.")
        self._label.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        self._label.setStyleSheet("color: #cba6f7;")  # 薰衣草紫
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
        self._label.setText(f"正在闻屎中{self._DOTS[self._dot_index]}")

    def _position_to_corner(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self._W - 24
            y = geo.y() + geo.height() - self._H - 24
            self.move(x, y)
