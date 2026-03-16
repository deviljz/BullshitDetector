import io
import base64

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor
import mss
from PIL import Image


class ScreenshotOverlay(QWidget):
    """全屏半透明遮罩，用户拖拽选择截图区域。"""

    def __init__(self, on_capture):
        super().__init__()
        self._on_capture = on_capture
        self._origin = QPoint()
        self._selection = QRect()
        self._is_selecting = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 覆盖所有屏幕组成的虚拟桌面（多屏支持）
        from PyQt6.QtWidgets import QApplication
        virtual = QApplication.instance().screens()[0].geometry()
        for screen in QApplication.instance().screens()[1:]:
            virtual = virtual.united(screen.geometry())
        self.setGeometry(virtual)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if not self._selection.isNull():
            rect = self._selection.normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # 亮青色 2px 边框
            from PyQt6.QtGui import QPen
            pen = QPen(QColor(0, 255, 220), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
            # 尺寸提示文字
            if rect.width() > 60 and rect.height() > 30:
                painter.setPen(QColor(0, 255, 220))
                painter.setFont(painter.font())
                painter.drawText(
                    rect.x() + 4,
                    rect.y() + 16,
                    f"{rect.width()} × {rect.height()}",
                )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._selection = QRect(self._origin, self._origin)
            self._is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._is_selecting:
            self._selection = QRect(self._origin, event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self.close()
            # _selection 是 widget-local 逻辑像素，转为全局坐标
            offset = self.geometry().topLeft()
            rect = self._selection.normalized().translated(offset)
            if rect.width() > 10 and rect.height() > 10:
                image = self._grab_region(rect)
                position = (rect.x() + rect.width(), rect.y())
                self._on_capture(image, position)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    @staticmethod
    def _grab_region(rect: QRect) -> Image.Image:
        """rect 为全局逻辑像素坐标。
        先抓取整个屏幕，再裁剪选择区域，避免坐标系混淆。
        grabWindow(0, x, y, w, h) 的 x/y 是相对于该屏幕的局部坐标，
        而 rect 是全局坐标，必须减去屏幕原点才能正确裁剪。"""
        from io import BytesIO
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QBuffer, QIODeviceBase

        app = QApplication.instance()
        screen = app.screenAt(rect.center()) or app.primaryScreen()
        # 抓取该屏幕全图，然后用屏幕局部坐标裁剪
        full_pixmap = screen.grabWindow(0)
        origin = screen.geometry().topLeft()
        local_x = rect.x() - origin.x()
        local_y = rect.y() - origin.y()
        cropped = full_pixmap.copy(local_x, local_y, rect.width(), rect.height())
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
        cropped.save(buf, "PNG")
        buf.seek(0)
        return Image.open(BytesIO(bytes(buf.data()))).convert("RGB")


def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
