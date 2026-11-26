# -*- coding: utf-8 -*-
"""Simple window for the players (opened by user_app.py): finds the game folder by itself, buttons Install Arabic / Restore original.
The Arabic text of the window is drawn as PICTURES with the same shaper + font the game patch uses, so it looks right on every Windows
(it does not depend on the text engine of Tk or of Windows). The work itself is done by cod4.cmd_apply / cod4.cmd_restore in a thread."""
import os, io, glob, base64, threading, queue, contextlib
import shaper
from PIL import Image, ImageDraw, ImageFont

BG, PANEL, FG, DIM, GOOD, BAD = '#15181b', '#1f252b', '#e9e7dc', '#97a1a7', '#9cc447', '#e2826a'
BUTTONS = {
    'install': ('#6f8f2a', '#86a83a'),
    'restore': ('#7a4a3c', '#955b49'),
    'browse': ('#34414c', '#47596b'),
    'delete': ('#442d32', '#5c3d44')
}
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')

MSG = {
    'searching': 'جارٍ البحث عن مجلد اللعبة...',
    'found': 'تم العثور على اللعبة. اضغط تركيب العربي.',
    'notfound': 'لم أجد اللعبة. اضغط تغيير واختر مجلد اللعبة، وهو المجلد الذي يحتوي على zone و main.',
    'invalid': 'هذا ليس مجلد اللعبة. يجب أن يحتوي على zone و main.',
    'pick': 'اختر مجلد اللعبة أولاً بزر تغيير.',
    'installing': 'جارٍ التركيب... يرجى الانتظار.',
    'restoring': 'جارٍ إرجاع الملفات الأصلية...',
    'done_install': 'تم التركيب بنجاح! شغّل اللعبة الآن.',
    'done_restore': 'تمت إعادة الملفات الأصلية.',
    'error': 'حدث خطأ. اقرأ السجل في الأسفل.',
    'busy': 'لا تغلق النافذة أثناء العمل.',
    'footer': 'يحتاج مساحة فارغة مؤقتة أثناء البناء، وتُحذف تلقائياً بعد انتهاء التركيب.',
    'keep': 'الاحتفاظ بنسخة من الملفات الأصلية للإرجاع لاحقاً',
    'keep_off': 'تنبيه: بدون هذا الخيار لن تستطيع الإرجاع من هنا، وستحتاج إعادة تثبيت اللعبة أو التحقق من ملفاتها في Steam.',
    'nobackup': 'لا توجد نسخ محفوظة من الملفات الأصلية، لذلك لا يمكن الإرجاع من هنا. أعد تثبيت اللعبة أو تحقق من ملفاتها في Steam.',
    'partial': 'تم إرجاع بعض الملفات فقط. الباقي ليس له نسخة محفوظة، فأعد تثبيت اللعبة أو تحقق من ملفاتها في Steam.',
    'needorig': 'ملفات اللعبة مترجمة سابقاً وليس لها نسخة أصلية محفوظة. أعد تثبيت اللعبة أو تحقق من ملفاتها في Steam ثم كرر التركيب.',
    'nobak_found': 'لا توجد أي ملفات نسخ احتياطي (.bak) في مجلد اللعبة.',
    'bak_deleted': 'تم حذف ملفات النسخ الاحتياطي وتوفير المساحة بنجاح.',
    'credit': 'تعريب وتطوير: REDADEV',
}

# ---------- pictures with Arabic text ----------
def _font(size, bold=True):
    return ImageFont.truetype(os.path.join(FONT_DIR, 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'), size, layout_engine=ImageFont.Layout.BASIC)

def _vis(s):
    return ''.join(chr(c) for c in shaper.visual(s))

def ar_image(text, size=18, color=FG, bg=BG, bold=True, width=None):
    """Arabic (and mixed) text as an RGB picture, centred, wrapped to `width` pixels when given."""
    f = _font(size, bold); lines = []; cur = ''
    for w in text.split(' '):
        t = (cur + ' ' + w).strip()
        if width and cur and f.getlength(_vis(t)) > width: lines.append(cur); cur = w
        else: cur = t
    lines.append(cur)
    vis = [_vis(l) for l in lines]; lh = int(size * 1.6)
    W = max(int(max(f.getlength(v) for v in vis)) + 6, width or 0)
    img = Image.new('RGB', (W, lh * len(vis) + 6), bg); d = ImageDraw.Draw(img)
    for i, v in enumerate(vis): d.text(((W - f.getlength(v)) / 2, i * lh + 3), v, font=f, fill=color)
    return img

def button_image(text, w, h, bg, fg=FG, size=20, outer=PANEL):
    img = Image.new('RGB', (w, h), outer); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 4, fill=bg)
    f = _font(size); v = _vis(text); tw = f.getlength(v)
    d.text(((w - tw) / 2, (h - size * 1.25) / 2 - 1), v, font=f, fill=fg)
    return img

def b64(img):
    buf = io.BytesIO(); img.save(buf, 'PNG'); return base64.b64encode(buf.getvalue())

# ---------- the job (no Tk inside, so it can be tested alone) ----------
class _Emit(io.TextIOBase):
    def __init__(self, emit): self.emit = emit; self.buf = ''
    def write(self, s):
        self.buf += s
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            if line.strip(): self.emit(line.rstrip())
        return len(s)
    def flush(self):
        if self.buf.strip(): self.emit(self.buf.rstrip())
        self.buf = ''

def run_job(cod4, kind, game, emit, keep_backup=True):
    """Runs the install (cod4.cmd_apply) or the restore (cod4.cmd_restore) and sends every printed line to emit().
    Returns 'ok' | 'error' | 'needorig' (install: the files are already translated and no original is saved) | (restore only) 'partial' | 'none'."""
    w = _Emit(emit); status = 'ok'; cod4.KEEP_BACKUP = bool(keep_backup)
    try:
        with contextlib.redirect_stdout(w), contextlib.redirect_stderr(w):
            r = (cod4.cmd_apply if kind == 'install' else cod4.cmd_restore)([game])
        if kind == 'restore' and r in ('partial', 'none'): status = r
    except cod4.NeedOriginal as e:
        emit(str(e.code)); status = 'needorig'
    except SystemExit as e:
        if e.code not in (None, 0): emit(str(e.code)); status = 'error'
    except Exception as e:
        emit('ERROR: %s' % e); status = 'error'
    finally:
        w.flush()
    return status

# ---------- the window ----------
def run(cod4, find_games, is_game, arg=None):
    global FONT_DIR
    FONT_DIR = os.path.join(cod4.HERE, 'fonts') if os.path.isdir(os.path.join(cod4.HERE, 'fonts')) else FONT_DIR
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk(); root.title('Call of Duty: World at War Arabic - REDADEV'); root.configure(bg=BG); root.resizable(False, False)
    W, H = 640, 750
    root.geometry('%dx%d+%d+%d' % (W, H, (root.winfo_screenwidth() - W) // 2, max(10, (root.winfo_screenheight() - H) // 3)))
    keep = []                                            # Tk forgets pictures nobody holds
    def pic(img): p = tk.PhotoImage(data=b64(img)); keep.append(p); return p
    q = queue.Queue(); state = {'busy': False, 'game': None}

    tk.Label(root, image=pic(ar_image('تعريب Call of Duty: World at War', 28)), bg=BG).pack(pady=(20, 0))
    tk.Label(root, image=pic(ar_image('ترجمة القصة (اللعب المنفرد)', 16, DIM, bold=False)), bg=BG).pack(pady=(0, 14))

    panel = tk.Frame(root, bg=PANEL); panel.pack(fill='x', padx=26, ipady=12); panel.columnconfigure(1, weight=1)
    tk.Label(panel, image=pic(ar_image('مجلد اللعبة', 16, bg=PANEL)), bg=PANEL).grid(row=0, column=2, padx=(10, 16))
    combo = ttk.Combobox(panel, state='readonly', font=('Segoe UI', 10)); combo.grid(row=0, column=1, sticky='ew')

    def make_button(parent, text, kind, w, h, size, command):
        n, hov = BUTTONS[kind]; outer = parent['bg']
        imgs = {'n': pic(button_image(text, w, h, n, size=size, outer=outer)), 'h': pic(button_image(text, w, h, hov, size=size, outer=outer)),
                'd': pic(button_image(text, w, h, '#2a3036', DIM, size=size, outer=outer))}
        lab = tk.Label(parent, image=imgs['n'], bg=outer, bd=0, cursor='hand2'); lab.enabled = True
        lab.bind('<Enter>', lambda e: lab.enabled and lab.configure(image=imgs['h']))
        lab.bind('<Leave>', lambda e: lab.enabled and lab.configure(image=imgs['n']))
        lab.bind('<Button-1>', lambda e: lab.enabled and command())
        lab.set_enabled = lambda on: (setattr(lab, 'enabled', on), lab.configure(image=imgs['n'] if on else imgs['d'], cursor='hand2' if on else 'arrow'))
        return lab

    status = tk.Label(root, bg=BG)
    def say(key, color=FG):
        p = tk.PhotoImage(data=b64(ar_image(MSG[key], 17, color, width=580))); status.image = p; status.configure(image=p)

    def set_game(path):
        state['game'] = path; combo.set(path)
    def browse():
        if state['busy']: return
        p = filedialog.askdirectory(title='Select the Call of Duty: World at War folder (it contains zone and main)')
        if not p: return
        p = os.path.normpath(p)
        if is_game(p):
            vals = list(combo['values']); vals = vals if p in vals else vals + [p]; combo['values'] = vals; set_game(p); say('found', GOOD)
        else: say('invalid', BAD)
    def on_combo(_e=None):
        if is_game(combo.get()): state['game'] = combo.get()
    combo.bind('<<ComboboxSelected>>', on_combo)
    make_button(panel, 'تغيير', 'browse', 96, 36, 17, browse).grid(row=0, column=0, padx=(14, 10))

    status.pack(pady=(14, 6))
    row = tk.Frame(root, bg=BG); row.pack(pady=(2, 4)); row.columnconfigure((0, 1), weight=1)
    b_install = make_button(row, 'تركيب العربي', 'install', 270, 58, 23, lambda: start('install'))
    b_restore = make_button(row, 'إرجاع الأصلي', 'restore', 270, 58, 23, lambda: start('restore'))
    b_install.grid(row=0, column=1, padx=8); b_restore.grid(row=0, column=0, padx=8)

    keep_var = tk.BooleanVar(value=True)                 # keep a copy of the original files (default: yes)
    krow = tk.Frame(root, bg=BG); krow.pack(pady=(4, 0))
    note = tk.Label(root, image=pic(ar_image(MSG['keep_off'], 13, BAD, width=560)), bg=BG)
    def on_keep():
        if keep_var.get(): note.pack_forget()
        else: note.pack(after=krow, pady=(4, 0))
    chk = tk.Checkbutton(krow, variable=keep_var, command=on_keep, bg=BG, activebackground=BG, selectcolor=PANEL, highlightthickness=0, bd=0, cursor='hand2')
    chk.pack(side='right')
    klab = tk.Label(krow, image=pic(ar_image(MSG['keep'], 15, FG, bold=False)), bg=BG, cursor='hand2'); klab.pack(side='right', padx=(0, 4))
    klab.bind('<Button-1>', lambda e: (not state['busy']) and (keep_var.set(not keep_var.get()), on_keep()))

    def on_delete_backups():
        if state['busy']: return
        g = state['game']
        if not g or not is_game(g): say('pick', BAD); return
        ze = os.path.join(g, 'zone', 'english')
        if not os.path.isdir(ze): say('invalid', BAD); return
        bak_files = []
        for pat in ('*.bak', '*.translated_bak'):
            bak_files.extend(glob.glob(os.path.join(ze, pat)))
        bak_files = sorted(list(set(bak_files)))
        if not bak_files:
            say('nobak_found', DIM)
            log_add('لا توجد أي ملفات نسخ احتياطي (.bak) في مجلد اللعبة.')
            return
        total_bytes = sum(os.path.getsize(p) for p in bak_files if os.path.exists(p))
        size_mb = total_bytes / (1024 * 1024)
        size_gb = total_bytes / (1024 * 1024 * 1024)
        size_str = '%.2f GB' % size_gb if size_gb >= 1.0 else '%.1f MB' % size_mb
        ans = messagebox.askyesno(
            'تأكيد حذف النسخ الاحتياطية',
            f'تم العثور على {len(bak_files)} ملف احتياطي بحجم إجمالي {size_str}.\n\n'
            'هل أنت متأكد من رغبتك في حذف هذه الملفات لتوفير المساحة على القرص؟\n\n'
            'تنبيه: بعد حذف النسخ الاحتياطية لن تتمكن من استرجاع الملفات الأصلية عبر زر «إرجاع الأصلي» إلا بإعادة تثبيت اللعبة أو التحقق من ملفاتها في Steam.',
            parent=root
        )
        if not ans: return
        log_add('-' * 40)
        log_add(f'جارٍ حذف {len(bak_files)} ملف احتياطي لتوفير {size_str}...')
        del_count = 0; freed = 0
        for p in bak_files:
            try:
                sz = os.path.getsize(p)
                os.remove(p)
                del_count += 1; freed += sz
                log_add('تم حذف: %s (%.1f MB)' % (os.path.basename(p), sz / (1024 * 1024)))
            except Exception as e:
                log_add('تعذر حذف %s: %s' % (os.path.basename(p), e))
        freed_gb = freed / (1024 * 1024 * 1024)
        freed_str = '%.2f GB' % freed_gb if freed_gb >= 1.0 else '%.1f MB' % (freed / (1024 * 1024))
        say('bak_deleted', GOOD)
        log_add(f'اكتمل الحذف: تم حذف {del_count} ملف وتوفير {freed_str} بنجاح.')

    del_row = tk.Frame(root, bg=BG); del_row.pack(pady=(6, 0))
    b_delbak = make_button(del_row, 'حذف ملفات النسخ الاحتياطي (.bak) لتوفير المساحة', 'delete', 370, 32, 14, on_delete_backups)
    b_delbak.pack()

    style = ttk.Style(root)
    try: style.theme_use('clam')
    except tk.TclError: pass
    style.configure('G.Horizontal.TProgressbar', troughcolor=PANEL, background=GOOD, bordercolor=BG, lightcolor=GOOD, darkcolor=GOOD)
    bar = ttk.Progressbar(root, mode='determinate', maximum=100, length=588, style='G.Horizontal.TProgressbar')
    prog_label = tk.Label(root, bg=BG)

    def set_progress(pct, desc):
        bar['value'] = pct
        txt = 'التقدم: %d%% | %s' % (pct, desc)
        p = tk.PhotoImage(data=b64(ar_image(txt, 14, GOOD, width=580, bold=False)))
        prog_label.image = p; prog_label.configure(image=p)
        root.update_idletasks()

    log = tk.Text(root, height=7, bg='#0e1114', fg='#b8c0c4', font=('Consolas', 9), bd=0, wrap='word', state='disabled', highlightthickness=0)
    log.pack(fill='both', expand=True, padx=26, pady=(6, 4))
    foot = pic(ar_image(MSG['footer'], 12, DIM, bold=False, width=580)); tk.Label(root, image=foot, bg=BG).pack(pady=(2, 0))
    tk.Label(root, image=pic(ar_image(MSG['credit'], 13, GOOD, bold=False)), bg=BG).pack(pady=(2, 12))

    def log_add(s):
        log.configure(state='normal'); log.insert('end', s + '\n'); log.see('end'); log.configure(state='disabled')
    def buttons(on):
        b_install.set_enabled(on); b_restore.set_enabled(on); b_delbak.set_enabled(on); chk.configure(state='normal' if on else 'disabled')
    def start(kind):
        if state['busy']: return
        g = state['game']
        if not g or not is_game(g): say('pick', BAD); return
        state['busy'] = True; buttons(False)
        prog_label.pack(before=log, pady=(2, 2))
        bar.pack(before=log, padx=26, pady=(2, 6))
        set_progress(0, 'بدء العمل...')
        say('installing' if kind == 'install' else 'restoring')
        log_add('-' * 40)
        keepflag = keep_var.get()
        def work(): q.put(('done', (kind, run_job(cod4, kind, g, lambda s: q.put(('line', s)), keepflag))))
        threading.Thread(target=work, daemon=True).start()
    def finish(kind, result):
        state['busy'] = False; bar.pack_forget(); prog_label.pack_forget(); buttons(True)
        if result == 'ok': say('done_install' if kind == 'install' else 'done_restore', GOOD)
        elif result in ('partial', 'none', 'needorig'): say({'partial': 'partial', 'none': 'nobackup', 'needorig': 'needorig'}[result], BAD)
        else: say('error', BAD)
    def poll():
        try:
            count = 0
            while count < 40:
                k, v = q.get_nowait()
                count += 1
                if k == 'line':
                    if v.startswith('[PROGRESS:'):
                        try:
                            end_bracket = v.find(']')
                            pct = int(v[10:end_bracket])
                            desc = v[end_bracket + 1:].strip()
                            set_progress(pct, desc)
                        except Exception: pass
                    else:
                        log_add(v)
                elif k == 'done': finish(*v)
                elif k == 'games':
                    if v: combo['values'] = v; set_game(v[0]); say('found', GOOD)
                    else: say('notfound', BAD)
        except queue.Empty: pass
        root.after(30, poll)
    def on_close():
        if state['busy']: say('busy', BAD)
        else: root.destroy()
    root.protocol('WM_DELETE_WINDOW', on_close)

    if is_game(arg): combo['values'] = [arg]; set_game(arg); say('found', GOOD)      # a folder dragged onto the program
    else:
        say('searching'); threading.Thread(target=lambda: q.put(('games', find_games())), daemon=True).start()
    poll(); root.mainloop()
