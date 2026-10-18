"""Раскладывает иконку по размерам Android (адаптивная + обычная).

  python app/tool/icon_svg.py <папка>            # SVG фона и переднего плана
  (рендер SVG -> icon_bg.png / icon_fg.png 1024x1024 через headless Chrome)
  python app/tool/make_icon.py <папка>           # mipmap-* в android/app/src/main/res
"""
import os, sys
from PIL import Image

src = sys.argv[1]
RES = os.path.join(os.path.dirname(__file__), '..', 'android', 'app', 'src', 'main', 'res')
bg = Image.open(os.path.join(src, 'icon_bg.png')).convert('RGBA')
fg = Image.open(os.path.join(src, 'icon_fg.png')).convert('RGBA')

for d, px in {'mdpi': 108, 'hdpi': 162, 'xhdpi': 216, 'xxhdpi': 324, 'xxxhdpi': 432}.items():
    folder = os.path.join(RES, f'mipmap-{d}')
    os.makedirs(folder, exist_ok=True)
    fg.resize((px, px), Image.LANCZOS).save(os.path.join(folder, 'ic_launcher_foreground.png'))
    bg.resize((px, px), Image.LANCZOS).save(os.path.join(folder, 'ic_launcher_background.png'))

# обычная иконка (старые Android): видимая часть 72 из 108, целиком
full = bg.copy()
full.alpha_composite(fg)
s = full.size[0]
off = int(s * 18 / 108)
legacy = full.crop((off, off, s - off, s - off))
for d, px in {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}.items():
    legacy.resize((px, px), Image.LANCZOS).convert('RGB').save(os.path.join(RES, f'mipmap-{d}', 'ic_launcher.png'))
print('ok')
