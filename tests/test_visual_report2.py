"""
生成更清晰的可视化报告：每行显示一个测试区域。
左列：全屏中用红框标出的位置（局部放大）；右列：_grab_region 实际捕获的内容。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QBuffer, QIODeviceBase
from PIL import Image, ImageDraw
import io

app = QApplication(sys.argv)
out = os.path.join(os.path.dirname(__file__), "capture_test_output")

from screenshot.capture import ScreenshotOverlay
screen = app.primaryScreen()
g = screen.geometry()
W, H = g.width(), g.height()
dpr = screen.devicePixelRatio()

# 全屏参考（物理像素 → 缩到逻辑尺寸）
full_px = screen.grabWindow(0)
buf = QBuffer(); buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
full_px.save(buf, "PNG"); buf.seek(0)
ref_phys = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")
ref_logical = ref_phys.resize((W, H), Image.LANCZOS)

# 6 个测试区域：角落+边中点，300×200 逻辑像素
TW, TH = 300, 200
test_rects = [
    ("左上角",   QRect(50,        50,          TW, TH)),
    ("右上角",   QRect(W-TW-50,   50,          TW, TH)),
    ("左下角",   QRect(50,        H-TH-50,     TW, TH)),
    ("右下角",   QRect(W-TW-50,   H-TH-50,     TW, TH)),
    ("正中心",   QRect(W//2-TW//2, H//2-TH//2, TW, TH)),
    ("右侧中",   QRect(W-TW-50,   H//2-TH//2,  TW, TH)),
]

# 每行：[全屏缩略图+红框标注] [捕获的预览]
ROW_H = 260
THUMB_W = 480   # 全屏缩略图宽
PREV_W = 450    # 预览宽
PAD = 16
canvas_w = PAD + THUMB_W + PAD + PREV_W + PAD
canvas_h = PAD + len(test_rects) * (ROW_H + PAD)
canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 30))
draw = ImageDraw.Draw(canvas)

for i, (label, rect) in enumerate(test_rects):
    y_off = PAD + i * (ROW_H + PAD)
    color = ["#FF4444","#FF8800","#FFCC00","#44FF44","#00CCFF","#FF44FF"][i]

    # 左：全屏缩略图标注框
    scale_x = THUMB_W / W
    scale_y = (ROW_H - 20) / H
    scale = min(scale_x, scale_y)
    tw = int(W * scale); th = int(H * scale)
    thumb = ref_logical.resize((tw, th), Image.LANCZOS)
    # 在缩略图上画框
    td = ImageDraw.Draw(thumb)
    sx = int(rect.x() * scale); sy = int(rect.y() * scale)
    sw = int(rect.width() * scale); sh = int(rect.height() * scale)
    td.rectangle([sx, sy, sx+sw, sy+sh], outline=color, width=3)
    canvas.paste(thumb, (PAD, y_off + 20))
    draw.text((PAD, y_off + 4), f"#{i+1} {label} ({rect.x()},{rect.y()},{rect.width()},{rect.height()})", fill=color)

    # 右：_grab_region 捕获的预览
    grabbed = ScreenshotOverlay._grab_region(rect)
    prev_h = int(grabbed.height * PREV_W / grabbed.width)
    prev = grabbed.resize((PREV_W, prev_h), Image.LANCZOS)
    px_off = PAD + THUMB_W + PAD
    # 彩色边框
    canvas.paste(Image.new("RGB", (PREV_W+4, prev_h+4), color), (px_off-2, y_off+20-2))
    canvas.paste(prev, (px_off, y_off+20))
    draw.text((px_off, y_off + 4), f"捕获预览 →", fill=color)

report = os.path.join(out, "visual_report2.png")
canvas.save(report)
print(f"报告已保存: {report}")
app.quit()
