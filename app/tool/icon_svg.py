"""Иконка приложения: векторный рисунок (прибор со светящейся дугой и надписью OBD).
Пишет два SVG: фон и передний план адаптивной иконки Android (поле 108x108, видимый круг ~72).
Рендер в PNG — tool/make_icon.py (через headless Chrome)."""
import math, sys, os

out = sys.argv[1]
cx, cy, r = 54, 57, 24

def pt(a, rr):
    a = math.radians(a)
    return cx + rr * math.cos(a), cy + rr * math.sin(a)

x0, y0 = pt(135, r)
x1, y1 = pt(405, r)
arc = f'M {x0:.2f} {y0:.2f} A {r} {r} 0 1 1 {x1:.2f} {y1:.2f}'
ticks = ''.join(
    f'<path d="M {pt(a, 17.5)[0]:.2f} {pt(a, 17.5)[1]:.2f} L {pt(a, 20.5)[0]:.2f} {pt(a, 20.5)[1]:.2f}"/>'
    for a in range(135, 406, 45))
nx, ny = pt(305, 19)
# стрелка — узкий треугольник от центра
px, py = pt(305 + 90, 2.4)
qx, qy = pt(305 - 90, 2.4)

background = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108" width="1024" height="1024">
<defs>
 <radialGradient id="bg" cx="0.38" cy="0.3" r="0.85">
  <stop offset="0" stop-color="#2A2F7A"/><stop offset="0.55" stop-color="#141A3D"/><stop offset="1" stop-color="#070A16"/>
 </radialGradient>
 <radialGradient id="glow" cx="0.5" cy="0.53" r="0.42">
  <stop offset="0" stop-color="#22D3EE" stop-opacity="0.22"/><stop offset="1" stop-color="#22D3EE" stop-opacity="0"/>
 </radialGradient>
</defs>
<rect width="108" height="108" fill="url(#bg)"/>
<rect width="108" height="108" fill="url(#glow)"/>
</svg>'''

foreground = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108" width="1024" height="1024">
<defs>
 <linearGradient id="arc" x1="0" y1="1" x2="1" y2="1">
  <stop offset="0" stop-color="#22D3EE"/><stop offset="0.55" stop-color="#8B5CF6"/><stop offset="1" stop-color="#F472B6"/>
 </linearGradient>
 <filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2"/></filter>
 <filter id="blurS" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.2"/></filter>
</defs>
<path d="{arc}" fill="none" stroke="#1E2650" stroke-width="7" stroke-linecap="round"/>
<path d="{arc}" fill="none" stroke="url(#arc)" stroke-width="8" stroke-linecap="round" filter="url(#blur)" opacity="0.85"/>
<path d="{arc}" fill="none" stroke="url(#arc)" stroke-width="5.5" stroke-linecap="round"/>
<g stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="1.4" stroke-linecap="round">{ticks}</g>
<path d="M {px:.2f} {py:.2f} L {nx:.2f} {ny:.2f} L {qx:.2f} {qy:.2f} Z" fill="#F472B6" filter="url(#blurS)"/>
<path d="M {px:.2f} {py:.2f} L {nx:.2f} {ny:.2f} L {qx:.2f} {qy:.2f} Z" fill="#FFFFFF"/>
<circle cx="{cx}" cy="{cy}" r="4.2" fill="#FFFFFF"/>
<circle cx="{cx}" cy="{cy}" r="1.9" fill="#141A3D"/>
<text x="54" y="84.5" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-weight="800"
      font-size="9.5" letter-spacing="1.2" fill="#FFFFFF">OBD</text>
</svg>'''

for name, svg in (('bg', background), ('fg', foreground)):
    with open(os.path.join(out, f'icon_{name}.svg'), 'w') as f:
        f.write(svg)
    with open(os.path.join(out, f'icon_{name}.html'), 'w') as f:
        f.write('<!doctype html><html><body style="margin:0;background:transparent">' + svg + '</body></html>')
print('ok')
