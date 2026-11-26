# -*- coding: utf-8 -*-
"""Arabic shaping + simple bidi for single-byte bitmap fonts (CoD2)."""
import re, unicodedata

# ---- build joining table from Unicode presentation forms ----
FORMS = {}   # base char -> {'isolated':cp,'initial':cp,'medial':cp,'final':cp}
LIGA = {}    # (lam, alefvariant) -> {'isolated':cp,'final':cp}
def _scan():
    for cp in list(range(0xFB50, 0xFDFF)) + list(range(0xFE70, 0xFEFD)):
        d = unicodedata.decomposition(chr(cp))
        if not d or not d.startswith('<'): continue
        tag, *rest = d.split()
        tag = tag.strip('<>')
        if tag not in ('isolated','initial','medial','final'): continue
        base = [chr(int(x,16)) for x in rest]
        if len(base) == 1:
            FORMS.setdefault(base[0], {})[tag] = cp
        elif len(base) == 2 and base[0] == '\u0644':
            LIGA.setdefault(tuple(base), {})[tag] = cp
_scan()

# letters we support (everything else Arabic is dropped or passed through)
ALLOWED = set('\u0621\u0622\u0623\u0624\u0625\u0626\u0627\u0628\u0629\u062a\u062b\u062c\u062d\u062e'
 '\u062f\u0630\u0631\u0632\u0633\u0634\u0635\u0636\u0637\u0638\u0639\u063a\u0641\u0642\u0643\u0644'
 '\u0645\u0646\u0647\u0648\u0649\u064a')
# Persian letters are not in the font any more (slots were needed for [ ] { } + _): replace by closest Arabic letter
FALLBACK = {'\u067e': '\u0628', '\u0686': '\u062c', '\u0698': '\u0632', '\u06af': '\u0643'}
TASHKEEL = set(chr(c) for c in range(0x064B, 0x0653)) | {'\u0640'}

def joins_next(ch):  # can connect to following letter
    f = FORMS.get(ch); return bool(f and 'initial' in f)
def joins_prev(ch):
    f = FORMS.get(ch); return bool(f and 'final' in f)

def shape(text):
    """logical Arabic string -> list of presentation-form code points (logical order)."""
    chars = [FALLBACK.get(c, c) for c in text if c not in TASHKEEL]
    out = []
    i = 0
    prev_joins = False  # previous letter connects forward
    while i < len(chars):
        c = chars[i]
        if c not in ALLOWED:
            out.append(ord(c)); prev_joins = False; i += 1; continue
        # lam-alef ligature
        if c == '\u0644' and i+1 < len(chars) and ('\u0644', chars[i+1]) in LIGA \
           and chars[i+1] in '\u0622\u0623\u0625\u0627':
            lg = LIGA[('\u0644', chars[i+1])]
            out.append(lg['final'] if prev_joins and 'final' in lg else lg['isolated'])
            prev_joins = False; i += 2; continue
        nxt = chars[i+1] if i+1 < len(chars) else None
        next_ok = nxt is not None and nxt in ALLOWED and joins_prev(nxt)
        a = prev_joins and joins_prev(c)
        b = joins_next(c) and next_ok
        f = FORMS[c]
        if a and b: k = 'medial'
        elif a: k = 'final'
        elif b: k = 'initial'
        else: k = 'isolated'
        out.append(f.get(k, f.get('isolated', ord(c))))
        prev_joins = joins_next(c) and (a or True) and b if False else (b)
        i += 1
    return out

ARABIC_RE = re.compile('[\u0600-\u06FF]')
TOKEN_RE = re.compile(r'\[\{[^}\s]*\}\]|\^\d|%[-\d.]*[a-zA-Z]|&&\d|\\n|\\r|\\t')   # first alternative = key placeholder like [{+melee_breath}]
MIRROR = {'(':')', ')':'(', '[':']', ']':'[', '{':'}', '}':'{', '<':'>', '>':'<'}
AR_PUNCT = {'\u061b': ';'}   # comma and question mark now have their own Arabic glyphs

def _is_ltr_strong(c): return c.isascii() and c.isalnum()

CODE_RE = re.compile(r'\^\d')

def visual(text):
    """logical text -> visual codepoints. Each line (separated by literal \\n) is processed on its own so lines keep their order.
    Colour codes (^1..^9) colour the text that comes AFTER them in the draw order (left to right). In Arabic the logical 'after' is
    drawn to the LEFT, so each coloured piece is reversed as a unit and its code is written right before it: '^2NAME: ^7message' is drawn
    as '^7 message ^2 NAME:' (name green, message white). Before this, the codes were moved like buttons and the colours were lost."""
    lines = text.split('\\n')
    colored = bool(CODE_RE.search(text)) and bool(ARABIC_RE.search(text))
    out = []; carried = None
    for i, ln in enumerate(lines):
        if i: out += [ord('\\'), ord('n')]
        if not colored: out += _visual_line(ln); continue
        parts = CODE_RE.split(ln); codes = CODE_RE.findall(ln)
        segs = [(carried, parts[0])] + list(zip(codes, parts[1:]))      # (colour in force, text); a colour continues on the next line
        if codes: carried = codes[-1]
        last = None
        for code, txt in reversed(segs):
            if not txt: continue
            if not txt.strip(): out += [ord(c) for c in txt]; continue  # only spaces: no colour needed
            c = code or '^7'                                            # no code yet = back to the normal colour
            if c != last: out += [ord(x) for x in c]; last = c
            out += _visual_line(txt)
    return out

def _visual_line(text):
    """logical text -> list of codepoints in *visual left-to-right* order."""
    # split into atoms: tokens (kept whole, LTR), chars
    atoms = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        atoms += [('c', ch) for ch in text[pos:m.start()]]
        atoms.append(('t', m.group()))
        pos = m.end()
    atoms += [('c', ch) for ch in text[pos:]]
    # classify
    kinds = []
    for k, v in atoms:
        if k == 't': kinds.append('L')
        elif ARABIC_RE.match(v): kinds.append('R')
        elif _is_ltr_strong(v): kinds.append('L')
        else: kinds.append('N')
    # resolve neutrals: LTR only if both neighbours (skipping neutrals) are L, else RTL
    n = len(kinds)
    res = kinds[:]
    for i in range(n):
        if kinds[i] != 'N': continue
        l = next((kinds[j] for j in range(i-1,-1,-1) if kinds[j] != 'N'), None)
        r = next((kinds[j] for j in range(i+1,n) if kinds[j] != 'N'), None)
        res[i] = 'L' if (l == 'L' and r == 'L') else 'R'
    # no Arabic at all -> leave plain LTR
    if 'R' not in res:
        return [ord(c) if k=='c' else None for k,c in atoms] if False else _plain(atoms)
    # group into runs
    runs = []
    for (k, v), d in zip(atoms, res):
        if runs and runs[-1][0] == d: runs[-1][1].append((k, v))
        else: runs.append([d, [(k, v)]])
    vis = []
    for d, items in reversed(runs):
        if d == 'L':
            for k, v in items: vis += [ord(x) for x in v]
        else:
            logical = ''.join(v for k, v in items)
            cps = shape(logical)
            seg = []
            for cp in reversed(cps):
                ch = chr(cp)
                ch = AR_PUNCT.get(ch, ch)
                ch = MIRROR.get(ch, ch)
                seg.append(ord(ch))
            vis += seg
    return vis

def _plain(atoms):
    out = []
    for k, v in atoms: out += [ord(x) for x in v]
    return out
