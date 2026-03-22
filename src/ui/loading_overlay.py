from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPainter, QColor, QPainterPath
from PyQt6.QtCore import QRectF

_MODE_CONFIG = {
    "analyze":   ("👃", "正在闻屎中",   "#cba6f7"),
    "summarize": ("📝", "正在总结中",   "#a6e3a1"),
    "explain":   ("❓", "正在解释中",   "#89b4fa"),
    "source":    ("🎬", "正在查找出处", "#fab387"),
}

# Module-level active overlay — set/cleared by main.py
_active_overlay: "LoadingOverlay | None" = None


def update_stage(text: str) -> None:
    """Thread-safe: update right-side stage label from any thread."""
    if _active_overlay is not None:
        try:
            _active_overlay.stage_changed.emit(text)
        except RuntimeError:
            pass


class LoadingOverlay(QWidget):
    """右下角加载动画：左侧图标+模式文字（静态），右侧动态阶段显示。"""

    stage_changed = pyqtSignal(str)

    _W, _H = 390, 72

    def __init__(self, mode: str = "analyze", parent=None):
        super().__init__(parent)
        icon_char, text, color = _MODE_CONFIG.get(mode, _MODE_CONFIG["analyze"])
        self._stage_base = "准备中"
        self._dot_count = 0
        self._setup_window()
        self._setup_ui(icon_char, text, color)
        self._position_to_corner()
        self.stage_changed.connect(self._on_stage_changed)

        # 省略号动画计时器
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(500)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("")
        self.setFixedSize(self._W, self._H)

    def _setup_ui(self, icon_char: str, text: str, color: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # 左侧：图标
        icon = QLabel(icon_char)
        icon.setFont(QFont("Segoe UI Emoji", 22))
        icon.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon)

        layout.addSpacing(8)

        # 左侧：模式文字（静态）
        mode_lbl = QLabel(text)
        mode_lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        mode_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        mode_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(mode_lbl)

        layout.addStretch()

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedSize(1, 36)
        sep.setStyleSheet("background: #45475a; border: none;")
        layout.addWidget(sep)

        layout.addSpacing(12)

        # 右侧：动态阶段文字
        self._stage_label = QLabel("准备中.")
        self._stage_label.setFont(QFont("Microsoft YaHei", 11))
        self._stage_label.setStyleSheet("color: #a6adc8; background: transparent; border: none;")
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._stage_label.setFixedWidth(148)
        layout.addWidget(self._stage_label)

    def paintEvent(self, event):
        """手动绘制圆角深色背景，避免 WA_TranslucentBackground + FramelessHint 下 stylesheet 不渲染。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.fillPath(path, QColor(24, 24, 37, 230))
        painter.setPen(QColor(69, 71, 90, 200))
        painter.drawPath(path)

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        max_chars = 13
        base = self._stage_base if len(self._stage_base) <= max_chars else self._stage_base[:max_chars] + "…"
        self._stage_label.setText(base + dots)

    def _on_stage_changed(self, text: str):
        self._stage_base = text
        self._dot_count = 0
        self._tick_dots()

    def closeEvent(self, event):
        self._dot_timer.stop()
        super().closeEvent(event)

    def _position_to_corner(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self._W - 24
            y = geo.y() + geo.height() - self._H - 24
            self.move(x, y)
