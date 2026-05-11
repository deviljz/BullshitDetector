"""
验证 overlay widget 实际 geometry 和 event.pos() 的坐标单位。
不需要用户拖选，程序自动模拟鼠标点击并记录坐标。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtTest import QTest

app = QApplication(sys.argv)

# 重现 overlay 的 setGeometry 逻辑
screens = app.screens()
virtual = screens[0].geometry()
for s in screens[1:]:
    virtual = virtual.united(s.geometry())

print(f"virtual rect (setGeometry target): {virtual}")

class TestOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(virtual)
        self.show()
        # 延迟检查实际 geometry
        QTimer.singleShot(200, self.check_and_quit)

    def check_and_quit(self):
        g = self.geometry()
        print(f"\noverlay.geometry() after show(): {g}")
        print(f"  topLeft = ({g.x()}, {g.y()})")
        print(f"  size    = {g.width()} x {g.height()}")

        # 对比每个屏幕
        for i, s in enumerate(app.screens()):
            sg = s.geometry()
            dpr = s.devicePixelRatio()
            print(f"\n  Screen{i}: geometry={sg}, dpr={dpr}")
            # 屏幕中心点（逻辑坐标）
            cx = sg.x() + sg.width() // 2
            cy = sg.y() + sg.height() // 2
            print(f"    center (logical): ({cx}, {cy})")
            print(f"    center (physical): ({int(cx * dpr)}, {int(cy * dpr)})")
            # 检查 mapFromGlobal：全局逻辑坐标 → 控件本地坐标
            local = self.mapFromGlobal(QPoint(cx, cy))
            print(f"    mapFromGlobal({cx},{cy}) = ({local.x()}, {local.y()})")

        app.quit()

w = TestOverlay()
sys.exit(app.exec())
