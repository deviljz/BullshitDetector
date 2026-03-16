"""
验证单屏 overlay 的坐标映射是否正确：
widget-local 坐标 + geometry().topLeft() = 全局坐标
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QCursor

app = QApplication(sys.argv)

out_dir = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out_dir, exist_ok=True)

from screenshot.capture import ScreenshotOverlay

for i, screen in enumerate(app.screens()):

    class TestOverlay(QWidget):
        def __init__(self, scr, idx):
            super().__init__()
            self._scr = scr
            self._idx = idx
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setGeometry(scr.geometry())
            self.show()
            QTimer.singleShot(200, self.check)

        def check(self):
            g = self.geometry()
            sg = self._scr.geometry()
            cx_global = sg.x() + sg.width() // 2
            cy_global = sg.y() + sg.height() // 2

            # mapFromGlobal 验证 widget-local = global - topLeft
            local = self.mapFromGlobal(QPoint(cx_global, cy_global))
            expected_local_x = cx_global - g.x()
            expected_local_y = cy_global - g.y()

            print(f"\n=== Screen{self._idx} ===")
            print(f"  geometry: {g}")
            print(f"  screen center global: ({cx_global},{cy_global})")
            print(f"  mapFromGlobal → local: ({local.x()},{local.y()})")
            print(f"  expected local:        ({expected_local_x},{expected_local_y})")
            coord_ok = local.x() == expected_local_x and local.y() == expected_local_y
            print(f"  1:1 mapping OK: {coord_ok}")

            # 截取屏幕中心 200x200 并验证
            half = 100
            rect_global = QRect(cx_global - half, cy_global - half, 200, 200)
            img = ScreenshotOverlay._grab_region(rect_global)
            path = os.path.join(out_dir, f"screen{self._idx}_singleoverlay.png")
            img.save(path)
            print(f"  capture saved: {path}")

            self.close()
            app.quit()

    w = TestOverlay(screen, i)
    # 只测一块屏就够了（主屏）
    break

sys.exit(app.exec())
