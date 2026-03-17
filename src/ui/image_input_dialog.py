"""
图片输入对话框
支持：剪贴板粘贴（Ctrl+V）、拖拽图片文件、自动检测剪贴板。
"""
import io

from PIL import Image
from PyQt6.QtCore import Qt, QPoint, QBuffer, QIODeviceBase
from PyQt6.QtGui import QImage, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QWidget
)


_PREVIEW_MAX_W = 460
_PREVIEW_MAX_H = 360


def _qimage_to_pil(qimg: QImage) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
    qimg.save(buf, "PNG")
    buf.seek(0)
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")


class ImageInputDialog(QDialog):
    """粘贴或拖拽图片，确认后发起分析。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._drag_pos = QPoint()
        self.selected_mode = "analyze"

        self.setWindowTitle("")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.winId()
        self.setWindowOpacity(0.0)
        self._build_ui()
        self.setMinimumWidth(500)
        self.adjustSize()
        # 自动读取剪贴板
        self._try_load_clipboard()

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)

    # ── 拖拽支持 ──────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        md = event.mimeData()
        if md.hasImage() or (md.hasUrls() and any(
            u.toLocalFile().lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'))
            for u in md.urls()
        )):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        md = event.mimeData()
        if md.hasUrls():
            path = md.urls()[0].toLocalFile()
            try:
                self._set_image(Image.open(path).convert("RGB"))
            except Exception:
                pass
        elif md.hasImage():
            qimg = QImage(md.imageData())
            self._set_image(_qimage_to_pil(qimg))

    # ── 拖动窗口 ──────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()

    # ── Ctrl+V ────────────────────────────────────────────────────────────────
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._try_load_clipboard()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    # ── 内部方法 ──────────────────────────────────────────────────────────────
    def _try_load_clipboard(self):
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        qimg = cb.image()
        if not qimg.isNull():
            self._set_image(_qimage_to_pil(qimg))

    def _accept_with_mode(self, mode: str):
        self.selected_mode = mode
        self.accept()

    def _set_image(self, img: Image.Image):
        self._image = img
        # 生成预览 pixmap
        thumb = img.copy()
        thumb.thumbnail((_PREVIEW_MAX_W, _PREVIEW_MAX_H), Image.LANCZOS)
        w, h = thumb.size
        data = thumb.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        self._preview_lbl.setPixmap(pixmap)
        self._preview_lbl.setFixedSize(_PREVIEW_MAX_W, _PREVIEW_MAX_H)
        self._preview_lbl.setStyleSheet(
            "border: 1px solid #3a3a55; border-radius: 4px; background: #0a0a14;"
        )
        orig_w, orig_h = img.size
        self._hint_lbl.setText(f"✓ 已加载  {orig_w}×{orig_h}px — 可重新拖拽或粘贴替换")
        self._hint_lbl.setStyleSheet("color: #a6e3a1; font-size: 11px; padding: 4px 0;")
        for btn in (self._btn_summarize, self._btn_explain, self._btn_analyze):
            btn.setEnabled(True)
        self.adjustSize()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(24,24,37,242); border-radius: 14px;"
            " border: 1px solid #45475a; }"
        )
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 标题
        title = QLabel("🖼  图片分析")
        title.setStyleSheet("color: #cba6f7; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        # 拖放/预览区
        self._preview_lbl = QLabel()
        self._preview_lbl.setFixedSize(_PREVIEW_MAX_W, _PREVIEW_MAX_H)
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "border: 2px dashed #45475a; border-radius: 8px; background: #13131f;"
        )
        self._preview_lbl.setText(
            "拖拽图片到这里\n或按 Ctrl+V 粘贴"
        )
        self._preview_lbl.setStyleSheet(
            "color: #585b70; font-size: 13px;"
            "border: 2px dashed #45475a; border-radius: 8px; background: #13131f;"
        )
        layout.addWidget(self._preview_lbl)

        # 提示文字
        self._hint_lbl = QLabel("支持 PNG / JPG / WEBP，也可直接从微信/QQ 右键复制后粘贴")
        self._hint_lbl.setStyleSheet("color: #585b70; font-size: 11px;")
        self._hint_lbl.setWordWrap(True)
        layout.addWidget(self._hint_lbl)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #313244;")
        layout.addWidget(line)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        _disabled_style = "QPushButton:disabled { color: #45475a; border-color: #313244; background: #1a1a2e; }"

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background: #2a2a3e; color: #6c7086; border: 1px solid #3a3a55;"
            " border-radius: 6px; font-size: 13px; padding: 0 18px; }"
            "QPushButton:hover { background: #333355; color: #cdd6f4; }"
        )
        cancel_btn.clicked.connect(self.reject)

        self._btn_summarize = QPushButton("📝 总结")
        self._btn_summarize.setFixedHeight(34)
        self._btn_summarize.setEnabled(False)
        self._btn_summarize.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_summarize.setStyleSheet(
            "QPushButton { background: #1a2e1e; color: #a6e3a1; border: 1px solid #a6e3a1;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 18px; }"
            "QPushButton:hover { background: #1e4028; border-color: #b6f3b1; color: #b6f3b1; }"
            + _disabled_style
        )
        self._btn_summarize.clicked.connect(lambda: self._accept_with_mode("summarize"))

        self._btn_explain = QPushButton("❓ 解释")
        self._btn_explain.setFixedHeight(34)
        self._btn_explain.setEnabled(False)
        self._btn_explain.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_explain.setStyleSheet(
            "QPushButton { background: #1a2a3e; color: #89b4fa; border: 1px solid #89b4fa;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 18px; }"
            "QPushButton:hover { background: #1e3a5e; border-color: #99c4ff; color: #99c4ff; }"
            + _disabled_style
        )
        self._btn_explain.clicked.connect(lambda: self._accept_with_mode("explain"))

        self._btn_analyze = QPushButton("🔍 鉴屎官")
        self._btn_analyze.setFixedHeight(34)
        self._btn_analyze.setEnabled(False)
        self._btn_analyze.setDefault(True)
        self._btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_analyze.setStyleSheet(
            "QPushButton { background: #1e1a2e; color: #cba6f7; border: 1px solid #cba6f7;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 18px; }"
            "QPushButton:hover { background: #2e1a4e; border-color: #d4b6ff; color: #d4b6ff; }"
            + _disabled_style
        )
        self._btn_analyze.clicked.connect(lambda: self._accept_with_mode("analyze"))

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._btn_summarize)
        btn_row.addWidget(self._btn_explain)
        btn_row.addWidget(self._btn_analyze)
        layout.addLayout(btn_row)

    def get_image(self) -> Image.Image | None:
        return self._image
