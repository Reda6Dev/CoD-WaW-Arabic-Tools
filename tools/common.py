# -*- coding: utf-8 -*-
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shaper
from ffcore import FF
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
HERE_ = os.path.dirname(os.path.abspath(__file__))
SMAP_BASE = json.load(open(os.path.join(HERE_, 'slotmap.json')))      # the shipped map: every A-W capital holds an Arabic shape, X Y Z are blank

# ---- Latin capitals that stay real letters (tools/keep_caps.txt) -----------------------------------------------------------------
# The font has no room for all Arabic shapes AND all capitals. X, Y, Z are free. Every other capital kept as a letter costs one rare
# Arabic form: the lam-alef shapes are then drawn as lam + alef (two glyphs), see DECOMP.
DROP_ORDER = [0xFBE8, 0xFBE9, 0xFEF6, 0xFEFA, 0xFEF5, 0xFEF9]
DECOMP = {0xFEF5: [0xFE82, 0xFEDF], 0xFEF6: [0xFE82, 0xFEE0], 0xFEF9: [0xFE88, 0xFEDF], 0xFEFA: [0xFE88, 0xFEE0]}   # visual (left-to-right) order

def read_keep():
    try: txt = open(os.path.join(HERE_, 'keep_caps.txt'), encoding='utf-8-sig').read()
    except Exception: return set()
    txt = '\n'.join(l for l in txt.split('\n') if not l.lstrip().startswith('#') and not l.lstrip().startswith('//'))
    return {c.upper() for c in txt if c.isascii() and c.isalpha()}

def apply_keep(base, keep):
    """-> (slotmap, dropped forms).  Moves the Arabic shapes that sit on kept capitals to the bytes of dropped rare forms."""
    slot = dict(base); K = {ord(c) for c in keep if ord(c) in slot.values()}
    drops = []
    while True:
        free = [slot[str(f)] for f in drops if str(f) in slot and slot[str(f)] not in K]
        reloc = [f for f, b in slot.items() if b in K and int(f) not in drops]
        if len(free) >= len(reloc): break
        if len(drops) == len(DROP_ORDER):
            sys.exit('keep_caps.txt: too many capitals. X, Y, Z are free and at most %d more can be kept (you asked for %s).' % (len(DROP_ORDER), ''.join(sorted(keep))))
        drops.append(DROP_ORDER[len(drops)])
    for f in drops: slot.pop(str(f), None)
    for f in reloc: slot[f] = free.pop(0)
    for f in drops:
        if f in DECOMP: assert all(str(x) in slot for x in DECOMP[f]), 'decomposition glyph missing from slotmap'
    return slot, drops

def read_grow():
    try: return open(os.path.join(HERE_, 'font_grow.txt'), encoding='utf-8-sig').read().split('#')[0].strip().lower() in ('on', '1', 'yes', 'true')
    except Exception: return False

def apply_grow(base):
    """every Arabic shape that sits on a capital A-W moves to the extra character codes 128.. (font tables get 23 more records)"""
    slot = dict(base); caps = sorted((b, f) for f, b in slot.items() if 65 <= b <= 90)
    for i, (b, f) in enumerate(caps): slot[f] = 128 + i
    assert 128 + len(caps) <= 151, 'more shapes on capitals than extra codes'
    return slot

GROW = read_grow()
if GROW:
    KEEP = set(chr(c) for c in range(65, 91)); SMAP = apply_grow(SMAP_BASE); DROPPED = []
    AVAILABLE_CAPS = KEEP
else:
    KEEP = read_keep() & set(chr(c) for c in range(65, 91))
    SMAP, DROPPED = apply_keep(SMAP_BASE, KEEP)
    AVAILABLE_CAPS = set('XYZ') | KEEP                  # Latin capitals the font really contains
FREED = '`~|#$@<>=*' + ''.join(chr(c) for c in range(65, 91) if chr(c) not in AVAILABLE_CAPS)   # ASCII slots that hold Arabic shapes (or nothing)

def lower_unavailable(s):
    """lowercase only the capitals the font cannot draw"""
    return ''.join(c.lower() if 'A' <= c <= 'Z' and c not in AVAILABLE_CAPS else c for c in s)
TOK = re.compile(r'\[\{[^}\s]*\}\]|\^\d|%[-\d.]*[a-zA-Z]|&&\d|\\n|\\r|\\t')

def clean_key(k):
    """a key must be plain ASCII: remove a BOM (real or typed as the text \\xef\\xbb\\xbf) and stray spaces that translators sometimes leave in front of it"""
    return k.replace('\ufeff', '').replace('\\xef\\xbb\\xbf', '').strip()

def load(p):
    d = {}
    for line in open(p, encoding='utf-8-sig'):
        line = line.rstrip('\r\n')
        if not line.strip() or line.startswith('//') or '=' not in line: continue
        k, v = line.split('=', 1); d[clean_key(k)] = v.strip()
    return d

def _dlen(w):
    """length of a word as it appears on screen: colour codes take no room, button/variable tokens about 3-4 characters"""
    w = re.sub(r'\^\d', '', w); w = re.sub(r'\[\{[^}\s]*\}\]', 'xxxx', w); w = re.sub(r'&&\d|%[-\d.]*[a-zA-Z]', 'xxx', w)
    return len(w)

def wrap_text(text, n):
    """Pre-wrap long texts. The game wraps long lines itself, but in the engine's (left-to-right) visual order, which puts the
    END of an Arabic sentence on the first line. Wrapping here, line by line in logical order, keeps the lines in the right order."""
    if n <= 0: return text
    out = []
    for seg in text.split('\\n'):
        if sum(_dlen(w) + 1 for w in seg.split(' ')) - 1 <= n: out.append(seg); continue
        lines, cur, curlen = [], '', 0
        for w in seg.split(' '):
            if cur and curlen + 1 + _dlen(w) > n: lines.append(cur); cur, curlen = w, _dlen(w)
            else: cur, curlen = ((cur + ' ' + w) if cur else w), (curlen + 1 + _dlen(w) if cur else _dlen(w))
        if cur: lines.append(cur)
        out.append('\\n'.join(lines))
    return '\\n'.join(out)

def encode(text, bad=None):
    """Arabic (or mixed) text -> raw game bytes (shaped, visual order, via slotmap)."""
    out = bytearray()
    vis = []
    for cp in shaper.visual(text):
        if cp in DROPPED and cp in DECOMP: vis.extend(DECOMP[cp])      # a rare lam-alef shape that has no slot: drawn as lam + alef
        else: vis.append(cp)
    sv = ''.join(chr(c) for c in vis); inside = set()
    for m in TOK.finditer(sv): inside.update(range(m.start(), m.end()))     # tokens like [{FAKE_INTRO_SECONDS:16}] stay raw (the engine reads them, never draws them)
    for i, cp in enumerate(vis):
        if i in inside and cp < 128: out.append(cp)
        elif str(cp) in SMAP: out.append(SMAP[str(cp)])
        elif cp < 128 and chr(cp) not in FREED: out.append(cp)
        else:
            out.append(ord('?'))
            if bad is not None: bad.add(chr(cp))
    return bytes(out).replace(b'\\n', b'\n')     # literal \n -> real line break

def apply_share(ff, newvals, report=True):
    """Texts that the game stores once and shares between several keys (same English) get ONE Arabic text:
    the first translated member of the group wins. This saves bytes (the file size budget is fixed)."""
    groups = {}
    for e in ff.ents:
        root = e['owner']['name'] if e['vp'] != 0xFFFFFFFF else e['name']
        groups.setdefault(root, []).append(e['name'])
    changed = 0
    for root, names in groups.items():
        if len(names) < 2: continue
        src = next((n for n in names if n in newvals), None)
        if src is None: continue
        for n in names:
            if n != 'NULL_EMPTY' and newvals.get(n) != newvals[src]:
                if n in newvals and report: changed += 1
                newvals[n] = newvals[src]
    if changed and report: print('note: %d shared key(s) were set to the same text as their group (identical English text)' % changed)
    return newvals
