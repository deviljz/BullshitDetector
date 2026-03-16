"""
验证截图坐标逻辑：抓取各屏幕中心区域并保存，人工确认是否正确。
运行：cd tests && python test_capture.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

app = QApplication(sys.argv)

screens = app.screens()
print(f"检测到 {len(screens)} 个屏幕：")
for i, s in enumerate(screens):
    g = s.geometry()
    print(f"  屏幕{i}: origin=({g.x()},{g.y()}) size={g.width()}x{g.height()} dpr={s.devicePixelRatio()}")

from screenshot.capture import ScreenshotOverlay

out_dir = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out_dir, exist_ok=True)

for i, screen in enumerate(screens):
    g = screen.geometry()
    # 抓取屏幕中心 200x200 区域
    cx = g.x() + g.width() // 2
    cy = g.y() + g.height() // 2
    rect = QRect(cx - 100, cy - 100, 200, 200)
    print(f"\n屏幕{i} 中心区域 global rect: ({rect.x()},{rect.y()}) {rect.width()}x{rect.height()}")

    img = ScreenshotOverlay._grab_region(rect)
    path = os.path.join(out_dir, f"screen{i}_center.png")
    img.save(path)
    print(f"  已保存：{path}")

print("\n请打开 tests/capture_test_output/ 目录检查图像是否与屏幕中心内容一致。")
app.quit()
