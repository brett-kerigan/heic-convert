"""Generate packaging/heic-convert.ico — a green 'H' on CRT black. Run once; the .ico is committed."""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (5, 10, 5, 255))
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype(
        os.path.join(os.path.dirname(__file__), "..", "static", "vendor", "VT323-Regular.ttf"), 210)
except OSError:
    font = ImageFont.load_default()
d.text((SIZE / 2, SIZE / 2 - 10), "H", font=font, fill=(56, 240, 110, 255), anchor="mm")
out = os.path.join(os.path.dirname(__file__), "heic-convert.ico")
img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
