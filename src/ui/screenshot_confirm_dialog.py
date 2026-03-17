"""
截图确认对话框
截图完成后弹出，显示预览，用户点击「开始分析」才真正发起分析请求。
"""
from PIL import Image
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)


class ScreenshotConfirmDialog(QDialog):
    """显示截图缩略图，让用户决定是否分析。"""

    _MAX_W = 480
    _MAX_H = 320

    def __init__(self, image: Image.Image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.winId()
        self.setWindowOpacity(0.0)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a2e;
                border: 1px solid #2a2a45;
                border-radius: 10px;
            }
        """)
        self._drag_pos = QPoint()
        self.selected_mode = "analyze"
        self._build_ui(image)
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()

    def _accept_with_mode(self, mode: str):
        self.selected_mode = mode
        self.accept()

    def _build_ui(self, image: Image.Image):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ── 截图预览 ─────────────────────────────────────────────────────────
        thumb = image.copy()
        thumb.thumbnail((self._MAX_W, self._MAX_H), Image.LANCZOS)
        w, h = thumb.size
        data = thumb.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        preview_lbl = QLabel()
        preview_lbl.setPixmap(pixmap)
        preview_lbl.setFixedSize(self._MAX_W, self._MAX_H)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_lbl.setStyleSheet(
            "border: 1px solid #3a3a55; border-radius: 4px; background: #0a0a14;"
        )
        layout.addWidget(preview_lbl)

        # ── 分隔线 ───────────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2a2a45;")
        layout.addWidget(line)

        # ── 按钮行 ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #2a2a3e; color: #6c7086;
                border: 1px solid #3a3a55; border-radius: 6px;
                font-size: 13px; padding: 0 18px;
            }
            QPushButton:hover { background: #333355; color: #cdd6f4; }
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_summarize = QPushButton("📝 总结")
        btn_summarize.setFixedHeight(34)
        btn_summarize.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_summarize.setStyleSheet("""
            QPushButton {
                background: #1a2e1e; color: #a6e3a1;
                border: 1px solid #a6e3a1; border-radius: 6px;
                font-size: 13px; font-weight: bold; padding: 0 18px;
            }
            QPushButton:hover { background: #1e4028; border-color: #b6f3b1; color: #b6f3b1; }
        """)
        btn_summarize.clicked.connect(lambda: self._accept_with_mode("summarize"))

        btn_analyze = QPushButton("🔍 鉴屎官")
        btn_analyze.setFixedHeight(34)
        btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_analyze.setDefault(True)
        btn_analyze.setStyleSheet("""
            QPushButton {
                background: #1e1a2e; color: #cba6f7;
                border: 1px solid #cba6f7; border-radius: 6px;
                font-size: 13px; font-weight: bold; padding: 0 18px;
            }
            QPushButton:hover { background: #2e1a4e; border-color: #d4b6ff; color: #d4b6ff; }
        """)
        btn_analyze.clicked.connect(lambda: self._accept_with_mode("analyze"))

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_summarize)
        btn_row.addWidget(btn_analyze)
        layout.addLayout(btn_row)
