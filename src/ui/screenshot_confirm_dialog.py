"""
截图确认对话框
截图完成后弹出，显示预览，用户点击「开始分析」才真正发起分析请求。
"""
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class ScreenshotConfirmDialog(QDialog):
    """显示截图缩略图，让用户决定是否分析。"""

    # 预览区最大尺寸
    _MAX_W = 480
    _MAX_H = 320

    def __init__(self, image: Image.Image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认分析？")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui(image)

    def _build_ui(self, image: Image.Image):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 外层容器（带圆角背景）────────────────────────────────────────────
        container = QLabel()
        container.setStyleSheet("""
            QLabel {
                background: #1a1a2e;
                border: 1px solid #2a2a45;
                border-radius: 10px;
            }
        """)
        inner = QVBoxLayout(container)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(10)

        # ── 截图预览 ─────────────────────────────────────────────────────────
        preview_lbl = QLabel()
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb = image.copy()
        thumb.thumbnail((self._MAX_W, self._MAX_H), Image.LANCZOS)
        w, h = thumb.size
        data = thumb.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        preview_lbl.setPixmap(pixmap)
        preview_lbl.setFixedSize(w, h)
        preview_lbl.setStyleSheet("border: 1px solid #3a3a55; border-radius: 4px;")
        inner.addWidget(preview_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

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

        btn_confirm = QPushButton("开始分析 →")
        btn_confirm.setFixedHeight(34)
        btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_confirm.setDefault(True)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background: #1e1a2e; color: #cba6f7;
                border: 1px solid #cba6f7; border-radius: 6px;
                font-size: 13px; font-weight: bold; padding: 0 18px;
            }
            QPushButton:hover { background: #2e1a4e; border-color: #d4b6ff; color: #d4b6ff; }
        """)
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)
        inner.addLayout(btn_row)

        layout.addWidget(container)
