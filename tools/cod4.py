# -*- coding: utf-8 -*-
"""CoD4 Arabic localization tool (multiplayer + single player .ff files).
Commands (run from the package folder):
  python tools/cod4.py extract [LINES]   English texts of every .ff in work/input -> work/english (parts of LINES lines, default 200) and prepares copies in work/arabic
  python tools/cod4.py check   [--only=partNNN_ar.txt] [--quick] [--full] (--only or --quick = fast check without the size test)\n  python tools/cod4.py check   [--wrap=N] (default N from tools/wrap.txt; 0 = no pre-wrapping)\n                                           checks the translation in work/arabic (placeholders, characters, size)
  python tools/cod4.py build   [--wrap=N] builds the Arabic .ff files + font -> work/output
  python tools/cod4.py shortened [--only=file.txt]   lists translated lines that look trimmed compared with the English -> work/shortened_report.txt
  python tools/cod4.py longsubs   lists dialogue lines that will show on more than one line -> work/long_subtitles_report.txt
  python tools/cod4.py import GAMEFOLDER copies only the single-player .ff files that hold texts from the game to work/input
  python tools/cod4.py install GAMEFOLDER copies the result into the game (backs up the originals once as .bak)
  python tools/cod4.py restore GAMEFOLDER puts the original files back and removes the Arabic font
"""
import sys, os, re, glob, json, zlib, shutil, zipfile
if getattr(sys, 'frozen', False):      # built as a single .exe (PyInstaller): data files are unpacked next to the modules
    HERE = sys._MEIPASS; ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import *
import ffcore, fontlib
IN, EN, AR, OUT = [os.path.join(ROOT, 'work', n) for n in ('input', 'english', 'arabic', 'output')]
if getattr(sys, 'frozen', False): AR = os.path.join(HERE, 'work_arabic')      # translations are bundled inside the .exe
for _d in (IN, EN, AR): os.makedirs(_d, exist_ok=True)
try: IWD = open(os.path.join(HERE, 'iwd_name.txt')).read().strip() or 'localized_english_iw07.iwd'
except Exception: IWD = 'localized_english_iw07.iwd'      # same naming family as the game's own localized_english_iwNN.iwd files: this is the name that was tested in the game
OLD_IWDS = ['zzz_arabic_font_cod4.iwd']                 # name used by earlier versions of this tool
FALLBACK_IWDS = ['localized_english_iw%02d.iwd' % n for n in range(90, 100)]      # used only if IWD is already a REAL game file

def is_ours(p):
    """True only for the font archive made by this tool (it contains exactly images/gamefonts_ar.iwi). Real game files are never touched."""
    try:
        with zipfile.ZipFile(p) as z: return z.namelist() == ['images/gamefonts_ar.iwi']
    except Exception: return False

def our_iwds(main):
    out = []
    for p in glob.glob(os.path.join(main, '*.iwd')):
        b = os.path.basename(p).lower()
        if (b.startswith('localized_english_iw') or b in OLD_IWDS) and is_ours(p): out.append(p)
    return out

def pick_iwd(main):
    for c in [IWD] + FALLBACK_IWDS:
        p = os.path.join(main, c)
        if not os.path.exists(p) or is_ours(p): return c
    return None

LANG = 'ar'
try:
    LANG = open(os.path.join(HERE, 'lang.txt')).read().strip() or 'ar'
except Exception: pass
MSG = {
 'no_ff': ('لا يوجد ملف ff بمجلد work\\input. انسخ الملفات الأصلية من CoD4\\zone\\english إليه أولاً.', 'No .ff file in work/input. Copy the ORIGINAL .ff files from CoD4\\zone\\english there first.'),
 'skipped': ('تم تجاوز الملف {0} (ما قدرت أقرأه): {1}', 'SKIPPED {0} - cannot read it: {1}'),
 'notext': ('ملف بدون نصوص (طبيعي، يُترك كما هو): {0}', 'no texts in {0} (normal, left as is)'),
 'modded': ('تحذير: الملف {0} يبدو أنه معرَّب أصلاً (مو الأصلي). استخدم النسخة الأصلية (.bak من مجلد اللعبة) بمجلد work\\input وإلا النصوص المستخرجة تكون بالعربي المشوّه.', 'WARNING: {0} looks already Arabized (not the original). Put the ORIGINAL (.bak) in work/input.'),
 'nothing': ('ما في ملف قابل للقراءة بمجلد work\\input.', 'Nothing readable in work/input.'),
 'extracted': ('تم الاستخراج. الملفات: {0} | عدد النصوص: {1} | عدد الأجزاء: {2} | المكان: {3}', 'files: {0} | texts: {1} | parts: {2} -> {3}'),
 'all_done': ('كل النصوص مترجمة! ما في شي جديد للترجمة.', 'Everything is translated! Nothing new to translate.'),
 'ar_created2': ('تم تجهيز {0} نص غير مترجم بملفات {1}001_ar.txt ... بمجلد work\\arabic (النصوص المترجمة سابقاً ({2}) ما انلمست). ترجم الجزء بعد = بها.', 'Prepared {0} untranslated texts in work/arabic as {1}001_ar.txt ... ({2} already translated texts were not touched).'),
 'ar_exists': ('مجلد work\\arabic فيه {0} ملف .txt من قبل، ما لمسته (امسحها إذا تريد نسخ جديدة).', 'work/arabic already has {0} .txt file(s): NOT touched (delete them for fresh copies).'),
 'ar_created': ('تم إنشاء نسخ الترجمة part001_ar.txt ... part{0:03d}_ar.txt بمجلد work\\arabic. ترجم الجزء اللي بعد علامة = بها.', 'Copies part001_ar.txt ... part{0:03d}_ar.txt created in work/arabic: translate the text after = in them.'),
 'extra': ('مفتاح غير موجود بأي ملف ff', 'key not in any .ff'),
 'badchar_hint': ('(الرموز ` ~ | # $ @ < > = * أو الحرف غير المدعوم غير متاحة. اكتبها بالعربي أو احذفها. الحروف الإنجليزية المتاحة الآن:)', '(these characters are not available in the font. Latin capitals available now:)'),
 'ph': ('رمز ناقص أو متغيّر. بالإنجليزي: {0} | بالعربي: {1}', 'English: {0} | Arabic: {1}'),
 'translated': ('تمت ترجمة {0} من {1} نص (والباقي {2} لسه إنجليزي) من {3} ملف', 'translated: {0} of {1} texts ({2} still English) from {3} file(s)'),
 'size_over': ('الحجم: {0}  تجاوز المساحة بمقدار {1} بايت. قصّر هذي النصوص (زيادة الطول بالبايت):', 'SIZE  {0}  OVER BUDGET by {1} bytes. Shorten these (Arabic bytes minus English bytes):'),
 'size_ok': ('الحجم: {0}  مناسب (باقي {1} بايت فاضي)', 'SIZE  {0}  OK ({1} spare bytes)'),
 'done_check': ('انتهى الفحص: {0} مشكلة', 'done: {0} problem(s)'),
 'fix_first': ('\nصلّح المشاكل أعلاه أولاً (ما تم بناء شي). المشاكل محفوظة أيضاً بملف work\\check_report.txt', '\nFix the problems above first (nothing was built). They are also saved in work/check_report.txt'),
 'fix_head': ('الإصلاح التلقائي (نسخة احتياطية بمجلد {0}):', 'AUTO-FIX (backup in {0}):'),
 'grown': ('تنبيه: الملف {0} تكبّر {1} بايت لأن الترجمة أطول من الأصل. هذا الأسلوب جُرّب باللعبة على ملف اللعب الجماعي، فإذا صار خلل بهذا الملف بالذات اجعل tools\\size_grow.txt = off وقصّر الأسطر.', 'NOTE: {0} was made {1} bytes larger because the translation is longer than the original (tested method)'),
 'no_grow': ('      ما أقدر أكبّر {0} تلقائياً (احتمال خطر {1} > الحد، الملف كبير أو النصوص بنهايته مو آخر شي). قصّر الأسطر المذكورة.', '      cannot grow {0} automatically (risk {1}: the file is too large to move its pointers safely). Shorten the lines above.'),
 'fix_key_junk': ('رموز زائدة قبل اسم المفتاح', 'junk characters before the key name'),
 'fix_quotes': ('« » -> " "', 'guillemets -> plain quotes'),
 'fix_case': ('حروف كبيرة -> صغيرة', 'capital letters -> lowercase'),
 'fix_key': ('اسم زر كيبورد -> حرف لاتيني صغير', 'keyboard key label -> lowercase Latin'),
 'fix_sp': ('تنظيف مسافات زائدة', 'extra spaces cleaned'),
 'fix_nl': ('أُضيفت \\n الناقصة بآخر النص', 'missing trailing \\n added'),
 'fix_done': ('تم إصلاح {0} سطر. التفاصيل بملف work\\fix_report.txt. شغّل 2_فحص_الترجمة.bat الآن للتأكد. (الباقي لازم تصلحه بإيدك، مثل تقصير النصوص الطويلة)', 'fixed {0} line(s). Details: work/fix_report.txt. Run check now. (the rest must be fixed by hand, e.g. shortening long texts)'),
 'fix_none': ('ما لقيت شي يُصلَّح تلقائياً.', 'Nothing to fix automatically.'),
 'iwd_taken': ('الملف {0} موجود بمجلد main كملف أصلي من اللعبة، ما انلمس. استخدمت الاسم {1} للخط بدلاً منه.', 'main\\{0} is a real game file: NOT touched. Using {1} for the font instead.'),
 'iwd_full': ('ما لقيت اسماً فاضياً لملف الخط بمجلد main.', 'No free file name for the font in main.'),
 'cleaned': ('تم حذف الملفات المؤقتة (work\\input و work\\output).', 'Temporary files removed (work/input, work/output).'),
 'font_ok': ('تم تركيب الخط العربي', 'Arabic font patched'),
 'font_none': ('ما في خطوط بهذا الملف (تُرك كما هو)', 'no fonts in this file (left as is)'),
 'built': ('تم بناء {0} - {1}', 'built {0} - {1}'),
 'build_ok': ('\nتم البناء بنجاح. النتيجة بمجلد work\\output (zone\\english\\*.ff و main\\{0}). الخطوة التالية: 4_تركيب_في_اللعبة.bat', '\nOK. Output in work/output (zone/english/*.ff and main/{0}). Next: 4_تركيب_في_اللعبة.bat'),
 'usage_install': ('الاستخدام: install مسار_اللعبة', 'Usage: install GAMEFOLDER'),
 'not_cod4': ('هذا مو مجلد اللعبة (ما فيه zone\\english): {0}', 'Not the game folder (no zone\\english): {0}'),
 'not_built': ('ما تم بناء شي بعد. شغّل 3_بناء_الملفات.bat أولاً.', 'Nothing built yet. Run build first.'),
 'backup': ('نسخة احتياطية: {0}', 'backup: {0}'),
 'installed': ('تم تركيب {0}', 'installed {0}'),
 'restored': ('تم إرجاع الأصلي {0}', 'restored {0}'),
 'removed': ('تم حذف {0}', 'removed {0}'),
 'slot_bad': ('خطأ: ملف tools/slotmap.json لا يطابق جداول الخط. استخدم ملف slotmap.json الأصلي من الحزمة.', 'ERROR: tools/slotmap.json does not match the font tables. Use the slotmap.json shipped with this package.'),
 'font_layout': ('خطأ: الملف {0} بتخطيط خط مختلف.', 'ERROR: {0} has a different font table layout.'),
}
KIND = {'EXTRA': 'مفتاح زائد', 'BADCHAR': 'حرف ممنوع', 'PLACEHOLDER': 'رمز متغيّر'}
def t(key, *a):
    ar, en = MSG[key]
    return (ar if LANG == 'ar' else en).format(*a)
WRAP_PREFIX = {}      # tools/wrap.txt: first number = default line width; lines like  SUBTITLE_ = 30  give another width to keys that start with that text
try:
    _w = open(os.path.join(HERE, 'wrap.txt'), encoding='utf-8-sig').read().split('\n'); DEFAULT_WRAP = int(next(l.split('#')[0].split()[0] for l in _w if l.split('#')[0].strip() and '=' not in l))
    for _l in _w:
        _l = _l.split('#')[0].strip()
        if '=' in _l: _k, _v = _l.split('=', 1); WRAP_PREFIX[_k.strip()] = int(_v.strip())
except Exception: DEFAULT_WRAP = 38
def wrap_for(key, default):
    for p, n in sorted(WRAP_PREFIX.items(), key=lambda x: -len(x[0])):
        if key.startswith(p): return n if default == DEFAULT_WRAP else min(n, default)
    return default
KEYNAMES = {'KEY_' + n for n in 'TAB ENTER ESCAPE SPACE BACKSPACE ALT CTRL SHIFT CAPSLOCK INS DEL PGDN PGUP HOME END'.split()}   # keyboard keys: must match the real (Latin) keyboard
def kind(k):
    return '%s (%s)' % (k, KIND[k]) if LANG == 'ar' else k

ONLY_FF = None      # --ff=a.ff,b.ff : work with these .ff files only (to test one mission at a time)
for _a in sys.argv[2:]:
    if _a.startswith('--ff='): ONLY_FF = {(x if x.endswith('.ff') else x + '.ff').lower() for x in _a[5:].split(',') if x}

try: _sg = open(os.path.join(HERE, 'size_grow.txt'), encoding='utf-8-sig').read().split('#')[0].strip().lower()
except OSError: _sg = 'off'
SIZE_GROW = _sg in ('on', '1', 'yes', 'true', 'all')
SIZE_GROW_ALL = _sg == 'all'      # 'all': also big files (the pointer search may touch a few look-alike numbers: test it in the game first, see 10_تجربة_تكبير_الملف.bat)      # tools/size_grow.txt: on = a file whose texts do not fit may become larger (only small files, see README)
try: STABLE_FILES = set(w.lower() for ln in open(os.path.join(HERE, 'stable.txt'), encoding='utf-8-sig').read().splitlines() for w in ln.split('#')[0].replace(',', ' ').split())
except Exception: STABLE_FILES = set()      # tools/stable.txt: files whose every text keeps its ORIGINAL length (shorter texts are padded with spaces), so nothing moves inside the file
try: STABLE_KEYS = set(w for ln in open(os.path.join(HERE, 'stable_keys.txt'), encoding='utf-8-sig').read().splitlines() for w in ln.split('#')[0].replace(',', ' ').split())
except Exception: STABLE_KEYS = set()      # tools/stable_keys.txt: keys whose text must stay at its ORIGINAL position (the game reads them from a fixed place); the texts before them are padded with spaces to keep it there
NO_TEXT = '--no-text' in sys.argv[2:]      # build the font only: leave every text as it is

def inputs():
    fs = sorted(glob.glob(os.path.join(IN, '*.ff')))
    if ONLY_FF is not None: fs = [f for f in fs if os.path.basename(f).lower() in ONLY_FF]
    if not fs: sys.exit(t('no_ff'))
    return fs

NOT_READ = []       # (file name, reason) of every .ff in work/input that gave no texts: shown again at the end of the build

def open_all():
    out = {}; NOT_READ.clear()
    for p in inputs():
        b = os.path.basename(p)
        try: out[b] = (ffcore.FF(p), p)
        except Exception as e:
            if 'no localized texts' in str(e): print(t('notext', b)); NOT_READ.append((b, 'no texts (normal)'))
            else: print(t('skipped', b, e)); NOT_READ.append((b, 'NOT READ: %s' % e))
    if not out: sys.exit(t('nothing'))
    return out

def union_english(ffs):
    d = {}
    for name, (ff, _) in ffs.items():
        for e in ff.ents:
            if e['name'] != 'NULL_EMPTY' and not e['ext'] and e['name'] not in d:
                d[e['name']] = e['val'].decode('cp1252', 'replace').replace('\r', '').replace('\n', '\\n')
    return d

POS = {}      # key -> 'file:line' of the translation that is used

def eng_cached():
    """The English texts of work/input. Reading all the .ff files takes a long time (World at War: 20 files, up to 90 MB each), so the result is kept in
    work/eng_cache.json and used again as long as the files in work/input did not change."""
    import json
    fs = [f for f in sorted(glob.glob(os.path.join(IN, '*.ff'))) if ONLY_FF is None or os.path.basename(f).lower() in ONLY_FF]
    sig = [[os.path.basename(f), os.path.getsize(f), int(os.path.getmtime(f))] for f in fs]
    cp = os.path.join(ROOT, 'work', 'eng_cache.json')
    try:
        c = json.load(open(cp, encoding='utf-8'))
        if c.get('sig') == sig: return c['eng']
    except Exception: pass
    eng = union_english(open_all())
    try: json.dump({'sig': sig, 'eng': eng}, open(cp, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception: pass
    return eng

def load_translation(eng=None):
    tr = {}; POS.clear()
    files = sorted(glob.glob(os.path.join(AR, '*.txt')))
    for p in files:
        for n, line in enumerate(open(p, encoding='utf-8-sig'), 1):
            line = line.rstrip('\r\n')
            if not line.strip() or line.startswith('//') or '=' not in line: continue
            k, v = line.split('=', 1); k = clean_key(k); v = v.strip()
            if eng is not None and k in eng and v == eng[k].strip(): continue      # still English: never overrides a real translation
            if v: tr[k] = v; POS[k] = '%s:%d' % (os.path.basename(p), n)
    return tr, len(files)

def drop_untranslated(tr, eng):
    # an entry identical to its English text has simply not been translated yet
    return {k: v for k, v in tr.items() if k not in eng or v.strip() != eng[k].strip()}

def untouched(path, eng):
    """True if every line of this arabic file is still the English text (nothing translated in it)."""
    for k, v in load(path).items():
        if k not in eng or v.strip() != eng[k].strip(): return False
    return True

LOOSE_ENTRY = re.compile(rb'\xff{8}([^\x00\xff]{1,600})\x00([A-Za-z][A-Za-z0-9_.\-]{2,80})\x00')

def possible_missed(ff):
    """Safety net for the extraction: the extraction only trusts keys written like MENU_QUIT (capitals, digits, _). This scans the same raw data with a much looser key rule and lists every
    'text + name' pair that has the same structure but was NOT extracted (a different key style, or a text in a place the tool did not see)."""
    have = {e['name'] for e in ff.ents}; out = []
    for m in LOOSE_ENTRY.finditer(ff.data):
        val, key = m.group(1), m.group(2).decode('latin-1')
        if key in have or not re.search(rb'[A-Za-z]{2,}', val): continue
        if not re.fullmatch(rb'[\x20-\x7e]+', val): continue                                      # random binary bytes, not an English text
        if re.search(r'\.(mp3|wav|iwi|bik|roq|ogg|gsc|csv|txt)$', key, re.I): continue         # a file name, not a text key
        if val.islower() and b' ' not in val: continue                                          # one lower-case word ('end', 'music'): a script/engine name, not a text
        out.append((key, val.decode('latin-1')))
    return out

KEEP_PREFIXES = []
try:
    for _l in open(os.path.join(HERE, 'keep_english.txt'), encoding='utf-8-sig').read().split('\n'):
        _l = _l.split('#')[0].strip()
        if _l: KEEP_PREFIXES.append(_l)
except OSError: pass

def keep_en(k, v):
    """tools/keep_english.txt: short technical labels (weapon names, start-point names, HUD codes, keyboard keys...) that stay English and are not listed in the todo files."""
    return len(v) <= 24 and any(k.startswith(p) for p in KEEP_PREFIXES)

def cmd_extract(args):
    nums = [a for a in args if a.isdigit()]; n = int(nums[0]) if nums else 200
    ffs = open_all(); eng = union_english(ffs)
    for name, (ff, _) in ffs.items():       # a file built by this tool keeps its length by padding NULL_EMPTY with spaces: the original has a short NULL_EMPTY
        if is_modded(ff): print(t('modded', name))
    miss = []
    for name, (ff, _) in ffs.items():
        for k, v in possible_missed(ff): miss.append('%s | %s | %s' % (name, k, v[:100]))
    open(os.path.join(ROOT, 'work', 'possible_missed.txt'), 'w', encoding='utf-8-sig').write('\n'.join(miss) + ('\n' if miss else ''))
    print('فحص التغطية: %s' % ('كل النصوص اللي بنفس شكل النصوص انستخرجت (0 ناقص).' if not miss else '%d نص بنفس بنية النصوص ما انستخرج! شوفها بـ work\\possible_missed.txt وأرسلها لي.' % len(miss)))
    for f in glob.glob(os.path.join(EN, '*.txt')): os.remove(f)
    bf = os.path.join(EN, 'by_file'); os.makedirs(bf, exist_ok=True)
    for f in glob.glob(os.path.join(bf, '*.txt')): os.remove(f)
    owner = {}
    for name, (ff, _) in ffs.items():
        ks = [e['name'] for e in ff.ents if e['name'] != 'NULL_EMPTY' and not e['ext']]
        for k in ks: owner.setdefault(k, []).append(name)
        with open(os.path.join(bf, name[:-3] + '.txt'), 'w', encoding='utf-8') as f:
            for k in ks: f.write('%s = %s\n' % (k, eng[k]))
    with open(os.path.join(EN, 'key_to_file.txt'), 'w', encoding='utf-8') as f:      # which .ff each text belongs to
        for k in eng: f.write('%s  ->  %s\n' % (k, ', '.join(owner.get(k, []))))
    items = list(eng.items())
    with open(os.path.join(EN, 'all_en.txt'), 'w', encoding='utf-8') as f:
        for k, v in items: f.write(f'{k} = {v}\n')
    parts = 0
    for i in range(0, len(items), n):
        parts += 1
        with open(os.path.join(EN, 'part%03d_en.txt' % parts), 'w', encoding='utf-8') as f:
            for k, v in items[i:i + n]: f.write(f'{k} = {v}\n')
    print(t('extracted', ', '.join(ffs), len(items), parts, EN))
    # arabic copies: only for texts that are not translated yet; copies nobody touched are replaced, translated files are never touched
    for f in glob.glob(os.path.join(AR, '*_ar.txt')):
        b = os.path.basename(f)
        if (b.startswith('part') or b.startswith('todo')) and untouched(f, eng): os.remove(f)
    tr, _ = load_translation(eng); tr = drop_untranslated(tr, eng)
    todo = [(k, v) for k, v in items if k not in tr and not keep_en(k, v)]
    prefix = 'todo' if tr else 'part'
    if not todo: print(t('all_done')); return
    c = 0
    for i in range(0, len(todo), n):
        c += 1; name = '%s%03d_ar.txt' % (prefix, c)
        while os.path.exists(os.path.join(AR, name)): c += 1; name = '%s%03d_ar.txt' % (prefix, c)
        with open(os.path.join(AR, name), 'w', encoding='utf-8-sig') as f:
            for k, v in todo[i:i + n]: f.write(f'{k} = {v}\n')
    print(t('ar_created2', len(todo), prefix, tr and len(tr) or 0))

def analyse(wrap, only=None):
    ffs = open_all(); eng = union_english(ffs); tr, nfiles = load_translation(eng); tr = drop_untranslated(tr, eng)
    if NO_TEXT: tr = {}
    problems = 0; newvals = {}; report = []
    def say(kind_, k, msg):
        if only and not POS.get(k, '').startswith(only + ':'): return False
        if k in eng and kind_ != 'EXTRA': msg += '\n      الأصل الإنجليزي: ' + eng[k][:160].replace('\n', ' ')
        line = '%s  %s  [المكان: %s]  %s' % (kind(kind_), k, POS.get(k, '?'), msg) if LANG == 'ar' else '%-11s %s  [%s]  %s' % (kind_, k, POS.get(k, '?'), msg)
        print(line); report.append(line); return True
    for k, v in tr.items():
        if k not in eng:
            if ONLY_FF is None: problems += bool(say('EXTRA', k, t('extra')))
            continue
        a, e = sorted(TOK.findall(v)), sorted(TOK.findall(eng[k]))
        if a != e: problems += bool(say('PLACEHOLDER', k, t('ph', e, a)))
        bad = set(); b = encode(wrap_text(v, wrap_for(k, wrap)), bad)
        if bad: problems += bool(say('BADCHAR', k, ' '.join(sorted(bad)) + '   ' + t('badchar_hint') + ' [' + ''.join(sorted(AVAILABLE_CAPS)) + ']' + '\n      النص: ' + v[:120]))
        newvals[k] = b
    miss = [k for k in eng if k not in tr]
    open(os.path.join(ROOT, 'work', 'still_english.txt'), 'w', encoding='utf-8-sig').write('\n'.join('%s = %s' % (k, eng[k]) for k in miss))
    print(t('translated', len(tr) - sum(1 for k in tr if k not in eng), len(eng), len(miss), nfiles))
    results = {}
    for name, (ff, p) in ffs.items():
        nv = {k: v for k, v in newvals.items() if k in {e['name'] for e in ff.ents}}
        nv = apply_share(ff, nv, report=False)
        if name.lower() in STABLE_FILES or os.path.splitext(name)[0].lower() in STABLE_FILES:
            over = []
            for e in ff.ents:
                k = e['name']
                if k not in nv or e['vp'] != 0xFFFFFFFF: continue
                n0 = len(e['val'])
                if len(nv[k]) > n0: over.append((len(nv[k]) - n0, k))
                else: nv[k] = nv[k] + b' ' * (n0 - len(nv[k]))
            if over:
                over.sort(reverse=True)
                print('الحجم: %s  (وضع المواضع الثابتة) %d نص أطول من الأصل بالبايت. قصّرها (كل نص لازم يساوي أو يقل عن طول الأصلي):' % (name, len(over))); report.append('STABLE %s: %d over' % (name, len(over)))
                for g, k in over[:40]:
                    print('        %+4d  %s   |  %s  ->  %s' % (g, k, eng.get(k, '')[:60], tr.get(k, '')[:60])); report.append('SIZE %+d %s' % (g, k))
                if len(over) > 40: print('        ... و %d غيرها (صلّح هذي ثم أعد الفحص)' % (len(over) - 40))
                results[name] = (None, -over[0][0]); problems += 0 if only else 1; continue
        anchor_bad = []
        if STABLE_KEYS and not (name.lower() in STABLE_FILES or os.path.splitext(name)[0].lower() in STABLE_FILES):
            for ri, run in enumerate(ff.runs):
                inl = [e for e in run['ents'] if e['vp'] == 0xFFFFFFFF]
                if not any(e['name'] in STABLE_KEYS for e in inl): continue
                # this GROUP of texts is read by the game from fixed places: every text keeps its original length (shorter = spaces behind it)
                for e in inl:
                    k = e['name']
                    if k not in nv: continue
                    n0 = len(e['val'])
                    if len(nv[k]) > n0: anchor_bad.append((len(nv[k]) - n0, k, ri))
                    else: nv[k] = nv[k] + b' ' * (n0 - len(nv[k]))
        if anchor_bad:
            anchor_bad.sort(reverse=True)
            print('الحجم: %s  %d نص بمجموعة ثابتة (stable_keys.txt) أطول من الأصل. كل نص بهذي المجموعة لازم يساوي طول الأصلي أو أقصر (الزيادة بالبايت):' % (name, len(anchor_bad))); report.append('STABLE %s: %d over' % (name, len(anchor_bad)))
            for g, k, ri in anchor_bad:
                print('        %+4d  %s   |  %s  ->  %s' % (g, k, eng.get(k, '')[:60], tr.get(k, '')[:60])); report.append('SIZE %+d %s' % (g, k))
            results[name] = (None, -anchor_bad[0][0]); problems += 0 if only else 1; continue
        if SIZE_GROW_ALL: ff.GROW_MAX_FALSE = 1e12
        stream, pad = ff.render(nv, grow=SIZE_GROW)
        results[name] = (stream, pad); ff.built_starts = list(ff.last_starts)
        if stream is not None and any(ff.last_grow): print(t('grown', name, sum(ff.last_grow), ' + '.join(str(g) for g in ff.last_grow if g)))
        if stream is None:
            print(t('size_over', name, -pad))
            if SIZE_GROW: print(t('no_grow', name, '%.1f' % ff.last_risk if ff.last_risk else '?'))
            names = {e['name']: e for e in ff.ents}
            shown = False
            for ri, p in enumerate(getattr(ff, 'last_pads', [])):      # the budget is PER GROUP of texts (run): savings in another group do not help
                if p >= 0: continue
                rows = sorted(((len(nv[e['name']]) - len(e['val']), e['name']) for e in ff.runs[ri]['ents'] if e['name'] in nv and e['vp'] == 0xFFFFFFFF), reverse=True)
                shown = True
                print('      >> مجموعة نصوص %d: تجاوز %d بايت. قصّر نصاً أو أكثر من هذه المجموعة فقط (الزيادة بالبايت):' % (ri + 1, -p)); report.append('SIZE group %d over by %d' % (ri + 1, -p))
                for g, k in rows[:12]:
                    print('        %+4d  %s   |  %s  ->  %s' % (g, k, eng.get(k, '')[:60], tr.get(k, '')[:60])); report.append('SIZE %+d %s' % (g, k))
            if not shown:
                grow = sorted(((len(v) - len(names[k]['val']), k) for k, v in nv.items() if names[k]['vp'] == 0xFFFFFFFF), reverse=True)[:15]
                for g, k in grow:
                    print('        %+4d  %s' % (g, k)); report.append('SIZE %+d %s' % (g, k))
                    if k in eng: print('              الأصل: %s\n              الترجمة: %s' % (eng[k][:100].replace('\n', ' '), tr.get(k, '')[:100]))
            problems += 0 if only else 1
        else: print(t('size_ok', name, pad))
    open(os.path.join(ROOT, 'work', 'check_report.txt'), 'w', encoding='utf-8-sig').write('\n'.join(report) + '\n')
    return ffs, results, problems

def analyse_quick(wrap, only=None):
    """Fast check of the text lines only (placeholders, characters, keys). It does NOT open the .ff files, so it takes a second instead of
    minutes. The real size check is done by the normal  check  (without --only)."""
    eng = eng_cached(); tr, nfiles = load_translation(eng); tr = drop_untranslated(tr, eng)
    problems = 0; report = []; longer = []
    def say(kind_, k, msg):
        if only and not POS.get(k, '').startswith(only + ':'): return False
        if k in eng and kind_ != 'EXTRA': msg += '\n      الأصل الإنجليزي: ' + eng[k][:160].replace('\n', ' ')
        line = '%s  %s  [المكان: %s]  %s' % (kind(kind_), k, POS.get(k, '?'), msg) if LANG == 'ar' else '%-11s %s  [%s]  %s' % (kind_, k, POS.get(k, '?'), msg)
        print(line); report.append(line); return True
    net = 0
    for k, v in tr.items():
        if k not in eng:
            problems += bool(say('EXTRA', k, t('extra'))); continue
        a, e = sorted(TOK.findall(v)), sorted(TOK.findall(eng[k]))
        if a != e: problems += bool(say('PLACEHOLDER', k, t('ph', e, a)))
        bad = set(); b = encode(wrap_text(v, wrap_for(k, wrap)), bad)
        if bad: problems += bool(say('BADCHAR', k, ' '.join(sorted(bad)) + '   ' + t('badchar_hint') + ' [' + ''.join(sorted(AVAILABLE_CAPS)) + ']' + '\n      النص: ' + v[:120]))
        if not only or POS.get(k, '').startswith(only + ':'):
            d = len(b) - len(eng[k].encode('cp1252', 'replace')); net += d
            if d > 0: longer.append((d, k))
    longer.sort(reverse=True)
    if longer:
        print('أطول من الأصل (تنبيه فقط، الحجم الحقيقي يُفحص بالفحص الكامل): صافي الفرق %+d بايت' % net)
        for d, k in longer[:8]: print('        %+4d  %s' % (d, k))
    print('(فحص سريع: بدون فحص حجم الملفات. شغّل  python tools\\cod4.py check  بدون --only للحجم الحقيقي)')
    print(t('translated', len(tr) - sum(1 for k in tr if k not in eng), len(eng), len([k for k in eng if k not in tr]), nfiles))
    return problems

def cmd_fix(args):
    import shutil, time
    eng = eng_cached(); files = sorted(glob.glob(os.path.join(AR, '*.txt')))
    bak = os.path.join(ROOT, 'work', 'arabic_backup_' + time.strftime('%Y%m%d_%H%M%S')); made = False
    rep = []; total = 0
    def low(v):   # lowercase Latin capitals, but never touch tokens like ^1 %s &&1 [{+key}] \\n
        out = []; pos = 0
        for m in TOK.finditer(v):
            out.append(lower_unavailable(v[pos:m.start()])); out.append(m.group()); pos = m.end()
        out.append(lower_unavailable(v[pos:])); return ''.join(out)
    for pth in files:
        lines = open(pth, encoding='utf-8-sig').read().split('\n'); changed = False
        for i, line in enumerate(lines):
            raw = line.rstrip('\r')
            if not raw.strip() or raw.startswith('//') or '=' not in raw: continue
            k, v = raw.split('=', 1); key = clean_key(k); val = v.strip()
            if key != k.strip():      # key with a BOM / junk in front of it: rewrite it clean
                if not made: os.makedirs(bak); made = True
                if not os.path.exists(os.path.join(bak, os.path.basename(pth))): shutil.copy(pth, bak)
                lines[i] = '%s= %s' % (key + ' ', v.strip()) + ('\r' if line.endswith('\r') else ''); changed = True; total += 1
                rep.append('%s:%d  %s  [%s]' % (os.path.basename(pth), i + 1, key, t('fix_key_junk'))); k = key + ' '
            if key in eng and (re.fullmatch(r'[A-Z0-9]|F\d{1,2}', eng[key].strip()) or key in KEYNAMES) and val != lower_unavailable(eng[key].strip()):
                new = lower_unavailable(eng[key].strip())      # a single keyboard key label: the real keyboard is Latin, so it must stay a Latin letter (lowercase: capitals are Arabic shapes in this font)
                if not made: os.makedirs(bak); made = True
                if not os.path.exists(os.path.join(bak, os.path.basename(pth))): shutil.copy(pth, bak)
                lines[i] = '%s= %s' % (k, new) + ('\r' if line.endswith('\r') else ''); changed = True; total += 1
                rep.append('%s:%d  %s  [%s]\n    %s\n -> %s' % (os.path.basename(pth), i + 1, key, t('fix_key'), val, new)); continue
            if key not in eng or val == eng[key].strip() or not val: continue      # untranslated / unknown: not touched
            new = low(val); why = []
            if new != val: why.append(t('fix_case'))
            q = new.replace('\u00ab', '"').replace('\u00bb', '"').replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'").replace('\u2026', '...')
            if q != new: new = q; why.append(t('fix_quotes'))
            n2 = re.sub(r' {2,}', ' ', new).strip()
            if n2 != new: why.append(t('fix_sp')); new = n2
            if eng[key].rstrip().endswith('\\n') and not new.endswith('\\n') and TOK.findall(eng[key]).count('\\n') == TOK.findall(new).count('\\n') + 1:
                new += '\\n'; why.append(t('fix_nl'))
            if new != val:
                if not made: os.makedirs(bak); made = True
                if not os.path.exists(os.path.join(bak, os.path.basename(pth))): shutil.copy(pth, bak)
                lines[i] = '%s= %s' % (k, new) + ('\r' if line.endswith('\r') else ''); changed = True; total += 1
                rep.append('%s:%d  %s  [%s]\n    %s\n -> %s' % (os.path.basename(pth), i + 1, key, ' + '.join(why), val, new))
        if changed: open(pth, 'w', encoding='utf-8-sig', newline='').write('\n'.join(lines))
    if not total:
        print(t('fix_none')); n_tr = sum(1 for v in load_translation(eng)[0].values()); print('(%d translated lines scanned in %d files)' % (n_tr, len(files))); return 0
    print(t('fix_head', os.path.basename(bak)))
    open(os.path.join(ROOT, 'work', 'fix_report.txt'), 'w', encoding='utf-8-sig').write('\n'.join(rep) + '\n')
    print(t('fix_done', total)); return 0

CODEWORDS = {'self', 'level', 'if', 'else', 'while', 'wait', 'thread', 'return', 'script', 'array', 'trigger', 'origin', 'classname', 'targetname', 'model', 'angles', 'notify', 'waittill', 'endon', 'for', 'new', 'set', 'get', 'true', 'false'}

def cmd_scan(args):
    """Lists readable English sentences that are OUTSIDE the localized-text blocks of each .ff (work/other_text_report.txt).
    Nothing is changed. Use it to see whether a file holds text that the normal extraction does not cover (subtitles, dialogue, raw files)."""
    import zlib
    names = args or [os.path.basename(f) for f in sorted(glob.glob(os.path.join(IN, '*.ff')))]
    out = []; noise = re.compile(r'D3DX|Shader Compiler|breakpoint|script window|scroll bar|^[\W\d_]+$|\.cfg|^//|^set |^seta |exec ')
    for n in names:
        pth = n if os.path.isfile(n) else os.path.join(IN, n)
        try: raw = open(pth, 'rb').read(); d = zlib.decompress(raw[12:])
        except Exception as e: out.append('%s: cannot read (%s)' % (os.path.basename(pth), e)); continue
        cov = []; nent = 0
        try: f = ffcore.FF(pth); cov = [(r['start'], r['end']) for r in f.runs]; nent = len(f.ents)
        except Exception: pass
        rows = []; seen = set()
        for m in re.finditer(rb"[A-Za-z][A-Za-z ,'.!?:\-]{14,300}", d):       # plain prose only: letters, spaces and sentence punctuation
            if any(a <= m.start() < b for a, b in cov): continue
            s = m.group().decode('latin-1').strip(); w = s.split()
            if len(w) < 4 or not re.search('[a-z]{3}', s) or noise.search(s) or s in seen: continue
            if sum(1 for x in w if x.lower() in CODEWORDS) > 1: continue
            seen.add(s); rows.append('  @%d  %s' % (m.start(), s[:200]))
        out.append('=' * 60 + '\n%s : localized entries read: %d in %d block(s) | other readable sentences: %d' % (os.path.basename(pth), nent, len(cov), len(rows)))
        out += rows[:1500]
        if len(rows) > 1500: out.append('  ... %d more' % (len(rows) - 1500))
    txt = '\n'.join(out)
    open(os.path.join(ROOT, 'work', 'other_text_report.txt'), 'w', encoding='utf-8').write(txt)
    print(txt[:4000]); print('\nwork\\other_text_report.txt')
    return 0

def cmd_growtest(args):
    """Makes a TEST copy of ENGLISH .ff files in which texts are made longer, so the file has to grow. Copy it into zone\\english and look at the game:
    if it runs and the long texts are shown, growing is safe for that file. Nothing is installed, nothing in work\\input changes."""
    names = args or [os.path.basename(f) for f in sorted(glob.glob(os.path.join(IN, '*.ff')))]
    outd = os.path.join(OUT, 'growtest'); os.makedirs(outd, exist_ok=True)
    for n in names:
        pth = n if os.path.isfile(n) else os.path.join(IN, n if n.endswith('.ff') else n + '.ff')
        try: ff = ffcore.FF(pth)
        except Exception as ex: print('%s: skipped (%s)' % (os.path.basename(pth), str(ex)[:60])); continue
        ff.GROW_MAX_FALSE = 1e12; nv = {}
        for ri, r in enumerate(ff.runs):
            k = 0
            for e in r['ents']:
                if e['ext'] or e['vp'] != 0xFFFFFFFF or not e['val'].strip() or e['name'] in ('NULL_EMPTY',): continue
                nv[e['name']] = e['val'] + b' <GROW TEST>'; k += 1
                if k >= (400 if ri == 0 else 60): break
        st, pad = ff.render(nv, grow=True)
        if st is None: print(n, 'cannot grow:', pad); continue
        dst = os.path.join(outd, os.path.basename(pth)); ffcore.pack(dst, st, ff.version)
        chk = ffcore.FF(dst, starts=ff.last_starts)
        assert [e['name'] for e in chk.ents] == [e['name'] for e in ff.ents], 'read back differs'
        print('%s: +%d bytes per run %s | chance-match estimate %.1f | %d texts lengthened -> %s' % (os.path.basename(pth), sum(ff.last_grow), ff.last_grow, ff.last_risk, len(nv), dst))
    print('نسخ تجربة بمجلد work\\output\\growtest. انسخها لمجلد zone\\english (احتفظ بالأصلية) وشغّل اللعبة: النصوص تظهر وبعدها <GROW TEST>.')
    return 0

def cmd_find(args):
    """Ground-truth search: where is a text that you SAW in the game stored? Reads work\\seen_in_game.txt (one phrase per line, exactly as seen)
    or the phrases given as arguments, and looks for each of them in the .ff files (work\\input) and, if game_path.txt exists, in the game's .ff and .iwd files.
    For every hit it says whether it is inside the localized texts the tool already extracts (and which key), or somewhere else."""
    import zlib
    phrases = [a for a in args if not a.startswith('--')]
    if not phrases:
        fp = os.path.join(ROOT, 'work', 'seen_in_game.txt')
        if not os.path.exists(fp): sys.exit('اكتب بملف work\\seen_in_game.txt سطر لكل نص شفته باللعبة (نفس الكلمات بالضبط)، أو مرّر النص كوسيط.')
        phrases = [l.strip() for l in open(fp, encoding='utf-8-sig').read().split('\n') if l.strip() and not l.startswith('//')]
    def pat(p, enc):
        parts = [re.escape(w.encode(enc)) for w in p.split()]
        sep = rb'(?:\s|\\n|\\\\n)+' if enc == 'latin-1' else rb'(?:\s\x00|\\\x00n\x00)+'
        return re.compile(sep.join(parts), re.I | re.S)
    targets = []      # (label, bytes loader)
    for f in sorted(glob.glob(os.path.join(IN, '*.ff'))): targets.append((os.path.basename(f), f, 'ff'))
    gp = os.path.join(ROOT, 'game_path.txt'); game = open(gp).read().strip() if os.path.exists(gp) else None
    if game and os.path.isdir(game):
        have = {t_[0].lower() for t_ in targets}
        for f in sorted(glob.glob(os.path.join(game, 'zone', 'english', '*.ff')) + glob.glob(os.path.join(game, 'zone', 'english', '*.ff.bak'))):
            if os.path.basename(f).lower() not in have: targets.append(('game:' + os.path.basename(f), f, 'ff'))
        for f in sorted(glob.glob(os.path.join(game, 'main', '*.iwd'))): targets.append(('game:' + os.path.basename(f), f, 'iwd'))
    out = []; unfound = []
    pats = {p: [(pat(p, 'latin-1'), 'ASCII')] + ([(pat(p, 'utf-16-le'), 'UTF-16')] if p.isascii() else []) for p in phrases}
    hits = {p: [] for p in phrases}
    for label, path, kind in targets:
        blobs = []
        try:
            if kind == 'ff':
                d = zlib.decompress(open(path, 'rb').read()[12:]); ff = None
                try: ff = ffcore.FF(path)
                except Exception: pass
                blobs.append((label, d, ff))
            else:
                with zipfile.ZipFile(path) as z:
                    for i in z.infolist():
                        if i.file_size == 0 or i.filename.lower().endswith(('.iwi', '.wav', '.mp3', '.dds', '.png', '.jpg', '.ogg', '.roq', '.bik')): continue
                        if i.file_size > 60 * 2 ** 20: continue
                        blobs.append((label + ':' + i.filename, z.read(i), None))
        except Exception as ex: out.append('(%s: cannot read: %s)' % (label, str(ex)[:60])); continue
        for lab, d, ff in blobs:
            for p in phrases:
                for rx, enc in pats[p]:
                    for m in list(rx.finditer(d))[:3]:
                        where = 'outside the extracted texts'
                        if ff is not None:
                            for r in ff.runs:
                                if r['start'] <= m.start() < r['end']:
                                    key = next((e['name'] for e in r['ents'] if False), None); where = 'INSIDE the extracted texts (localized block)'
                        ctx = d[max(0, m.start() - 40): m.end() + 30].decode('latin-1' if enc == 'ASCII' else 'utf-16-le', 'replace').replace('\n', ' ').replace('\r', ' ')
                        hits[p].append('   %s  @%d  [%s]  %s\n        ...%s...' % (lab, m.start(), enc, where, re.sub(r'[^\x20-\x7e\u0600-\u06ff]', '.', ctx)))
    for p in phrases:
        out.append('=' * 60 + '\n"%s"' % p)
        if hits[p]: out += hits[p][:12]
        else: out.append('   NOT FOUND in any searched file (it may be drawn inside a video, or built from several pieces, or stored compressed/encoded)'); unfound.append(p)
    out.append('=' * 60 + '\nsearched %d files; %d of %d phrases not found' % (len(targets), len(unfound), len(phrases)))
    txt = '\n'.join(out); open(os.path.join(ROOT, 'work', 'find_report.txt'), 'w', encoding='utf-8').write(txt)
    print(txt[:6000]); print('\nwork\\find_report.txt')
    return 0

def cmd_keys(args):
    """Subtitle/text keys that the game DATA refers to but that no localized block defines (these would show as missing or raw text in the game).
    Looks at every .ff in work\\input: all words shaped like KEY_NAME_PART found outside the localized blocks, whose first part is a prefix that real keys use."""
    import zlib
    ffs = open_all(); eng = union_english(ffs); defined = set(eng)
    prefixes = {}
    for k in defined: prefixes[k.split('_')[0]] = prefixes.get(k.split('_')[0], 0) + 1
    prefixes = {p for p, n in prefixes.items() if n >= 3 and len(p) >= 4}
    rx = re.compile(rb'(?<![A-Za-z0-9_])[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+){1,}(?![A-Za-z0-9_])')
    out = []; total = {}
    for name, (ff, p) in ffs.items():
        d = ff.data; cov = [(r['start'], r['end']) for r in ff.runs]; seen = {}
        for m in rx.finditer(d):
            if any(a <= m.start() < b for a, b in cov): continue
            k = m.group().decode('latin-1')
            if k.split('_')[0] in prefixes and k not in defined: seen.setdefault(k, m.start())
        out.append('=' * 60 + '\n%s : keys the file refers to but nobody defines: %d' % (name, len(seen)))
        for k, pos in sorted(seen.items())[:200]: out.append('   %s   @%d' % (k, pos)); total[k] = total.get(k, 0) + 1
    out.append('=' * 60 + '\nthe keys above exist as words in the game data but have no text in any extracted block. Prefixes checked: %s' % ' '.join(sorted(prefixes)))
    txt = '\n'.join(out); open(os.path.join(ROOT, 'work', 'missing_keys_report.txt'), 'w', encoding='utf-8').write(txt)
    print(txt[:5000]); print('\nwork\\missing_keys_report.txt')
    return 0

def cmd_diagnose(args):
    names = args or [os.path.basename(f) for f in sorted(glob.glob(os.path.join(IN, '*.ff')))]
    out = []
    for n in names:
        pth = n if os.path.isfile(n) else os.path.join(IN, n)
        try: ffcore.FF(pth); out.append('%s: OK (readable)' % os.path.basename(pth)); continue
        except Exception as e:
            if 'no localized texts' in str(e): out.append('%s: NO TEXTS (normal, nothing to translate)' % os.path.basename(pth)); continue
            head = '%s: UNREADABLE (%s)' % (os.path.basename(pth), e)
        try: body = ffcore.diagnose(pth)
        except Exception as e: body = 'diagnose failed: %r' % e
        out.append('=' * 60 + '\n' + head + '\n' + body)
    txt = '\n'.join(out)
    open(os.path.join(ROOT, 'work', 'diagnose_report.txt'), 'w', encoding='utf-8').write(txt)
    print(txt); print('\nwork\\diagnose_report.txt')
    return 0

def cmd_review(args):
    # lists translated lines a human should look at (never changes anything)
    eng = eng_cached(); tr, _ = load_translation(eng); tr = drop_untranslated(tr, eng); rows = []
    for k, v in tr.items():
        if k not in eng: continue
        e = eng[k]; why = []
        ev = re.sub(r'\b(\d+)(st|nd|rd|th)\b', '', e)                       # ordinals (1st, 22nd) are usually written as words
        en_num = [n for n in re.findall(r'\d+', TOK.sub('', ev)) if n not in ('1', '2')]   # 1 and 2 are often written as words (واحد، اثنان)
        ar_num = re.findall(r'\d+', TOK.sub('', v))
        if any(n not in ar_num for n in en_num) or any(n not in re.findall(r'\d+', TOK.sub('', e)) for n in ar_num):
            why.append('رقم ناقص أو زائد: الأصل %s | الترجمة %s' % (sorted(set(en_num)), sorted(set(ar_num))))
        e2 = TOK.sub('', e).strip()      # looks like a code/path: one word with _ / \\ or a file extension, or only symbols
        if (re.fullmatch(r'\S+', e2) and re.search(r'[\\/_]|\.\w{2,4}$', e2)) or (e2 and not re.search(r'[A-Za-z0-9]', e2)): why.append('النص الأصلي يشبه رمزاً/مساراً (ربما ما يُترجم)')
        if len(e) > 12 and len(v) < len(e) * 0.25: why.append('الترجمة قصيرة جداً مقارنة بالأصل')
        if len(e) > 12 and len(v) > len(e) * 2.5: why.append('الترجمة طويلة جداً مقارنة بالأصل')
        if re.search(r'[A-Za-z]{4,}', TOK.sub('', re.sub(r'\S+\.(dat|cfg|iwd|ff|txt)\b', '', v))): why.append('بقيت كلمة إنجليزية بالترجمة')
        if why: rows.append('%s  [%s]\n    EN: %s\n    AR: %s\n    !! %s' % (k, POS.get(k, '?'), e, v, ' | '.join(why)))
    open(os.path.join(ROOT, 'work', 'review_report.txt'), 'w', encoding='utf-8-sig').write('\n\n'.join(rows) + '\n')
    print('%d سطر يحتاج مراجعة بشرية من %d مترجم. افتح work\\review_report.txt بالنوتباد.' % (len(rows), len(tr))); return 0

def cmd_longsubs(args):
    """Subtitles (dialogue) that will show on MORE THAN ONE LINE: keys that have their own width in tools/wrap.txt (SUBTITLE_, VIDSUBTITLES_ ...)
    whose Arabic text is longer than that width. On screen the lines scroll up and vanish fast, so a dialogue should be one short line.
    Writes work/long_subtitles_report.txt (EN and AR side by side). Never changes anything."""
    eng = eng_cached(); tr, _ = load_translation(eng); tr = drop_untranslated(tr, eng); rows = []; total = 0
    for k, v in tr.items():
        lim = wrap_for(k, DEFAULT_WRAP)
        if lim == DEFAULT_WRAP or k not in eng: continue
        total += 1
        n = sum(len(w) + 1 for w in re.sub(r'\^\d', '', TOK.sub('xxx', v.replace('\\n', ' '))).split(' ') if w) - 1
        if n > lim: rows.append((n - lim, '%s  [%s]  %d حرف (الحد %d، يزيد %d)\n    EN: %s\n    AR: %s' % (k, POS.get(k, '?'), n, lim, n - lim, eng[k], v)))
    rows.sort(key=lambda r: -r[0])
    head = 'حوارات (ترجمات لمفاتيح لها عرض خاص بـ wrap.txt) تطلع بأكثر من سطر: %d من %d. الأطول أولاً.\n' % (len(rows), total)
    open(os.path.join(ROOT, 'work', 'long_subtitles_report.txt'), 'w', encoding='utf-8-sig').write(head + '\n' + '\n\n'.join(r[1] for r in rows) + '\n')
    print(head.strip()); print('افتح work\\long_subtitles_report.txt'); return 0

def cmd_shortened(args):
    """Lists translated lines that look TRIMMED compared with the English (words dropped to save size when the old tool could not grow a file).
    Writes work/shortened_report.txt grouped by translation file (EN and AR side by side). Never changes anything.  --only=part003_ar.txt limits it to one file."""
    only = next((a.split('=', 1)[1] for a in args if a.startswith('--only=')), None)
    eng = eng_cached(); tr, _ = load_translation(eng); tr = drop_untranslated(tr, eng); rows = []
    for k, v in tr.items():
        if k not in eng: continue
        where = POS.get(k, '?')
        if only and not where.startswith(only + ':'): continue
        e = eng[k]; ec = TOK.sub(' ', e).replace('\\n', ' '); ac = TOK.sub(' ', v).replace('\\n', ' ')
        ew = re.findall(r"[A-Za-z][A-Za-z'\-]*|\d+", ec); aw = re.findall(r"[\u0600-\u06FFA-Za-z0-9][\u0600-\u06FFA-Za-z0-9'\-]*", ac)
        if not ew or not aw: continue
        why = []; ratio = len(aw) / len(ew)
        if len(ew) >= 5 and ratio < 0.6: why.append('كلمات الترجمة %d مقابل %d بالأصل' % (len(aw), len(ew)))
        if len(ec.strip()) >= 30 and len(ac.strip()) < len(ec.strip()) * 0.55: why.append('الترجمة أقصر بكثير بالحروف (%d مقابل %d)' % (len(ac.strip()), len(ec.strip())))
        se, sa = len(re.findall(r'[.!?](\s|$)', ec.strip() + ' ')), len(re.findall(r'[.!?؟](\s|$)', ac.strip() + ' '))
        if se >= 2 and sa < se: why.append('الأصل %d جمل والترجمة %d' % (se, sa))
        if why: rows.append((where.split(':')[0], int(where.split(':')[1]) if ':' in where and where.split(':')[1].isdigit() else 0, '%s  [%s]  نسبة الكلمات %.2f\n    EN: %s\n    AR: %s\n    !! %s' % (k, where, ratio, e, v, ' | '.join(why))))
    rows.sort(key=lambda r: (r[0], r[1]))
    out = []; cur = None; per = {}
    for f, ln, txt in rows:
        per[f] = per.get(f, 0) + 1
        if f != cur: out.append('=' * 70 + '\n' + f); cur = f
        out.append(txt)
    head = 'أسطر تبدو مقصوصة (%d سطر من %d مترجم). ملخص حسب الملف: %s\n' % (len(rows), len(tr), ' | '.join('%s: %d' % (f, n) for f, n in sorted(per.items())) or 'لا شي')
    open(os.path.join(ROOT, 'work', 'shortened_report.txt'), 'w', encoding='utf-8-sig').write(head + '\n' + '\n\n'.join(out) + '\n')
    print(head.strip()); print('افتح work\\shortened_report.txt'); return 0

def is_modded(ff):
    ne = next((e for e in ff.ents if e['name'] == 'NULL_EMPTY'), None)
    if (ne is not None and ne['val'] is not None and len(ne['val']) > 100): return True
    if b'gamefonts_ar' in ff.data: return True
    count = 0
    for e in ff.ents:
        if e['val'] and any(b >= 128 for b in e['val']):
            count += 1
            if count > 10: return True
    return False

SKIP_NAMES = re.compile(r'(^mp_|^localized_|^nazi_zombie|_mp(\.|_)|_load\.ff$|^default\.ff$|^common_ignore\.ff$)', re.I)      # multiplayer, zombies, loading screens, engine files

def fixgame(g):
    """accepts the game folder, or by mistake its zone\\english sub-folder, with or without a closing slash / quotes"""
    g = g.strip().strip('"').rstrip('\\/ ')
    n = os.path.normpath(g)
    if os.path.basename(n).lower() == 'english' and os.path.basename(os.path.dirname(n)).lower() == 'zone': n = os.path.dirname(os.path.dirname(n))
    return n

ZOMBIE_NAMES = re.compile(r'(localized_)?nazi_zombie(?!.*_load\.ff$)', re.I)

def cmd_import(args):
    """import GAMEFOLDER : looks at every .ff in zone\\english, keeps ONLY the single-player files that really hold texts, copies the originals
    to work\\input (a .bak is used when the game file was already translated) and writes tools\\ff_list.txt (the list used by 'apply' for players)."""
    if not args: sys.exit('usage: python tools/cod4.py import GAMEFOLDER   (the folder that has zone\\english)')
    g = fixgame(args[0]); ze = os.path.join(g, 'zone', 'english')
    if not os.path.isdir(ze): sys.exit(t('not_cod4', g))
    names = sorted({os.path.basename(f)[:-4] if f.endswith('.bak') else os.path.basename(f) for f in glob.glob(os.path.join(ze, '*.ff')) + glob.glob(os.path.join(ze, '*.ff.bak'))})
    zombies = '--zombies' in args      # also take the Nazi Zombies files (nazi_zombie_*, localized_nazi_zombie_*)
    for f in glob.glob(os.path.join(IN, '*.ff')): os.remove(f)
    keep = []; skipped = []
    for n in names:
        if SKIP_NAMES.search(n) and not (zombies and ZOMBIE_NAMES.match(n)): skipped.append(n); continue
        src = os.path.join(ze, n + '.bak')
        if not os.path.exists(src): src = os.path.join(ze, n)
        try:
            ff = ffcore.FF(src)
            if is_modded(ff): print(t('modded', n)); continue
            has = sum(1 for e in ff.ents if e['name'] != 'NULL_EMPTY' and not e['ext'])
        except Exception as e:
            print('  - %s: %s' % (n, e)); continue
        if has == 0: print('  - %s: بدون نصوص / no texts (skipped)' % n); continue
        shutil.copy2(src, os.path.join(IN, n)); keep.append(n); print('  + %s : %d texts' % (n, has))
    open(os.path.join(HERE, 'ff_list.txt'), 'w').write('\n'.join(keep) + '\n')
    print('تم: %d ملف للعب المنفرد فيه نصوص اننسخ إلى work\\input (تجاهلت %d ملف: جماعي/زومبي/تحميل/محرك). القائمة محفوظة بـ tools\\ff_list.txt' % (len(keep), len(skipped)))
    print('الخطوة التالية: 1_استخراج_النصوص.bat')

def cmd_apply(args):
    # one-step for the END USER: take the original .ff files from the game folder, apply the translation in work/arabic, build, install
    if not args: sys.exit(t('usage_install').replace('install', 'apply'))
    g = fixgame(args[0]); ze = os.path.join(g, 'zone', 'english')
    if not os.path.isdir(ze): sys.exit(t('not_cod4', g))
    lst = os.path.join(HERE, 'ff_list.txt')
    names = [x.strip() for x in open(lst).read().split() if x.strip()] if os.path.exists(lst) else sorted(os.path.basename(f) for f in glob.glob(os.path.join(ze, '*.ff')))
    if ONLY_FF is not None: names = [n for n in names if n.lower() in ONLY_FF]

    # Fast check: if no .bak files exist and the game is already translated, inform user immediately
    has_baks = any(os.path.exists(os.path.join(ze, n + '.bak')) for n in names)
    if not has_baks:
        iwd = os.path.join(g, 'main', IWD)
        is_translated = os.path.exists(iwd)
        if not is_translated:
            cp = os.path.join(ze, 'code_post_gfx.ff')
            if os.path.exists(cp):
                try:
                    import zlib
                    is_translated = b'gamefonts_ar' in zlib.decompress(open(cp, 'rb').read()[12:])
                except Exception: pass
        if is_translated:
            raise NeedOriginal('كل ملفات اللعبة معربة مسبقاً ولا توجد نسخ أصلية محفوظة (.bak). اللعبة معربة بالفعل! للبدء من جديد أعد التحقق من ملفات اللعبة عبر Steam أو أعد تثبيتها.')

    for f in glob.glob(os.path.join(IN, '*.ff')): os.remove(f)
    n_ok = 0; n_mod = 0; total = len(names)
    for i, n in enumerate(names, 1):
        src = os.path.join(ze, n + '.bak')
        is_backup = os.path.exists(src)
        if not is_backup: src = os.path.join(ze, n)
        if not os.path.exists(src): print('  - ' + n + ': ' + ('غير موجود بمجلد اللعبة' if LANG == 'ar' else 'not found in the game folder')); continue
        dst = os.path.join(IN, n); shutil.copy2(src, dst)
        if not is_backup:
            try: ff = ffcore.FF(dst)
            except Exception as e: os.remove(dst); print('  - %s: %s' % (n, e)); continue
            if is_modded(ff): os.remove(dst); print(t('modded', n)); n_mod += 1; continue
        n_ok += 1
        pct = int(10 * i / max(1, total))
        print('[PROGRESS:%d] فحص ونسخ: %s (%d/%d)' % (pct, n, i, total))
    if not n_ok:
        if n_mod: raise NeedOriginal('كل ملفات اللعبة معربة مسبقاً ولا توجد نسخ أصلية محفوظة (.bak). أعد تثبيت اللعبة أو تحقق من ملفاتها عبر Steam ثم أعد المحاولة.')
        sys.exit(t('nothing'))
    cmd_build([]); cmd_install([g])
    for d in (IN, OUT):      # the copies of the game files are no longer needed (they can be 2 GB)
        for r, _, fl in os.walk(d):
            for f in fl:
                if f.endswith(('.ff', '.iwd', '.iwi')): os.remove(os.path.join(r, f))
    print(t('cleaned'))

def cmd_release(args):
    # for the translator: makes a small zip (tools + translations, NO game files) to give to other people
    out = os.path.join(ROOT, 'work', 'release'); os.makedirs(out, exist_ok=True)
    names = sorted(open_all().keys())
    open(os.path.join(HERE, 'ff_list.txt'), 'w').write('\n'.join(names) + '\n')
    zp = os.path.join(out, 'cod4_arabic_translation.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk(HERE):
            if '__pycache__' in root: continue
            for f in fs:
                if f in ('last_output.txt',): continue
                z.write(os.path.join(root, f), os.path.join('tools', os.path.relpath(os.path.join(root, f), HERE)))
        for f in glob.glob(os.path.join(AR, '*.txt')): z.write(f, os.path.join('work', 'arabic', os.path.basename(f)))
        for b in ('5_استرجاع_الأصلي.bat',): z.write(os.path.join(ROOT, b), b)
        z.write(os.path.join(ROOT, 'USER_README.txt'), 'اقرأني.txt')
        z.write(os.path.join(ROOT, '9_تطبيق_ترجمة_جاهزة.bat'), '9_تطبيق_ترجمة_جاهزة.bat')
        z.writestr('work/input/.keep', ''); z.writestr('work/english/.keep', ''); z.writestr('work/output/.keep', '')
    print('%s  (%d ملف ff, %d ملف ترجمة, %.1f MB)' % (zp, len(names), len(glob.glob(os.path.join(AR, '*.txt'))), os.path.getsize(zp) / 1e6))
    return 0

def cmd_check(args):
    wrap = next((int(a.split('=')[1]) for a in args if a.startswith('--wrap=')), DEFAULT_WRAP)
    only = next((a.split('=', 1)[1] for a in args if a.startswith('--only=')), None)
    if ('--quick' in args or only) and '--full' not in args: problems = analyse_quick(wrap, only)
    else: _, _, problems = analyse(wrap, only)
    print(t('done_check', problems)); return problems

def cmd_build(args):
    wrap = next((int(a.split('=')[1]) for a in args if a.startswith('--wrap=')), DEFAULT_WRAP)
    ffs, results, problems = analyse(wrap)
    bad_in = [n for n, (ff, p) in ffs.items() if is_modded(ff)]
    if bad_in: sys.exit('توقف: الملفات التالية بمجلد work\\input مو أصلية (معرَّبة أو معدّلة من قبل): %s\nالبناء فوقها يطلّع حروف مشوهة أو خطأ gamefonts_ar. حط النسخ الأصلية (تاريخها 2020، أو Verify integrity من ستيم) بمجلد work\\input وكرر.' % ', '.join(bad_in))
    if problems: sys.exit(t('fix_first'))
    # font: tables are made from the first file and applied to all (same letters required)
    base = None; made = None; os.makedirs(os.path.join(OUT, 'zone', 'english'), exist_ok=True); os.makedirs(os.path.join(OUT, 'main'), exist_ok=True)
    slot = SMAP        # slotmap.json adjusted by tools/keep_caps.txt (kept capitals stay real letters)
    pack_items = []
    for name, (ff, p) in ffs.items():
        stream = results[name][0]
        try: fonts = fontlib.find_fonts(stream)
        except Exception: fonts = None
        if fonts and len(fonts) == 7 and not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),'no_font.txt')):
            if made is None:
                sm, _ = fontlib.make_slotmap(fonts)
                if sm != SMAP_BASE: sys.exit(t('slot_bad'))
                fontlib.FREED_ASCII[:] = [c for c in fontlib.FREED_ASCII if c not in AVAILABLE_CAPS]      # kept capitals (and X Y Z) are drawn as normal letters
                fx = fontlib.expand_fonts(fonts) if GROW else fonts       # GROW: tools/font_grow.txt = on  -> 23 more records per font table
                _o = os.path.join(HERE, 'waw_original_gamefonts_pc.iwi')
                orig = fontlib.read_iwi_alpha(_o) if os.path.exists(_o) else None          # World at War: keep the game's own Latin glyphs
                atlas, made, _ = fontlib.build_glyphs(fx, slot, orig=orig); base = fonts
                iwi = os.path.join(OUT, 'gamefonts_ar.iwi'); fontlib.write_iwi(atlas, iwi)
                with zipfile.ZipFile(os.path.join(OUT, 'main', IWD), 'w', zipfile.ZIP_DEFLATED) as z: z.write(iwi, 'images/gamefonts_ar.iwi')
                os.remove(iwi); atlas.save(os.path.join(OUT, 'atlas_preview.png'))
            if any([r[0] for r in fonts[n]['recs']] != [r[0] for r in base[n]['recs']] for n in made):
                sys.exit(t('font_layout', name))
            stream = fontlib.rename_image(fontlib.patch_stream(stream, fonts, made))
            note = t('font_ok')
        else: note = t('font_none')
        pack_items.append((name, os.path.join(OUT, 'zone', 'english', name), stream, ff.version, note))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    def _pack_file(item):
        n, out_p, strm, ver, nt = item
        ffcore.pack(out_p, strm, ver)
        return n, nt

    total_ff = len(pack_items)
    workers = min(6, max(2, (os.cpu_count() or 4) - 1))
    done_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_pack_file, it): it[0] for it in pack_items}
        for fut in as_completed(futures):
            done_count += 1
            n, nt = fut.result()
            pct = 10 + int(75 * done_count / max(1, total_ff))
            print('[PROGRESS:%d] بناء: %s (%d/%d)' % (pct, n, done_count, total_ff))
            print(t('built', n, nt))
    print('\n== ملخص البناء / build summary ==')
    print('ملفات بـ work\\input: %d | انبنت: %d | بدون نصوص أو ما انقرأت: %d' % (len(ffs) + len(NOT_READ), len(ffs), len(NOT_READ)))
    for b, why in NOT_READ: print('   %-34s %s' % (b, why))
    if made is None: print('تحذير: ما لقيت جداول الخط بأي ملف انبنى، فصورة الخط ما انسوّت (لازم تبني code_post_gfx.ff و localized_code_post_gfx_mp.ff).')
    print(t('build_ok', IWD))

class NeedOriginal(SystemExit):
    """every game file is already translated and no saved original exists: the window shows a clear message"""

KEEP_BACKUP = True      # False (the window's checkbox): install without saving the original files as .ff.bak (the player then cannot restore from here)

def cmd_install(args):
    if not args: sys.exit(t('usage_install'))
    g = fixgame(args[0]); ze = os.path.join(g, 'zone', 'english')
    if not os.path.isdir(ze): sys.exit(t('not_cod4', g))
    test = '--from=growtest' in args      # install the TEST copies made by growtest (English, longer texts) instead of the real build
    src = os.path.join(OUT, 'growtest') if test else os.path.join(OUT, 'zone', 'english'); fs = glob.glob(os.path.join(src, '*.ff'))
    if ONLY_FF is not None: fs = [f for f in fs if os.path.basename(f).lower() in ONLY_FF]
    if not fs: sys.exit(t('not_built'))
    total_inst = len(fs) + 1
    for idx, f in enumerate(fs, 1):
        dst = os.path.join(ze, os.path.basename(f))
        if KEEP_BACKUP and os.path.exists(dst) and not os.path.exists(dst + '.bak'):
            try: cur_mod = is_modded(ffcore.FF(dst))
            except Exception: cur_mod = b'gamefonts_ar' in open(dst, 'rb').read()
            if cur_mod: sys.exit('توقف: ملف اللعبة %s معدّل أصلاً (فيه الخط العربي) وما عندي نسخة .bak له، فلا أقدر آخذه نسخة احتياطية على أنه الأصلي. رجّع الأصلي أولاً (ستيم: Verify integrity of game files) وكرر التركيب.' % os.path.basename(dst))
            shutil.copy2(dst, dst + '.bak'); print(t('backup', os.path.basename(dst) + '.bak'))
        shutil.copy2(f, dst)
        pct = 85 + int(14 * idx / max(1, total_inst))
        print('[PROGRESS:%d] تثبيت: %s (%d/%d)' % (pct, os.path.basename(f), idx, len(fs)))
        print(t('installed', os.path.basename(f)))
    if not KEEP_BACKUP: print('No copy of the original files was kept (as requested). Existing .bak files were left as they are.')
    built = os.path.join(OUT, 'main', IWD)
    if os.path.exists(built) and not test:
        main = os.path.join(g, 'main'); os.makedirs(main, exist_ok=True)
        name = pick_iwd(main)
        if name is None: sys.exit(t('iwd_full'))
        if name != IWD: print(t('iwd_taken', IWD, name))
        for p in our_iwds(main):                      # an older copy of OUR font file under another name (never a game file)
            if os.path.basename(p).lower() != name.lower(): os.remove(p)
        shutil.copy2(built, os.path.join(main, name)); print(t('installed', 'main\\' + name))
    print('[PROGRESS:100] اكتمل التثبيت بنجاح')

def cmd_restore(args):
    """Puts the saved originals (.ff.bak) back. Returns 'ok' | 'partial' (some translated files have no saved original) | 'none' (nothing could be restored)."""
    if not args: sys.exit(t('usage_install').replace('install', 'restore'))
    g = fixgame(args[0]); ze = os.path.join(g, 'zone', 'english'); done = []
    baks = [b for b in glob.glob(os.path.join(ze, '*.ff.bak')) if ONLY_FF is None or os.path.basename(b)[:-4].lower() in ONLY_FF]
    total_baks = len(baks)
    for idx, b in enumerate(baks, 1):
        shutil.copy2(b, b[:-4]); done.append(os.path.basename(b)[:-4])
        pct = int(90 * idx / max(1, total_baks))
        print('[PROGRESS:%d] استرجاع: %s (%d/%d)' % (pct, os.path.basename(b)[:-4], idx, total_baks))
        print(t('restored', os.path.basename(b)[:-4]))
    if ONLY_FF is not None:
        print('[PROGRESS:100] اكتمل استرجاع الملفات')
        return 'ok'
    lst = os.path.join(HERE, 'ff_list.txt')
    names = [x.strip() for x in open(lst).read().split() if x.strip()] if os.path.exists(lst) else sorted(os.path.basename(f) for f in glob.glob(os.path.join(ze, '*.ff')))
    left = []
    for n in names:
        p = os.path.join(ze, n)
        if n in done or not os.path.exists(p): continue
        try: still = is_modded(ffcore.FF(p))
        except Exception: still = False
        if still: left.append(n)
    if left:
        print('No saved original for: %s' % ', '.join(left))
        print('The Arabic font file was kept so these files still show correctly. To get the original game back, verify the game files (Steam) or reinstall the game.')
        print('[PROGRESS:100] استرجاع جزئي')
        return 'partial' if done else 'none'
    for p in our_iwds(os.path.join(g, 'main')): os.remove(p); print(t('removed', os.path.basename(p)))
    if not done: print('Nothing was translated in this game folder.')
    print('[PROGRESS:100] اكتملت استعادة النسخة الأصلية بنجاح')
    return 'ok'

class Tee:
    def __init__(self, f): self.f = f; self.o = sys.stdout
    def write(self, x): self.o.write(x); self.f.write(x)
    def flush(self): self.o.flush(); self.f.flush()

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('extract', 'check', 'fix', 'diagnose', 'scan', 'find', 'keys', 'growtest', 'review', 'shortened', 'longsubs', 'build', 'install', 'restore', 'apply', 'import', 'release'): sys.exit(__doc__)
    sys.stdout = Tee(open(os.path.join(ROOT, 'work', 'last_output.txt'), 'w', encoding='utf-8-sig'))   # same text is saved for Notepad
    r = globals()['cmd_' + sys.argv[1]](sys.argv[2:])
    if sys.argv[1] == 'check' and r: sys.exit(1)
