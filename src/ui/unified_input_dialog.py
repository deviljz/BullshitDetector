"""unified_input_dialog.py —— 统一输入对话框

支持文字/链接 + 图片（多张）混合输入。
Alt+V 触发，自动填充剪贴板内容（图片或文字）。
"""
import io

from PIL import Image
from PyQt6.QtCore import Qt, QPoint, QBuffer, QIODeviceBase
from PyQt6.QtGui import QImage, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QTextEdit,
)

_THUMB_W = 120
_THUMB_H = 90


def _qimage_to_pil(qimg: QImage) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
    qimg.save(buf, "PNG")
    buf.seek(0)
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")


class _ThumbWidget(QFrame):
    """单张图片缩略图 + X 删除按钮"""

    def __init__(self, img: Image.Image, on_remove, parent=None):
        super().__init__(parent)
        self._img = img
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        thumb = img.copy()
        thumb.thumbnail((_THUMB_W, _THUMB_H), Image.LANCZOS)
        w, h = thumb.size
        data = thumb.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix_lbl = QLabel()
        pix_lbl.setPixmap(QPixmap.fromImage(qimg))
        pix_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix_lbl.setFixedSize(_THUMB_W, _THUMB_H)
        pix_lbl.setStyleSheet("background: #0a0a14; border-radius: 4px;")
        layout.addWidget(pix_lbl)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        size_lbl = QLabel(f"{img.width}×{img.height}")
        size_lbl.setStyleSheet("color: #585b70; font-size: 10px;")
        bottom.addWidget(size_lbl)
        bottom.addStretch()
        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(16, 16)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rm_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 8px;"
            " font-size: 9px; padding: 0; border: none; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        rm_btn.clicked.connect(on_remove)
        bottom.addWidget(rm_btn)
        layout.addLayout(bottom)

        self.setFixedWidth(_THUMB_W + 8)
        self.setStyleSheet("QFrame { background: #181825; border-radius: 6px; }")

    def image(self) -> Image.Image:
        return self._img


class UnifiedInputDialog(QDialog):
    """统一输入对话框：文字/链接 + 图片（多张），自动填充剪贴板。"""

    def __init__(self, parent=None, preloaded_image: "Image.Image | None" = None):
        super().__init__(parent)
        self._images: list[Image.Image] = []
        self._thumb_widgets: list[_ThumbWidget] = []
        self._drag_pos = QPoint()
        self.selected_mode = "analyze"
        self._fetched_text: str | None = None

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
        self.setMinimumWidth(520)
        self.adjustSize()
        if preloaded_image is not None:
            self._add_image(preloaded_image)
        else:
            self._try_load_clipboard()

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(1.0)

    # ── 拖拽 ──────────────────────────────────────────────────────────────────

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
            for url in md.urls():
                path = url.toLocalFile()
                if path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')):
                    try:
                        self._add_image(Image.open(path).convert("RGB"))
                    except Exception:
                        pass
        elif md.hasImage():
            self._add_image(_qimage_to_pil(QImage(md.imageData())))

    # ── 拖动窗口 ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()

    # ── 键盘 ──────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._try_load_clipboard()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    # ── 内部 ──────────────────────────────────────────────────────────────────

    def _try_load_clipboard(self):
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        qimg = cb.image()
        if not qimg.isNull():
            self._add_image(_qimage_to_pil(qimg))
            return
        text = cb.text().strip()
        if text and not self._text_edit.toPlainText().strip():
            self._text_edit.setPlainText(text)

    def _add_image(self, img: Image.Image):
        tw = _ThumbWidget(img, on_remove=lambda: self._remove_image(tw))
        self._images.append(img)
        self._thumb_widgets.append(tw)
        self._thumb_container_layout.addWidget(tw)
        self._image_strip.setVisible(True)
        self._drop_hint.setVisible(False)
        self._update_buttons()
        self.adjustSize()

    def _remove_image(self, tw: _ThumbWidget):
        idx = self._thumb_widgets.index(tw)
        self._images.pop(idx)
        self._thumb_widgets.pop(idx)
        self._thumb_container_layout.removeWidget(tw)
        tw.deleteLater()
        has_imgs = len(self._images) > 0
        self._image_strip.setVisible(has_imgs)
        self._drop_hint.setVisible(not has_imgs)
        self._update_buttons()
        self.adjustSize()

    def _accept_with_mode(self, mode: str):
        self.selected_mode = mode
        raw = self._text_edit.toPlainText().strip()
        if raw:
            if raw.startswith(("http://", "https://")) and "\n" not in raw:
                from text_fetcher import fetch_article
                self._fetched_text = fetch_article(raw)
            else:
                self._fetched_text = raw
        self.accept()

    def _update_buttons(self):
        has_content = bool(self._images) or bool(self._text_edit.toPlainText().strip())
        for btn in (self._btn_summarize, self._btn_explain, self._btn_source, self._btn_analyze):
            btn.setEnabled(has_content)

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
        layout.setSpacing(10)

        # 标题行
        title_row = QHBoxLayout()
        title = QLabel("📋  分析")
        title.setStyleSheet("color: #cba6f7; font-size: 15px; font-weight: bold;")
        title_row.addWidget(title)
        title_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; border-radius: 11px;"
            " font-size: 11px; border: none; }"
            "QPushButton:hover { background: #ff5555; color: #fff; }"
        )
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        # 文字输入区
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText(
            "粘贴文字、链接…（可留空，只分析图片）\n"
            "http(s):// 开头的链接将自动提取正文"
        )
        self._text_edit.setMinimumHeight(72)
        self._text_edit.setMaximumHeight(150)
        self._text_edit.setStyleSheet(
            "QTextEdit { background: #181825; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 6px; padding: 8px; font-size: 13px; }"
            "QTextEdit:focus { border: 1px solid #cba6f7; }"
        )
        self._text_edit.textChanged.connect(self._update_buttons)
        layout.addWidget(self._text_edit)

        # 图片拖放提示（无图时显示）
        self._drop_hint = QLabel("拖拽图片到这里，或按 Ctrl+V 粘贴图片（支持多张）")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setStyleSheet(
            "color: #585b70; font-size: 12px; padding: 10px;"
            " border: 1px dashed #3a3a55; border-radius: 6px; background: #13131f;"
        )
        layout.addWidget(self._drop_hint)

        # 图片缩略图横排（有图时显示）
        self._image_strip = QScrollArea()
        self._image_strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._image_strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._image_strip.setWidgetResizable(True)
        self._image_strip.setFixedHeight(_THUMB_H + 44)
        self._image_strip.setStyleSheet(
            "QScrollArea { background: #13131f; border: 1px solid #3a3a55; border-radius: 6px; }"
        )
        container = QWidget()
        self._thumb_container_layout = QHBoxLayout(container)
        self._thumb_container_layout.setContentsMargins(6, 6, 6, 6)
        self._thumb_container_layout.setSpacing(6)
        self._thumb_container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._image_strip.setWidget(container)
        self._image_strip.setVisible(False)
        layout.addWidget(self._image_strip)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #313244;")
        layout.addWidget(line)

        # 按钮行
        _dis = "QPushButton:disabled { color: #45475a; border-color: #313244; background: #1a1a2e; }"
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background: #2a2a3e; color: #6c7086; border: 1px solid #3a3a55;"
            " border-radius: 6px; font-size: 13px; padding: 0 16px; }"
            "QPushButton:hover { background: #333355; color: #cdd6f4; }"
        )
        cancel_btn.clicked.connect(self.reject)

        self._btn_summarize = QPushButton("📝 总结")
        self._btn_summarize.setFixedHeight(34)
        self._btn_summarize.setEnabled(False)
        self._btn_summarize.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_summarize.setStyleSheet(
            "QPushButton { background: #1a2e1e; color: #a6e3a1; border: 1px solid #a6e3a1;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 16px; }" + _dis
        )
        self._btn_summarize.clicked.connect(lambda: self._accept_with_mode("summarize"))

        self._btn_explain = QPushButton("❓ 解释")
        self._btn_explain.setFixedHeight(34)
        self._btn_explain.setEnabled(False)
        self._btn_explain.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_explain.setStyleSheet(
            "QPushButton { background: #1a2a3e; color: #89b4fa; border: 1px solid #89b4fa;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 16px; }" + _dis
        )
        self._btn_explain.clicked.connect(lambda: self._accept_with_mode("explain"))

        self._btn_source = QPushButton("🎬 求出处")
        self._btn_source.setFixedHeight(34)
        self._btn_source.setEnabled(False)
        self._btn_source.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_source.setStyleSheet(
            "QPushButton { background: #2e1e0e; color: #fab387; border: 1px solid #fab387;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 12px; }"
            "QPushButton:hover { background: #3e2a0e; border-color: #fac397; color: #fac397; }"
            + _dis
        )
        self._btn_source.clicked.connect(lambda: self._accept_with_mode("source"))

        self._btn_analyze = QPushButton("🔍 鉴屎官")
        self._btn_analyze.setFixedHeight(34)
        self._btn_analyze.setEnabled(False)
        self._btn_analyze.setDefault(True)
        self._btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_analyze.setStyleSheet(
            "QPushButton { background: #1e1a2e; color: #cba6f7; border: 1px solid #cba6f7;"
            " border-radius: 6px; font-size: 13px; font-weight: bold; padding: 0 16px; }" + _dis
        )
        self._btn_analyze.clicked.connect(lambda: self._accept_with_mode("analyze"))

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._btn_summarize)
        btn_row.addWidget(self._btn_explain)
        btn_row.addWidget(self._btn_source)
        btn_row.addWidget(self._btn_analyze)
        layout.addLayout(btn_row)

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def get_images(self) -> list[Image.Image]:
        return list(self._images)

    def get_text(self) -> str:
        if self._fetched_text is not None:
            return self._fetched_text
        return self._text_edit.toPlainText().strip()

    def has_images(self) -> bool:
        return len(self._images) > 0

    def has_text(self) -> bool:
        return bool(self._text_edit.toPlainText().strip())
