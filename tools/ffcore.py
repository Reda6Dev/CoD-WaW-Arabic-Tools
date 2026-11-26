# -*- coding: utf-8 -*-
"""Reader/writer for the Localize-entry region of a CoD4 (IWffu100 v5) fastfile.

Region layout (verified on localized_code_post_gfx_mp.ff):  for each entry
    struct {u32 valuePtr; u32 namePtr(=0xFFFFFFFF)}   (8 bytes, lives in another memory block)
    value\\0   only if valuePtr == 0xFFFFFFFF; otherwise valuePtr = 0x40000000 | offset  = back-reference
                to an identical string loaded earlier (shared strings)
    name\\0
The strings (value+name bytes, NOT the 8-byte structs) are consecutive in one memory block, and a
back-reference stores that block offset:  offset = BASE + (string bytes before the target value).
"""
import os, zlib, struct, re
NONE = 0xFFFFFFFF
AMBIG_MAX = 5
# Files that have too few shared strings to find the block base by voting (checked by hand from 6_تشخيص_ملف reports):
# {key that stores a back-reference: key of the entry that owns the identical text}
HINTS = {
    'BOG_A_SECURE_THE_M1A1_ABRAMS': 'BOG_A_SECURE_THE_M1A2_ABRAMS',
    'KILLHOUSE_CLIMB_THE_LADDER1': 'KILLHOUSE_CLIMB_THE_LADDER',
    'CGAME_SB_PLAYERS': 'CGAME_SB_PLAYER',
}
ENTRY = re.compile(rb'\xff{8}[^\x00\xff]*\x00[A-Z0-9]+_[A-Z0-9_\-]+\x00')
FIRST = b'\xff' * 8 + b'Server is full.\x00EXE_SERVERISFULL\x00'

def _flag(name, default=True):
    try:
        t = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), encoding='utf-8-sig').read().split('\n')[0].strip().lower()
        return t not in ('off', '0', 'no')
    except OSError: return default
POINTER_FIX = _flag('pointer_fix.txt')      # tools/pointer_fix.txt: on (default) = pointers to single texts follow the texts; off = old behaviour (to compare in the game)

POINTER = re.compile(rb'(?=[\x00-\xff][\x00-\xff][\x00-\xff][\x40-\x4f])', re.S)      # every position whose 4 bytes could be a pointer into block 4 (top nibble 4)

class FF:
    """All localize runs of a fastfile.  A fastfile can hold several separate runs of LocalizeEntry assets
    (e.g. code_post_gfx.ff: menu texts, then CGAME_/PLATFORM_ texts, then VIDSUBTITLES_ texts).  Every run keeps its own
    total length when rebuilt, so nothing after it moves; back-references may point from one run into an earlier run."""
    def __init__(self, path, starts=None):
        """starts: positions where the text blocks begin (taken from the ORIGINAL file). Used to read back a file we built: its texts may
        contain the byte 0xFF (an Arabic shape), which the automatic search for block starts cannot handle."""
        raw = open(path, 'rb').read()
        assert raw[:8] == b'IWffu100', 'not an IWffu100 fastfile'
        self.version = raw[8:12]
        self.data = zlib.decompress(raw[12:])
        self._starts = starts
        self._parse()

    # ---- reading one run -------------------------------------------------------------------------------------------
    def _read_run(self, p):
        d = self.data; start = p; ents = []; cum = 0
        while True:
            vp, np_ = struct.unpack_from('<II', d, p)
            assert np_ == NONE, f'unexpected structure at {p}'
            q = p + 8
            if vp == NONE:
                e = d.index(b'\0', q); val = d[q:e]; vcum = cum; cum += len(val) + 1; q = e + 1
            else:
                val = None; vcum = None
            e = d.index(b'\0', q); name = d[q:e].decode('latin-1'); cum += len(name) + 1; q = e + 1
            ents.append({'vp': vp, 'val': val, 'vcum': vcum, 'name': name, 'ext': False, 'owner': None})
            p = q
            if not self._next_is_entry(d, p): break
            assert re.match(r'^[A-Z0-9]+_', name), f'unexpected key {name!r}'
        return {'start': start, 'end': p, 'ents': ents, 'sb': cum, 'base': None, 'blk': 4}

    @staticmethod
    def _lookup(runs, vp):
        """('exact', owner entry) / ('inside', None) / None  for a back-reference value among runs with a known base."""
        blk, off = vp >> 28, vp & 0x0FFFFFFF
        for r in runs:
            if r['base'] is None or r['blk'] != blk: continue
            if r['base'] <= off < r['base'] + r['sb']:
                o = r['owners'].get(off - r['base'])
                return ('exact', o) if o is not None else ('inside', None)
        return None

    def _add_run(self, run, kept, first):
        """Find the block base of `run` and resolve its references. Raises AssertionError if it is not consistent."""
        from collections import Counter
        ents = run['ents']
        run['owners'] = owners = {e['vcum']: e for e in ents if e['vcum'] is not None}
        refs = [e for e in ents if e['vp'] != NONE]
        rest = []
        for e in refs:
            h = self._lookup(kept, e['vp'])
            if h is None: rest.append(e)
            else:
                assert h[0] == 'exact', 'reference into the middle of an earlier run'
        if rest:
            floor = max([r['base'] + r['sb'] for r in kept if r['base'] is not None] or [0])
            votes = Counter()
            for e in rest:
                for c in owners:
                    b = (e['vp'] & 0x0FFFFFFF) - c
                    if first or b >= floor: votes[(e['vp'] >> 28, b)] += 1
            hb = set(); byname = {e['name']: e for e in ents}
            for r in rest:
                o = byname.get(HINTS.get(r['name']))
                if o is not None and o['vcum'] is not None: hb.add((r['vp'] >> 28, (r['vp'] & 0x0FFFFFFF) - o['vcum']))
            if len(hb) == 1: (blk, base), n = hb.pop(), 99
            elif votes:
                (blk, base), n = votes.most_common(1)[0]
                top = [k for k, v in votes.items() if v == n]
                if len(top) > 1 and len({e['vp'] for e in rest}) == 1:
                    # several candidate owners fit equally and every reference points at ONE string: the game stores a text once and
                    # the following keys with the same text point back to it, so the owner is the inline entry just before them
                    first_ref = ents.index(rest[0])
                    prev = [e for e in ents[:first_ref] if e['vcum'] is not None]
                    if prev:
                        o = prev[-1]; blk, base = rest[0]['vp'] >> 28, (rest[0]['vp'] & 0x0FFFFFFF) - o['vcum']; n = 2
                        run['assumed'] = True
            else: n = 0
            assert n >= 2, 'cannot determine block base'
            run['blk'], run['base'] = blk, base
        for e in refs:
            h = self._lookup(kept + [run], e['vp'])
            if h is None:
                e['ext'] = True; e['owner'] = None; e['val'] = None
            else:
                assert h[0] == 'exact', 'cannot determine block base (reference into the middle of the texts)'
                e['owner'] = h[1]; e['val'] = h[1]['val']

    def _parse(self):
        """Read every text block. If the later blocks cannot be understood (or the unchanged rebuild differs), they are dropped one by one
        and the file is read the old way (first block only), so a file that could be read before can always be read."""
        limit = None
        if self._starts: self._nfound = 0; return self._parse_runs(None)      # verification mode: no silent fallback
        while True:
            self._nfound = 0
            try: return self._parse_runs(limit)
            except Exception:
                if self._nfound <= 1: raise
                limit = self._nfound - 1

    def _parse_runs(self, limit):
        # Every run is searched from the start of the file (never anchored on a text such as "Server is full."): the same runs are found
        # in the original file and in a rebuilt (translated) one.
        d = self.data
        if self._starts:
            runs = []
            for p in self._starts:
                run = self._read_run(p); self._add_run(run, runs, first=not runs); runs.append(run); self._nfound = len(runs)
            seen = True; first_err = None
            return self._finish(runs)
        pos = 0; runs = []; first_err = None; seen = False
        while True:
            m = ENTRY.search(d, pos)
            if not m: break
            p = m.start(); seen = True
            if limit is not None and len(runs) >= limit: break
            try:
                while d[p + 8] == 0xFF: p += 1      # a text never starts with 0xFF: those bytes belong to the previous data
                run = self._read_run(p)
                self._add_run(run, runs, first=not runs)
            except Exception as ex:
                if first_err is None: first_err = ex
                pos = m.start() + 1; continue       # something that only looks like a text block is skipped
            runs.append(run); pos = run['end']; self._nfound = len(runs)
        assert seen, 'no localized texts found in this file'
        if not runs: raise AssertionError(str(first_err))
        return self._finish(runs)

    def _finish(self, runs):
        self.runs = runs; self.ents = [e for r in runs for e in r['ents']]
        for i, e in enumerate(self.ents): e['i'] = i
        for ri, r in enumerate(runs):
            for e in r['ents']: e['run'] = ri
        r0 = runs[0]
        self.start, self.end, self.base, self.blk = r0['start'], r0['end'], r0['base'] or 0, r0['blk']
        self.string_bytes = sum(r['sb'] for r in runs)
        # which entry of each run absorbs the spare bytes (spaces): NULL_EMPTY, else the last inline text nobody points to
        used = {e['owner']['i'] for e in self.ents if e['owner'] is not None}
        # texts that other parts of the file (menus, the video-subtitle table) point at: the spare spaces must NOT go there, or the game would
        # read a text with hundreds of trailing spaces (it crashed when a video started)
        import numpy as np
        starts = {}
        for r in runs:
            if r['base'] is None or r['blk'] not in (4, 8): continue
            for e in r['ents']:
                if e['vp'] == NONE: starts[(r['blk'] << 28) | (r['base'] + e['vcum'])] = e['i']
        pointed = set()
        if starts:
            keys = np.array(sorted(starts), dtype=np.uint32); d = self.data; pos = 0
            for piece in [(pos, runs[0]['start'])] + [(runs[i]['end'], runs[i + 1]['start']) for i in range(len(runs) - 1)] + [(runs[-1]['end'], len(d))]:
                seg = d[piece[0]:piece[1]]
                for sh in range(4):
                    n = (len(seg) - sh) // 4
                    if n <= 0: continue
                    v = np.frombuffer(seg, dtype='<u4', count=n, offset=sh)
                    for x in v[np.isin(v, keys)].tolist(): pointed.add(starts[x])
        self.pointed = pointed
        for r in runs:
            inl = [e for e in r['ents'] if e['vp'] == NONE]
            ne = [e for e in inl if e['name'] == 'NULL_EMPTY' and e['i'] not in pointed]
            free = [e for e in inl if e['i'] not in used and e['i'] not in pointed]
            blank = [e for e in inl if not e['val'].strip() and e['i'] in used]       # an empty text (e.g. the attract-loop subtitle): nobody reads it
            free2 = [e for e in inl if e['i'] not in used]
            r['pad_i'] = (ne or free or blank or free2 or inl)[-1]['i']
        out, _ = self.render({})
        assert out == self.data, 'internal check failed: unchanged rebuild differs'

    @staticmethod
    def _next_is_entry(d, p):
        if p + 10 > len(d): return False
        vp, np_ = struct.unpack_from('<II', d, p)
        if np_ != NONE or not (vp == NONE or vp >> 28 in (4, 8)): return False
        q = p + 8
        if vp == NONE:
            e = d.find(b'\0', q)
            if e < 0 or e - q > 400000: return False
            q = e + 1
        e = d.find(b'\0', q)
        if e < 0 or e - q > 120: return False
        return re.fullmatch(rb'[A-Z0-9]+_[A-Za-z0-9_\. -]+', d[q:e]) is not None

    GROW_STEP = 1024      # a run may only grow by a multiple of this: later items of the memory block are aligned, so any other shift moves them unevenly
    GROW_MAX_FALSE = 3.0  # expected number of look-alike numbers (chance matches) we accept inside the data that follows

    def grow_risk(self, grown_runs):
        """Growing a run needs every pointer into the memory block behind its texts to be moved. They are found by their shape, so a number
        in other data that only looks like one (a chance match) would be damaged. Returns the expected number of such chance matches."""
        if any(self.runs[i]['base'] is None for i in grown_runs): return float('inf')      # position of this run's strings in the memory block is unknown (no back-references to measure it from)
        b4 = struct.unpack_from('<11I', self.data)[2 + 4]
        lo = min(self.runs[i]['base'] + self.runs[i]['sb'] for i in grown_runs)
        return len(self.data) * max(b4 - lo, 0) / 2 ** 32

    def render(self, newvals, grow=False):
        """newvals: {KEY: bytes}. Returns (new_stream or None, pad)  pad<0 => over budget by -pad bytes (worst run).
        Every run keeps its total length (so nothing after it moves); spare bytes are filled with spaces appended to
        one value of that run (NULL_EMPTY in the first run). pad returned = smallest spare of any run.
        grow=True: a run that is over budget is made longer instead (by a multiple of GROW_STEP) and every pointer behind it is moved
        (self.last_grow = growth per run, self.last_starts = where the runs start in the new stream)."""
        ents = self.ents
        cur = [None] * len(ents)
        for e in ents:                 # owners first (they always come before their back-references)
            i = e['i']
            if e['ext']: cur[i] = b''
            elif e['name'] in newvals: cur[i] = newvals[e['name']]
            elif e['vp'] != NONE: cur[i] = cur[e['owner']['i']]   # untranslated shared text follows its owner
            else: cur[i] = e['val']
        plan = []
        for e in ents:
            if e['ext']: plan.append('ext'); continue
            same = e['vp'] != NONE and cur[e['i']] == cur[e['owner']['i']]
            plan.append('ref' if same else 'inline')
        pads = []
        for r in self.runs:
            size = sum(8 + (len(cur[e['i']]) + 1 if plan[e['i']] == 'inline' else 0) + len(e['name']) + 1 for e in r['ents'])
            pads.append((r['end'] - r['start'] - r.get('cut', 0)) - size)      # 'cut': bytes this run gives away (font experiment)
        self.last_pads = list(pads)      # spare bytes of every run (negative = this run is over budget)
        self.last_risk = 0; self.last_grow = [0] * len(self.runs); self.last_starts = [r['start'] for r in self.runs]
        worst = min(pads)
        need = [i for i, p in enumerate(pads) if p < 0]
        self.last_risk = self.grow_risk(need) if need else 0
        if worst < 0 and grow and self.last_risk <= self.GROW_MAX_FALSE and all(self.runs[i]['blk'] == 4 for i in need) and not any(r.get('cut') or r.get('shift') for r in self.runs):
            self.last_grow = [(-p + self.GROW_STEP - 1) // self.GROW_STEP * self.GROW_STEP if p < 0 else 0 for p in pads]
            pads = [p + g for p, g in zip(pads, self.last_grow)]; worst = min(pads)
        elif worst < 0: return None, worst
        grown = any(self.last_grow)
        marks = [(r['base'] + r['sb'], g) for r, g in zip(self.runs, self.last_grow) if g]      # (end of that run's strings, growth)
        def move(off): return off + sum(g for t, g in marks if t <= off)
        for ri, r in enumerate(self.runs):
            # The spare bytes may not go onto ONE text when other parts of the file point at it (the video table points at every subtitle): the game would read a
            # text with thousands of spaces. They are spread over the texts of the run instead, never making a text longer than its ORIGINAL length, half in front, half behind (a centred text stays centred).
            pad = pads[ri]
            if pad > 0 and r['pad_i'] in self.pointed and not r.get('cut') and not r.get('shift'):
                cand = [(max(0, len(e['val']) - len(cur[e['i']])), e['i']) for e in r['ents'] if e['vp'] == NONE and not e['ext'] and plan[e['i']] == 'inline' and e['name'] != 'NULL_EMPTY']
                D = sum(d for d, i in cand)
                if D >= pad:
                    rest = pad; shares = {}
                    for d, i in cand:
                        sh = pad * d // D; shares[i] = sh; rest -= sh
                    for d, i in sorted(cand, reverse=True):
                        if rest <= 0: break
                        if shares[i] < d: shares[i] += 1; rest -= 1
                    for i, sh in shares.items():
                        if sh: cur[i] = b' ' * (sh // 2) + cur[i] + b' ' * (sh - sh // 2)
                    pads[ri] = 0
        for r, pad in zip(self.runs, pads):
            if pad:
                t = r['pad_i']; assert not ents[t]['ext']
                cur[t] += b' ' * pad; plan[t] = 'inline'
        vnew = {}
        for r in self.runs:
            cum = 0
            for e in r['ents']:
                if plan[e['i']] == 'inline': vnew[e['i']] = cum; cum += len(cur[e['i']]) + 1
                cum += len(e['name']) + 1
        hdr = struct.unpack_from('<11I', self.data); b4 = hdr[2 + 4]; lo = min(t for t, g in marks) if marks else 0
        # Other parts of the file (menus, the video-subtitle table...) point straight at the START of single strings inside the text blocks.
        # When a translation has another length, every string behind it moves, so those pointers must follow: smap = old start -> new start.
        smap = {}
        for r in self.runs:
            if r['base'] is None or r['blk'] not in (4, 8): continue
            oc = 0; nc = 0; nb = move(r['base']) + r.get('shift', 0)
            for e in r['ents']:
                if e['vp'] == NONE:                                   # value was stored here originally
                    if plan[e['i']] == 'inline': nv = nb + nc
                    else: o = e['owner']; ro = self.runs[o['run']]; nv = move(ro['base']) + ro.get('shift', 0) + vnew[o['i']]
                    if nv != r['base'] + oc: smap[(r['blk'] << 28) | (r['base'] + oc)] = (r['blk'] << 28) | nv
                    oc += len(e['val']) + 1
                if plan[e['i']] == 'inline': nc += len(cur[e['i']]) + 1
                if nb + nc != r['base'] + oc: smap[(r['blk'] << 28) | (r['base'] + oc)] = (r['blk'] << 28) | (nb + nc)    # the key string
                oc += len(e['name']) + 1; nc += len(e['name']) + 1
        self.last_remap = 0; smap_keys = None
        if smap and not POINTER_FIX: smap = {}
        if smap:
            import numpy as np
            smap_keys = np.array(sorted(smap), dtype=np.uint32)
        def fix_gap(piece):
            """move every pointer into block 4 that points behind a grown run (found by its shape, at any alignment: the stream has no padding),
            and every pointer to the start of a string whose position changed (smap)"""
            if (not grown and smap_keys is None) or len(piece) < 4: return piece
            import numpy as np
            cand = []
            for sh in range(4):
                n = (len(piece) - sh) // 4
                if n <= 0: continue
                v = np.frombuffer(piece, dtype='<u4', count=n, offset=sh)
                sel = np.zeros(n, dtype=bool)
                if grown:
                    off = v & np.uint32(0x0fffffff)
                    sel |= ((v >> np.uint32(28)) == 4) & (off >= lo) & (off < b4)
                if smap_keys is not None: sel |= np.isin(v, smap_keys)
                cand.append(np.nonzero(sel)[0].astype(np.int64) * 4 + sh)
            pos_list = np.sort(np.concatenate(cand)) if cand else []
            buf = bytearray(piece); last = -4
            for p in pos_list.tolist():
                if p < last + 4: continue
                v = struct.unpack_from('<I', piece, p)[0]
                if v in smap: nv = smap[v]; self.last_remap += 1
                elif grown and v >> 28 == 4 and lo <= (v & 0x0fffffff) < b4: nv = (v & 0xf0000000) | move(v & 0x0fffffff)
                else: continue
                struct.pack_into('<I', buf, p, nv); last = p
            return bytes(buf)
        res = bytearray(); pos = 0
        for ri, r in enumerate(self.runs):
            res += fix_gap(self.data[pos:r['start']])
            self.last_starts[ri] = len(res)
            out = bytearray()
            for e in r['ents']:
                k = plan[e['i']]
                if k == 'inline': out += struct.pack('<II', NONE, NONE) + cur[e['i']] + b'\0'
                elif k == 'ext':
                    vp = e['vp']
                    if grown and vp >> 28 == 4 and lo <= (vp & 0x0fffffff) < b4: vp = (vp & 0xf0000000) | move(vp & 0x0fffffff)
                    out += struct.pack('<II', vp, NONE)
                else:
                    o = e['owner']; orun = self.runs[o['run']]
                    out += struct.pack('<II', (orun['blk'] << 28) | (move(orun['base']) + orun.get('shift', 0) + vnew[o['i']]), NONE)
                out += e['name'].encode('latin-1') + b'\0'
            assert len(out) == r['end'] - r['start'] - r.get('cut', 0) + self.last_grow[ri]
            res += out; pos = r['end']
        res += fix_gap(self.data[pos:])
        if grown:
            tot = sum(self.last_grow); h = list(hdr); h[0] += tot; h[2 + 4] += tot
            res[:44] = struct.pack('<11I', *h)
        return bytes(res), worst

def pack(path, stream, version=b'\x05\x00\x00\x00', level=5):
    open(path, 'wb').write(b'IWffu100' + version + zlib.compress(stream, level))


def diagnose(path):
    """Lenient analysis of a fastfile that FF() cannot read. Returns a text report (small, safe to send to someone)."""
    from collections import Counter
    L = []; P = L.append
    raw = open(path, 'rb').read(); P('file: %s  size: %d' % (path.replace('\\', '/').split('/')[-1], len(raw)))
    if raw[:8] != b'IWffu100': P('NOT an IWffu100 file: %r' % raw[:12]); return '\n'.join(L)
    d = zlib.decompress(raw[12:]); P('version: %d  decompressed: %d' % (struct.unpack('<I', raw[8:12])[0], len(d)))
    P('xfile header: %s' % (struct.unpack('<11I', d[:44]),))
    allm = [m.start() for m in ENTRY.finditer(d)]
    P('entry-like matches in whole file: %d  first at: %s' % (len(allm), allm[:3]))
    if not allm: return '\n'.join(L)
    p = allm[0]
    while d[p + 8] == 0xFF: p += 1
    start = p; ents = []; cum = 0; stop = None
    while True:
        try:
            vp, np_ = struct.unpack_from('<II', d, p)
            if np_ != NONE: stop = 'bad namePtr at %d' % p; break
            q = p + 8
            if vp == NONE:
                e = d.index(b'\0', q); val = d[q:e]; vc = cum; cum += len(val) + 1; q = e + 1
            else: vc = None
            e = d.index(b'\0', q); name = d[q:e].decode('latin-1'); cum += len(name) + 1; q = e + 1
        except Exception as ex: stop = 'parse error %r at %d' % (ex, p); break
        ents.append((vp, vc, name)); p = q
        if not FF._next_is_entry(d, p): stop = 'next bytes are not an entry at %d' % p; break
    P('region: start=%d end=%d bytes=%d entries=%d string_bytes=%d' % (start, p, p - start, len(ents), cum))
    P('stop reason: %s' % stop)
    P('bytes after region (hex): %s' % d[p:p + 48].hex(' '))
    P('first 5 keys: %s' % [e[2] for e in ents[:5]]); P('last 5 keys: %s' % [e[2] for e in ents[-5:]])
    later = [m for m in allm if m >= p]
    P('entry-like matches AFTER the region: %d  at %s' % (len(later), later[:6]))
    refs = [e for e in ents if e[0] != NONE]; owners = {e[1]: e for e in ents if e[1] is not None}
    P('inline values: %d  back-references: %d' % (len(owners), len(refs)))
    P('reference blocks: %s' % Counter(e[0] >> 28 for e in refs).most_common(5))
    votes = Counter((e[0] >> 28, (e[0] & 0xFFFFFFF) - c) for e in refs for c in owners)
    P('top base votes (block, base): %s' % votes.most_common(4))
    if len(refs) <= AMBIG_MAX:      # too few shared strings to vote: list the candidates so a human can pick the right owner
        for r in refs:
            idx = ents.index(r); P('AMBIGUOUS REF: entry #%d key=%s vp=%s' % (idx, r[2], hex(r[0])))
            q = start
            for e in ents[:idx + 1]:
                q += 8
                if e[0] == NONE:
                    z = d.index(b'\0', q); txt = d[q:z].decode('latin-1')[:70]; q = z + 1
                    if e is not r: P('   cand vcum=%d base=%d key=%s | %s' % (e[1], (r[0] & 0xFFFFFFF) - e[1], e[2], txt.replace('\n', ' ')))
                z = d.index(b'\0', q); q = z + 1
    if votes:
        (blk, base), n = votes.most_common(1)[0]; bad = []
        for e in refs:
            off = (e[0] & 0xFFFFFFF) - base
            if not (e[0] >> 28 == blk and off in owners): bad.append((e[2], hex(e[0]), off))
        P('refs not matching an owner start with best base: %d of %d' % (len(bad), len(refs)))
        for b in bad[:12]: P('   %s vp=%s off=%d' % b)
        P('ref offsets min/max: %s / %s' % (min(e[0] & 0xFFFFFFF for e in refs), max(e[0] & 0xFFFFFFF for e in refs)))
    return '\n'.join(L)
