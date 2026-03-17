"""
生成 assets/icon.ico —— 与托盘图标同风格的 💩 暗色圆形图标。
在 build.bat 中自动调用，无需手动执行。
"""
from PIL import Image, ImageDraw, ImageFont
import os

SIZES = [256, 128, 64, 48, 32, 16]
OUT = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")


def make_frame(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))  # 透明底
    draw = ImageDraw.Draw(img)

    emoji = "💩"
    font_size = int(size * 0.8)
    font = None
    for font_path in [
        r"C:\Windows\Fonts\seguiemj.ttf",   # Segoe UI Emoji
        r"C:\Windows\Fonts\segoeui.ttf",
    ]:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                pass

    if font:
        bbox = draw.textbbox((0, 0), emoji, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size - tw) // 2 - bbox[0]
        y = (size - th) // 2 - bbox[1]
        draw.text((x, y), emoji, font=font, embedded_color=True)
    else:
        # 无 emoji 字体时用黄色圆圈占位
        r = size // 3
        cx, cy = size // 2, size // 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(249, 226, 175, 255))

    return img


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames = [make_frame(s) for s in SIZES]
    frames[0].save(
        OUT,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )
    print(f"Icon saved: {OUT}")


if __name__ == "__main__":
    main()
