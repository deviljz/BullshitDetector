"""
生成可视化截图报告：左侧全屏参考图（标注了测试区域），右侧对应的 _grab_region 捕获预览。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QBuffer, QIODeviceBase
from PIL import Image, ImageDraw, ImageFont
import io

app = QApplication(sys.argv)
out = os.path.join(os.path.dirname(__file__), "capture_test_output")
os.makedirs(out, exist_ok=True)

from screenshot.capture import ScreenshotOverlay

screen = app.primaryScreen()
g = screen.geometry()
W, H = g.width(), g.height()
dpr = screen.devicePixelRatio()

# 1. 全屏参考图（物理像素）
full_px = screen.grabWindow(0)
buf = QBuffer(); buf.open(QIODeviceBase.OpenModeFlag.ReadWrite)
full_px.save(buf, "PNG"); buf.seek(0)
ref_phys = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")
# 缩小到逻辑尺寸用于标注
ref_logical = ref_phys.resize((W, H), Image.LANCZOS)

# 2. 测试区域：9 个位置（左/中/右 × 上/中/下），每个 300x200 逻辑像素
TW, TH = 300, 200
test_rects = []
for row, ry in enumerate([50, H//2 - TH//2, H - TH - 50]):
    for col, rx in enumerate([50, W//2 - TW//2, W - TW - 50]):
        test_rects.append((row * 3 + col + 1, QRect(rx, ry, TW, TH)))

# 3. 截取各区域
previews = []
for idx, rect in test_rects:
    img = ScreenshotOverlay._grab_region(rect)
    previews.append((idx, rect, img))

# 4. 在参考图上标注矩形和编号
annotated = ref_logical.copy()
draw = ImageDraw.Draw(annotated)
colors = ["#FF4444","#FF8800","#FFCC00","#44FF44","#00CCFF","#8844FF","#FF44AA","#44FFAA","#FFFFFF"]
for idx, rect, _ in previews:
    c = colors[(idx-1) % len(colors)]
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    draw.rectangle([x, y, x+w, y+h], outline=c, width=3)
    draw.rectangle([x+2, y+2, x+28, y+22], fill=c)
    draw.text((x+5, y+3), str(idx), fill="black")

# 5. 合并：左侧标注全屏，右侧 3 列预览
PREV_W, PREV_H = 300, 200  # 预览统一缩放到此尺寸
COLS = 3
ROWS = 3
PAD = 10
panel_w = PREV_W * COLS + PAD * (COLS + 1)
panel_h = (PREV_H + 30) * ROWS + PAD * (ROWS + 1)
left_w = W
left_h = H
scale = min(panel_h / left_h, 1.0)
left_disp_w = int(left_w * scale)
left_disp_h = int(left_h * scale)
annotated_scaled = annotated.resize((left_disp_w, left_disp_h), Image.LANCZOS)

total_w = left_disp_w + PAD + panel_w
total_h = max(left_disp_h, panel_h)
canvas = Image.new("RGB", (total_w, total_h), (30, 30, 40))
canvas.paste(annotated_scaled, (0, (total_h - left_disp_h) // 2))

draw2 = ImageDraw.Draw(canvas)
for i, (idx, rect, prev_img) in enumerate(previews):
    col = i % COLS
    row = i // COLS
    px = left_disp_w + PAD + col * (PREV_W + PAD) + PAD
    py = row * (PREV_H + 30 + PAD) + PAD
    c = colors[(idx-1) % len(colors)]
    # 预览边框
    canvas.paste(Image.new("RGB", (PREV_W + 4, PREV_H + 4), c), (px - 2, py - 2))
    # 缩放预览
    thumb = prev_img.resize((PREV_W, PREV_H), Image.LANCZOS)
    canvas.paste(thumb, (px, py))
    # 标签
    draw2.text((px, py + PREV_H + 2), f"#{idx} ({rect.x()},{rect.y()},{rect.width()},{rect.height()})", fill=c)

report_path = os.path.join(out, "visual_report.png")
canvas.save(report_path)
print(f"报告已保存: {report_path}")
app.quit()
