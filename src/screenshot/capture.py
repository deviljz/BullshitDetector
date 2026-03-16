import io
import base64

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor
from PIL import Image


class ScreenshotOverlay(QWidget):
    """全屏半透明遮罩，用户拖拽选择截图区域。"""

    def __init__(self, on_capture, on_cancel=None):
        super().__init__()
        self._on_capture = on_capture
        self._on_cancel = on_cancel
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

        # 只覆盖光标当前所在的屏幕，避免跨屏虚拟桌面的混合坐标系问题
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QCursor
        app = QApplication.instance()
        screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
        self.setGeometry(screen.geometry())
        self.show()
        self.activateWindow()
        self.setFocus()

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
        if event.button() == Qt.MouseButton.RightButton:
            if self._on_cancel:
                self._on_cancel()
            self.close()
            return
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
            # widget 覆盖单块屏幕，widget-local 坐标 = 屏幕本地坐标
            # geometry().topLeft() 即该屏幕在全局坐标系中的原点，平移即可得全局坐标
            offset = self.geometry().topLeft()
            rect = self._selection.normalized().translated(offset)
            if rect.width() > 10 and rect.height() > 10:
                image = self._grab_region(rect)
                position = (rect.x() + rect.width(), rect.y())
                self._on_capture(image, position)
            else:
                if self._on_cancel:
                    self._on_cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._on_cancel:
                self._on_cancel()
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
        # grabWindow(0) 返回物理像素 pixmap（width=physical），copy() 接受物理坐标
        # rect 是逻辑坐标，需乘 DPR 转物理坐标后裁剪
        dpr = screen.devicePixelRatio()
        full_pixmap = screen.grabWindow(0)
        origin = screen.geometry().topLeft()
        phys_x = round((rect.x() - origin.x()) * dpr)
        phys_y = round((rect.y() - origin.y()) * dpr)
        phys_w = round(rect.width() * dpr)
        phys_h = round(rect.height() * dpr)
        cropped = full_pixmap.copy(phys_x, phys_y, phys_w, phys_h)
        buf = QBuffer()
        buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
        cropped.save(buf, "PNG")
        buf.seek(0)
        return Image.open(BytesIO(bytes(buf.data()))).convert("RGB")


def image_to_base64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
