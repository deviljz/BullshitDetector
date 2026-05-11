"""
改进版可视化报告：
- 左列 = 从全屏参考图裁出"应该捕获的区域"
- 右列 = _grab_region 实际捕获结果
- 两列内容应完全一致；不一致说明坐标有偏移
- 跳过内容过于空白的区域（标准差 < 8）
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QBuffer, QIODeviceBase
from PIL import Image, ImageDraw, ImageStat
import io, math

app = QApplication(sys.argv)
out = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out, exist_ok=True)

from screenshot.capture import ScreenshotOverlay
screen = app.primaryScreen()
g = screen.geometry()
W, H = g.width(), g.height()
dpr = screen.devicePixelRatio()

# 全屏参考（物理像素）
full_px = screen.grabWindow(0)
buf = QBuffer(); buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
full_px.save(buf, "PNG"); buf.seek(0)
ref_phys = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")  # 3840×2160
ref_logical = ref_phys.resize((W, H), Image.LANCZOS)  # 2560×1440

def is_blank(img, threshold=8):
    stat = ImageStat.Stat(img)
    return max(stat.stddev) < threshold

# 候选区域：大块 600×400，遍历直到找到 6 个非空白
TW, TH = 600, 400
candidates = []
step_x = W // 4
step_y = H // 3
for row in range(3):
    for col in range(4):
        cx = col * step_x + step_x // 2 - TW // 2
        cy = row * step_y + step_y // 2 - TH // 2
        cx = max(0, min(cx, W - TW))
        cy = max(0, min(cy, H - TH))
        candidates.append(QRect(cx, cy, TW, TH))

chosen = []
for rect in candidates:
    # 从参考图裁出这块
    px = round(rect.x() * dpr)
    py = round(rect.y() * dpr)
    pw = round(rect.width() * dpr)
    ph = round(rect.height() * dpr)
    ref_crop = ref_phys.crop((px, py, px+pw, py+ph)).resize((TW, TH), Image.LANCZOS)
    if not is_blank(ref_crop):
        chosen.append(rect)
    if len(chosen) >= 6:
        break

print(f"选定 {len(chosen)} 个非空白区域")

# 报告布局
COL_W = TW + 20
PAD = 16
LABEL_H = 24
ROW_H = TH + LABEL_H + PAD
canvas_w = PAD + COL_W + PAD + COL_W + PAD
canvas_h = PAD + len(chosen) * ROW_H
canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 30))
draw = ImageDraw.Draw(canvas)

colors = ["#FF4444","#FF8800","#FFCC00","#44FF44","#00CCFF","#FF44FF"]

for i, rect in enumerate(chosen):
    y_off = PAD + i * ROW_H
    c = colors[i % len(colors)]
    label = f"#{i+1} ({rect.x()},{rect.y()}) {rect.width()}×{rect.height()}"

    # 左列：从参考图裁出（理论上应看到的内容）
    px = round(rect.x() * dpr)
    py = round(rect.y() * dpr)
    pw = round(rect.width() * dpr)
    ph = round(rect.height() * dpr)
    ref_crop = ref_phys.crop((px, py, px+pw, py+ph)).resize((TW, TH), Image.LANCZOS)
    canvas.paste(Image.new("RGB", (TW+4, TH+4), c), (PAD-2, y_off+LABEL_H-2))
    canvas.paste(ref_crop, (PAD, y_off+LABEL_H))
    draw.text((PAD, y_off+2), f"参考 {label}", fill=c)

    # 右列：_grab_region 实际捕获
    grabbed = ScreenshotOverlay._grab_region(rect)
    grabbed_disp = grabbed.resize((TW, TH), Image.LANCZOS)
    rx = PAD + COL_W + PAD
    canvas.paste(Image.new("RGB", (TW+4, TH+4), c), (rx-2, y_off+LABEL_H-2))
    canvas.paste(grabbed_disp, (rx, y_off+LABEL_H))

    # 计算像素差
    from PIL import ImageChops
    diff = ImageChops.difference(ref_crop, grabbed_disp)
    pixels = list(diff.getdata())
    mean_diff = sum(sum(p) for p in pixels) / (len(pixels) * 3)
    draw.text((rx, y_off+2), f"捕获 diff={mean_diff:.1f}", fill=c)

report = os.path.join(out, "visual_report3.png")
canvas.save(report)
print(f"报告: {report}")
app.quit()
