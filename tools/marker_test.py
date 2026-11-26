# -*- coding: utf-8 -*-
"""Test translation (NOT a real translation): puts the Arabic letter ا at the start of every text so that you can see in the game which texts
were really replaced. Lines the checker rejects are put back to English. Usage (from the project root):  python tools\\marker_test.py
Then run 3_بناء_الملفات.bat and install as usual. To go back to the real translation: delete work\\arabic and run 1_استخراج_النصوص.bat again."""
import os, re, glob, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARA = os.path.join(ROOT, 'work', 'arabic'); ENG = os.path.join(ROOT, 'work', 'english', 'all_en.txt')
def rd(p): return open(p, encoding='utf-8-sig').read().split('\n')
en = {}
for l in rd(ENG):
    if ' = ' in l: k, v = l.split(' = ', 1); en[k] = v
def marker(v):
    if re.search(r'[&\^*=<>#|`~$@]|[^\x00-\x7f]', v) or not v[:1].isalpha(): return v
    return 'ا' + v[1:]
files = sorted(glob.glob(os.path.join(ARA, '*_ar.txt'))); n = 0
for f in files:
    out = []
    for l in rd(f):
        if ' = ' in l:
            k, v = l.split(' = ', 1)
            if v == en.get(k, v): v = marker(v); n += 1
            l = k + ' = ' + v
        out.append(l)
    open(f, 'w', encoding='utf-8-sig').write('\n'.join(out))
print('marked lines:', n)
for rnd in range(4):
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'cod4.py'), 'check'], cwd=ROOT, capture_output=True)
    rep = os.path.join(ROOT, 'work', 'check_report.txt')
    bad = set()
    for l in rd(rep):
        m = re.match(r'^(?:BADCHAR|PLACEHOLDER|EXTRA|LINES|KEY)\b.*?\s(\S+)\s+\[', l) or re.match(r'^SIZE \+[1-9]\d* (\S+)', l)
        if m: bad.add(m.group(1))
    print('round', rnd + 1, 'problem keys:', len(bad))
    if not bad: break
    for f in files:
        out = rd(f)
        for i, l in enumerate(out):
            if ' = ' in l:
                k = l.split(' = ', 1)[0]
                if k in bad and k in en: out[i] = k + ' = ' + en[k]
        open(f, 'w', encoding='utf-8-sig').write('\n'.join(out))
print('done. Now run 3_بناء_الملفات.bat')
