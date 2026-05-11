"""
验证 mapToGlobal 能正确还原全局坐标，并验证 _grab_region 在还原后的坐标下能抓到正确内容。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtTest import QTest

app = QApplication(sys.argv)

screens = app.screens()
virtual = screens[0].geometry()
for s in screens[1:]:
    virtual = virtual.united(s.geometry())

results = {}

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
        QTimer.singleShot(200, self.run_checks)

    def run_checks(self):
        out_dir = os.path.join(os.path.dirname(__file__), "capture_test_output")
        os.makedirs(out_dir, exist_ok=True)

        from screenshot.capture import ScreenshotOverlay

        for i, screen in enumerate(app.screens()):
            g = screen.geometry()
            # 屏幕中心的全局坐标
            cx_global = g.x() + g.width() // 2
            cy_global = g.y() + g.height() // 2
            print(f"\n=== Screen{i} center: global=({cx_global},{cy_global}) ===")

            # mapFromGlobal: 全局 → widget-local
            local = self.mapFromGlobal(QPoint(cx_global, cy_global))
            print(f"  mapFromGlobal({cx_global},{cy_global}) = ({local.x()},{local.y()})")

            # mapToGlobal: widget-local → 全局（验证 round-trip）
            back = self.mapToGlobal(local)
            print(f"  mapToGlobal(local)                   = ({back.x()},{back.y()})")
            print(f"  round-trip OK: {back.x()==cx_global and back.y()==cy_global}")

            # 模拟用户在屏幕中心选 200x200 区域：widget-local 坐标
            half = 100
            local_tl = QPoint(local.x() - half, local.y() - half)
            local_br = QPoint(local.x() + half, local.y() + half)
            # 用 mapToGlobal 还原（新修复的逻辑）
            global_tl = self.mapToGlobal(local_tl)
            global_br = self.mapToGlobal(local_br)
            rect = QRect(global_tl, global_br).normalized()
            print(f"  selection widget-local: ({local_tl.x()},{local_tl.y()})→({local_br.x()},{local_br.y()})")
            print(f"  after mapToGlobal: rect=({rect.x()},{rect.y()},{rect.width()},{rect.height()})")
            print(f"  expected:          rect=({cx_global-half},{cy_global-half},200,200)")
            ok = (rect.x()==cx_global-half and rect.y()==cy_global-half and rect.width()==200 and rect.height()==200)
            print(f"  coord fix OK: {ok}")

            # 实际截图验证
            img = ScreenshotOverlay._grab_region(rect)
            path = os.path.join(out_dir, f"screen{i}_center_fixed.png")
            img.save(path)
            print(f"  saved: {path}")

        app.quit()

w = TestOverlay()
sys.exit(app.exec())
