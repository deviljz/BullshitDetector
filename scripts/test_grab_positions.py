"""
在多个已知位置截图，并与 screen.grabWindow(0) 全屏参考图对比，
确认 copy() 使用的是逻辑坐标还是物理坐标。
测试方法：把全屏截图切成 3×3 网格（9 块），每块用 _grab_region 截取，
再从全屏参考图裁出同样区域，比较像素差值。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QBuffer, QIODeviceBase
from PIL import Image, ImageChops
import io

app = QApplication(sys.argv)
out = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out, exist_ok=True)

from screenshot.capture import ScreenshotOverlay

screen = app.primaryScreen()
g = screen.geometry()
dpr = screen.devicePixelRatio()
W, H = g.width(), g.height()
print(f"Screen: {W}x{H} logical, DPR={dpr}")

# 1. 全屏参考图（ground truth）
full_px = screen.grabWindow(0)
buf = QBuffer(); buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
full_px.save(buf, "PNG"); buf.seek(0)
ref = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")
ref.save(os.path.join(out, "ref_full.png"))
print(f"Reference full pixmap size: {ref.size} (logical={W}x{H}, physical={int(W*dpr)}x{int(H*dpr)})")

# 2. 用 _grab_region 截 3×3 网格，对比 ref 对应区域
cols, rows = 3, 3
errors = []
for row in range(rows):
    for col in range(cols):
        x = col * (W // cols)
        y = row * (H // rows)
        w = W // cols
        h = H // rows
        rect = QRect(x, y, w, h)

        grabbed = ScreenshotOverlay._grab_region(rect)
        grabbed.save(os.path.join(out, f"grid_{row}_{col}_grabbed.png"))

        # ref 是物理尺寸，同样用物理坐标裁剪（与 _grab_region 修复后一致）
        px, py = round(x*dpr), round(y*dpr)
        pw, ph = round(w*dpr), round(h*dpr)
        ref_crop = ref.crop((px, py, px+pw, py+ph))
        # grabbed 和 ref_crop 应为同样大小，无需 resize
        if grabbed.size != ref_crop.size:
            ref_crop = ref_crop.resize(grabbed.size, Image.LANCZOS)

        # 像素差（手动计算）
        diff_img = ImageChops.difference(grabbed, ref_crop)
        pixels = list(diff_img.getdata())
        diff = sum(sum(p) for p in pixels) / (len(pixels) * 3)
        errors.append((row, col, x, y, w, h, diff))
        print(f"  grid({row},{col}) rect=({x},{y},{w},{h}): mean_pixel_diff={diff:.1f}")

print(f"\n全局平均差: {sum(e[6] for e in errors)/len(errors):.1f}")
print("差值越小，坐标越准确（<5 基本正确，>20 有明显偏移）")

app.quit()
