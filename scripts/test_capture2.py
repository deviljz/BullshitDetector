"""
精确验证 grabWindow 返回的 pixmap 是逻辑像素还是物理像素，
以及 copy() 坐标是否与 event.pos() 的逻辑像素坐标系一致。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

app = QApplication(sys.argv)
out_dir = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out_dir, exist_ok=True)

for i, screen in enumerate(app.screens()):
    g = screen.geometry()
    dpr = screen.devicePixelRatio()
    print(f"\n=== 屏幕{i} ===")
    print(f"  geometry (logical): ({g.x()},{g.y()}) {g.width()}x{g.height()}")
    print(f"  devicePixelRatio: {dpr}")
    print(f"  物理分辨率: {int(g.width()*dpr)}x{int(g.height()*dpr)}")

    full = screen.grabWindow(0)
    print(f"  grabWindow(0) pixmap.width()={full.width()}, .height()={full.height()}")
    print(f"  grabWindow(0) pixmap.devicePixelRatio()={full.devicePixelRatio()}")
    # 如果 pixmap 是逻辑像素，width() 应等于 g.width()=2560
    # 如果 pixmap 是物理像素，width() 应等于 g.width()*dpr=3840
    if full.width() == g.width():
        print(f"  -> pixmap 是【逻辑像素】坐标")
    elif full.width() == int(g.width() * dpr):
        print(f"  -> pixmap 是【物理像素】坐标 (DPR={dpr})")
    else:
        print(f"  -> 未知坐标系！")

    # 在屏幕左上角 1/4 处截一个 100x100 区域，两种坐标法都试一次
    # 方法A: 用逻辑坐标 (logical 1/4 position)
    lx = g.width() // 4
    ly = g.height() // 4
    cropA = full.copy(lx, ly, 100, 100)
    pathA = os.path.join(out_dir, f"screen{i}_logical_crop.png")
    cropA.save(pathA)

    # 方法B: 用物理坐标 (logical * dpr)
    px = int(lx * dpr)
    py = int(ly * dpr)
    cropB = full.copy(px, py, int(100 * dpr), int(100 * dpr))
    pathB = os.path.join(out_dir, f"screen{i}_physical_crop.png")
    cropB.save(pathB)

    print(f"  裁剪位置: 逻辑({lx},{ly}) / 物理({px},{py})")
    print(f"  保存: {pathA}")
    print(f"        {pathB}")
    print(f"  (请对比两张图，看哪张与屏幕左上1/4处的实际内容一致)")

app.quit()
