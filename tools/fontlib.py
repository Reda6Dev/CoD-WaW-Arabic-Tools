# -*- coding: utf-8 -*-
"""CoD4 Arabic font: slot map, glyph-table patching (sizes never change), atlas + IWi writer."""
import struct, json, os, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import shaper

FONTDIR = os.path.join(HERE, 'fonts')          # DejaVu fonts shipped with the package (free license, see LICENSE_DejaVu.txt)
SANS = os.path.join(FONTDIR, 'DejaVuSans.ttf')
BOLD = os.path.join(FONTDIR, 'DejaVuSans-Bold.ttf')
MONO = os.path.join(FONTDIR, 'DejaVuSansMono.ttf')
UI_FONTS = ['bigFont', 'smallFont', 'boldFont', 'normalFont', 'extraBigFont', 'objectiveFont']
ALL_FONTS = ['consoleFont'] + UI_FONTS
BOLD_FONTS = {'boldFont', 'extraBigFont'}
FREED_ASCII = list('`~|#$@<>=*') + [chr(c) for c in range(65, 91)]     # free ASCII slots: A-Z are given up
RARE = [0xFE89, 0xFE8A, 0xFE8B, 0xFE8C, 0xFEF5, 0xFEF6, 0xFEF9, 0xFEFA]   # least needed forms (hamza-on-yeh, lam-alef madda/hamza-below)

def needed_forms():
    used = set()
    pers = set('پچژگ')
    for b, f in shaper.FORMS.items():
        if b in shaper.ALLOWED and b not in pers: used.update(f.values())
    for l, f in shaper.LIGA.items():
        if l[1] in 'آأإا': used.update(f.values())
    return sorted(used) + [0x060C, 0x061F]

# ---------- locating the fonts inside the decompressed stream ----------
def find_fonts(d):
    out = {}
    for name in ALL_FONTS:
        o = d.find(b'fonts/' + name.encode() + b'\x00')
        if o < 0: continue
        pix, cnt = struct.unpack_from('<II', d, o - 20)[0:2] if False else struct.unpack_from('<II', d, o - 20)
        p = None
        for q in range(o, o + 7000):
            if all(struct.unpack_from('<H', d, q + 24 * i)[0] == 32 + i for i in range(6)): p = q; break
        assert p, name
        recs = [struct.unpack_from('<HbbBBBBffff', d, p + 24 * i) for i in range(cnt)]
        out[name] = {'pos': p, 'count': cnt, 'pix': pix, 'recs': recs}
    return out

def make_slotmap(fonts):
    """Arabic form -> byte code. Codes must exist in every UI font table; rare forms go to codes missing from objectiveFont."""
    sets = {n: {r[0] for r in fonts[n]['recs']} for n in UI_FONTS}
    common_ext = sorted(set.intersection(*[{c for c in s if c > 126} for n, s in sets.items() if n != 'objectiveFont']))
    obj_ext = {c for c in sets['objectiveFont'] if c > 126}
    only_not_obj = [c for c in common_ext if c not in obj_ext]
    in_obj = [c for c in common_ext if c in obj_ext]
    ascii_codes = [ord(c) for c in FREED_ASCII]
    forms = needed_forms()
    rare = [f for f in RARE if f in forms]
    rest = [f for f in forms if f not in rare]
    slots_rare = only_not_obj + in_obj + ascii_codes          # rare forms first take the codes objectiveFont lacks
    mapping = {}
    for f, c in zip(rare, slots_rare): mapping[f] = c
    free = [c for c in slots_rare if c not in mapping.values()]
    assert len(free) >= len(rest), (len(free), len(rest))
    for f, c in zip(rest, free): mapping[f] = c
    return {str(k): v for k, v in mapping.items()}, only_not_obj

# ---------- rendering ----------
EXTRA_PCT = {}      # font name -> extra thickness in percent (font_weight.txt:  smallFont = bold+25)

def read_weights():
    """font_weight.txt: one line per font, e.g.  normalFont = bold   (values: normal | bold | extra)"""
    w = {n: 'normal' for n in ALL_FONTS}; EXTRA_PCT.clear()
    try: txt = open(os.path.join(HERE, 'font_weight.txt'), encoding='utf-8-sig').read()
    except OSError: return w
    for line in txt.split('\n'):
        line = line.split('#')[0].strip()
        if '=' not in line: continue
        k, v = [x.strip() for x in line.split('=', 1)]; v = v.lower().replace(' ', '')
        pct = 0
        if '+' in v:
            v, _, ps = v.partition('+')
            try: pct = int(ps.rstrip('%'))
            except ValueError: sys.exit('font_weight.txt: %r after + must be a number (percent)' % ps)
            if not 0 <= pct <= 100: sys.exit('font_weight.txt: the percent after + must be between 0 and 100')
        if v not in ('normal', 'bold', 'extra'): sys.exit('font_weight.txt: unknown value %r (use normal, bold or extra, optionally +25 for 25 percent thicker)' % v)
        if k.lower() == 'all':
            for n in UI_FONTS: w[n] = v; EXTRA_PCT[n] = pct
        elif k in w: w[k] = v; EXTRA_PCT[k] = pct
        else: sys.exit('font_weight.txt: unknown font %r (%s)' % (k, ', '.join(ALL_FONTS)))
    return w

def read_scales():
    """font_scale.txt: size of the letters, e.g.  all = 0.90  or  smallFont = 0.85  (1.0 = same size as before; smaller = smaller letters)"""
    sc = {n: 1.0 for n in ALL_FONTS}
    try: txt = open(os.path.join(HERE, 'font_scale.txt'), encoding='utf-8-sig').read()
    except OSError: return sc
    for line in txt.split('\n'):
        line = line.split('#')[0].strip()
        if '=' not in line: continue
        k, v = [x.strip() for x in line.split('=', 1)]
        try: f = float(v)
        except ValueError: sys.exit('font_scale.txt: %r is not a number' % v)
        if not 0.4 <= f <= 1.5: sys.exit('font_scale.txt: use a number between 0.4 and 1.5 (you wrote %s)' % v)
        if k.lower() == 'all':
            for n in UI_FONTS: sc[n] = f
        elif k in sc: sc[k] = f
        else: sys.exit('font_scale.txt: unknown font %r (%s)' % (k, ', '.join(ALL_FONTS)))
    return sc

def thicken(im, d4):
    """Makes the strokes of a glyph thicker: the picture is enlarged 4 times, grown by d4 small steps (each = 1/4 pixel) and reduced again.
    Returns (picture, pad) - pad = pixels added on every side."""
    from PIL import ImageFilter
    if d4 <= 0: return im, 0
    pad = (d4 + 3) // 4 + 1
    big = Image.new('L', ((im.size[0] + 2 * pad) * 4, (im.size[1] + 2 * pad) * 4), 0)
    big.paste(im.resize((im.size[0] * 4, im.size[1] * 4), Image.LANCZOS), (pad * 4, pad * 4))
    for _ in range(d4): big = big.filter(ImageFilter.MaxFilter(3))
    return big.resize((big.size[0] // 4, big.size[1] // 4), Image.LANCZOS), pad

def glyph_image(font, ch, sw=0):
    bb = font.getbbox(ch, anchor='ls', stroke_width=sw)
    adv = font.getlength(ch) + sw
    if ch == ' ' or bb is None or bb[2] <= bb[0] or bb[3] <= bb[1]: return None, 0, 0, adv, 0, 0
    l, t, r, b = bb
    im = Image.new('L', (r - l, b - t), 0)
    ImageDraw.Draw(im).text((-l, -t), ch, font=font, fill=255, anchor='ls', stroke_width=sw, stroke_fill=255)
    return im, l, t, adv, r - l, b - t

def build_glyphs(fonts, slotmap, W=512, H=1024, target=48, orig=None):
    """orig = alpha picture of the game's own font image (World at War): its glyphs are kept as they are (original look) and placed in the top
    part of the new, taller atlas; only the Arabic glyphs are drawn new, below it."""
    inv = {v: int(k) for k, v in slotmap.items()}; weights = read_weights(); scales = read_scales()
    while True:
        atlas = Image.new('L', (W, H), 0); st = {'x': 2, 'y': 2, 'rh': 0}; ok = True; new = {}
        if orig is not None:
            atlas.paste(orig, (0, 0)); st['y'] = orig.size[1] + 2; oh = orig.size[1] / H
        def place(im):
            nonlocal ok
            w, h = im.size
            if st['x'] + w + 2 > W: st['x'] = 2; st['y'] += st['rh'] + 2; st['rh'] = 0
            if st['y'] + h + 2 > H: ok = False; return 0, 0
            x, y = st['x'], st['y']; atlas.paste(im, (x, y)); st['x'] += w + 2; st['rh'] = max(st['rh'], h)
            return x, y
        for name in ALL_FONTS:
            f = fonts[name]; recs = f['recs']
            capA = next(r[5] for r in recs if r[0] == ord('H')); capA = max(capA, 5)
            size = capA / 0.729 * scales[name]                   # px that gives the original cap height (times tools/font_scale.txt)
            r = min(1.0, target / size)
            wt = weights[name]
            path = MONO if name == 'consoleFont' else (BOLD if (name in BOLD_FONTS or wt in ('bold', 'extra')) else SANS)
            swu = 0 if wt != 'extra' else max(1, int(round(size / 14)))          # extra: an outline is added around every stroke
            swt = 0 if swu == 0 else max(1, int(round(swu * r)))
            fu = ImageFont.truetype(path, max(4, int(round(size))))            # unit metrics
            ft = ImageFont.truetype(path, max(4, int(round(size * r))))        # texture render
            out = []
            for rec in recs:
                L = rec[0]
                if orig is not None and not (L in inv and name != 'consoleFont'):
                    out.append(tuple(rec[:7]) + (rec[7], rec[8] * oh, rec[9], rec[10] * oh)); continue          # untouched original glyph (picture rows are now half as tall)
                if L in inv and name != 'consoleFont': ch = chr(inv[L])
                elif 32 <= L < 127 and chr(L) not in FREED_ASCII: ch = chr(L)
                else: ch = None
                if name == 'consoleFont' and not (32 <= L < 127): ch = None
                if ch is None: out.append((L, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)); continue
                im_u, x0, y0, adv, w, h = glyph_image(fu, ch, swu)
                dx = int(round(adv))
                if im_u is None: out.append((L, 0, 0, min(dx, 255), 0, 0, 0, 0, 0, 0, 0)); continue
                im_t, *_ = glyph_image(ft, ch, swt)
                pct = EXTRA_PCT.get(name, 0)
                if pct:
                    stem = (0.17 if path == BOLD else 0.11) * size * r                   # stroke width of the letters in the texture (pixels)
                    d4 = int(round(stem * pct / 100 / 2 * 4))                            # growth on each side, in quarter pixels
                    im_t, pad = thicken(im_t, d4)
                    if pad:
                        pu = int(round(pad / r)); x0 -= pu; y0 -= pu; w += 2 * pu; h += 2 * pu      # the picture is bigger: the glyph box grows with it
                px, py = place(im_t)
                out.append((L, x0, y0, min(dx, 255), min(w, 255), min(h, 255), 0,
                            px / W, py / H, (px + im_t.size[0]) / W, (py + im_t.size[1]) / H))
            new[name] = out
        if ok: return atlas, new, target
        target -= 1
        if target < 6: raise RuntimeError('atlas cannot hold the fonts')

GROW_CODES = list(range(128, 151))      # 23 extra character codes: the Arabic shapes that used to sit on the capitals A-W move here

def expand_fonts(fonts, codes=GROW_CODES):
    """Font layout with `codes` added to every UI font table. The file must keep its length, so the same number of bytes is taken
    away from consoleFont (the developer console font: its control/extended characters are not needed by players)."""
    out = {n: dict(f, recs=list(f['recs'])) for n, f in fonts.items()}
    need = 0
    for n in UI_FONTS:
        recs = out[n]['recs']; have = {r[0] for r in recs}
        miss = [c for c in codes if c not in have]          # World at War: smallFont already has codes above 127, only the missing ones are added
        need += len(miss)
        if not miss: continue
        blank = next(r for r in recs if r[0] == 32)
        idx = next((i for i, r in enumerate(recs) if r[0] > miss[-1]), len(recs))
        recs[idx:idx] = [(c,) + tuple(blank[1:]) for c in miss]
    cons = out['consoleFont']['recs']
    removable = sorted((i for i, r in enumerate(cons) if not 32 <= r[0] < 127), key=lambda i: -cons[i][0])
    assert len(removable) >= need, 'consoleFont has too few spare records'
    drop = set(removable[:need])
    out['consoleFont']['recs'] = [r for i, r in enumerate(cons) if i not in drop]
    for n in out: out[n]['count'] = len(out[n]['recs'])
    assert sum(f['count'] for f in out.values()) == sum(f['count'] for f in fonts.values())      # the file keeps its length
    return out

def patch_stream(d, fonts, new):
    """fonts: layout found in the ORIGINAL stream (find_fonts); new: {font name: list of glyph records} (a table may get longer or shorter,
    but the total number of records must stay the same so that nothing after the fonts moves)."""
    order = sorted(new, key=lambda n: fonts[n]['pos'])
    out = bytearray(); prev = 0
    for n in order:
        p = fonts[n]['pos']; e = p + 24 * fonts[n]['count']
        out += d[prev:p]
        for r in new[n]: out += struct.pack('<HbbBBBBffff', *r)
        prev = e
    out += d[prev:]
    assert len(out) == len(d), 'font tables changed the file length'
    for n in order:
        o = out.find(b'fonts/' + n.encode() + b'\x00')
        pix, cnt = struct.unpack_from('<II', out, o - 20); assert cnt == fonts[n]['count'], n
        struct.pack_into('<I', out, o - 16, len(new[n]))
    return bytes(out)

IMG_NAME = b'gamefonts_ar'     # same length as 'gamefonts_pc': our image gets its own name so no other .iwd can shadow it

def rename_image(d):
    old = b'\xffgamefonts_pc\x00'; new = b'\xff' + IMG_NAME + b'\x00'
    if d.count(old) == 1: return d.replace(old, new)
    if d.count(old) == 0 and d.count(new) == 1: return d          # input file was already patched before
    raise AssertionError('image name not found (this .ff has a different font image layout). found original=%d patched=%d' % (d.count(old), d.count(new)))

# ---------- IWi (DXT5 alpha atlas) ----------
def dxt5(alpha):
    h, w = alpha.shape
    if h < 4 or w < 4:
        pad = np.zeros((max(h, 4), max(w, 4)), np.uint8); pad[:] = alpha[0, 0]; pad[:h, :w] = alpha; alpha = pad; h, w = alpha.shape
    bh, bw = h // 4, w // 4
    blocks = alpha.reshape(bh, 4, bw, 4).transpose(0, 2, 1, 3).reshape(bh, bw, 16).astype(np.int32)
    a0 = blocks.max(-1); a1 = blocks.min(-1)
    tab = np.zeros((bh, bw, 8), np.int32); tab[..., 0] = a0; tab[..., 1] = a1
    for k in range(6): tab[..., 2 + k] = ((6 - k) * a0 + (1 + k) * a1) // 7
    idx = np.abs(blocks[..., :, None] - tab[..., None, :]).argmin(-1); idx[a0 == a1] = 0
    out = np.zeros((bh, bw, 16), np.uint8); out[..., 0] = a0; out[..., 1] = a1
    bits = np.zeros((bh, bw), np.uint64)
    for i in range(16): bits |= idx[..., i].astype(np.uint64) << np.uint64(3 * i)
    for i in range(6): out[..., 2 + i] = ((bits >> np.uint64(8 * i)) & np.uint64(255)).astype(np.uint8)
    out[..., 8:10] = 0xFF; out[..., 10:12] = 0; out[..., 12:16] = 0     # c0=white c1=black (like the original)
    return out.tobytes()

def read_iwi_alpha(path):
    """alpha channel of the biggest mip of a DXT5 .iwi (decoded through a DDS wrapper)"""
    import io
    d = open(path, 'rb').read(); ver, fmt = d[3], d[4]; W, H = struct.unpack('<HH', d[6:10]); n = W * H
    assert d[:3] == b'IWi' and fmt == 13, 'not a DXT5 iwi'
    dds = b'DDS ' + struct.pack('<7I', 124, 0x81007, H, W, n, 0, 1) + b'\0' * 44 + struct.pack('<2I4s5I', 32, 4, b'DXT5', 0, 0, 0, 0, 0) + struct.pack('<5I', 0x1000, 0, 0, 0, 0)
    return Image.open(io.BytesIO(dds + d[-n:])).convert('RGBA').split()[3]

def write_iwi(atlas_img, path, like=None):
    W, H = atlas_img.size
    a = np.array(atlas_img, np.uint8); mips = [a]; f = a.astype(np.float32)
    while f.shape[0] > 1 or f.shape[1] > 1:
        hh, ww = max(f.shape[0] // 2, 1), max(f.shape[1] // 2, 1)
        f = f[:hh * 2 if f.shape[0] > 1 else 1, :ww * 2 if f.shape[1] > 1 else 1]
        f = f.reshape(hh, f.shape[0] // hh, ww, f.shape[1] // ww).mean((1, 3))
        mips.append(np.round(f).astype(np.uint8))
    datas = [dxt5(m) for m in mips]
    total = 28 + sum(len(x) for x in datas)
    if like:
        h = open(like, 'rb').read(28); ver, fmt, flags = h[3], h[4], h[5]
    else: ver, fmt, flags = 6, 13, 0xC1          # values of the original gamefonts_pc.iwi
    sizes = [total]; s = total
    for x in datas[:3]: s -= len(x); sizes.append(s)
    sizes = sizes[:4]
    hdr = b'IWi' + bytes([ver, fmt, flags]) + struct.pack('<HHH', W, H, 1) + struct.pack('<4I', *sizes)
    assert len(hdr) == 28
    with open(path, 'wb') as fh:
        fh.write(hdr)
        for x in reversed(datas): fh.write(x)
    return total
