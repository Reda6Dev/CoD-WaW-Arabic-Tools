# -*- coding: utf-8 -*-
"""Render a text the way the game would, from the patched .ff and the font .iwd (approximation).
Usage: python preview.py patched.ff "نص عربي" out.png [fontname]"""
import sys, os, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from fontlib import find_fonts
from common import encode
ff, text, out = sys.argv[1:4]; name = sys.argv[4] if len(sys.argv) > 4 else 'normalFont'
d = zlib.decompress(open(ff, 'rb').read()[12:]); f = find_fonts(d)[name]
atlas = Image.open(os.path.join(os.path.dirname(out) or '.', 'atlas_preview.png')) if os.path.exists(os.path.join(os.path.dirname(out) or '.', 'atlas_preview.png')) else Image.open(sys.argv[5])
W, H = atlas.size; byletter = {r[0]: r for r in f['recs']}
data = encode(text); x = 8; base = 60; canvas = Image.new('L', (1000, 120), 30)
for ch in data:
    r = byletter.get(ch)
    if not r: continue
    L, x0, y0, dx, pw, ph, _, s0, t0, s1, t1 = r
    if pw and ph:
        g = atlas.crop((round(s0 * W), round(t0 * H), round(s1 * W), round(t1 * H))).resize((pw, ph))
        canvas.paste(Image.new('L', g.size, 255), (x + x0, base + y0), g)
    x += dx
canvas.crop((0, 0, x + 8, 120)).resize(((x + 8) * 3, 360)).save(out)
print('bytes', data[:20], 'width', x)
