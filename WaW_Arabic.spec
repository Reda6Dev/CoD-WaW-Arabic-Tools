# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tools/user_app.py'],
    pathex=['tools'],
    binaries=[],
    datas=[('tools/slotmap.json', '.'), ('tools/fonts', 'fonts'), ('tools/wrap.txt', '.'), ('tools/lang.txt', '.'), ('tools/iwd_name.txt', '.'), ('tools/font_grow.txt', '.'), ('tools/keep_caps.txt', '.'), ('tools/font_weight.txt', '.'), ('tools/font_scale.txt', '.'), ('tools/size_grow.txt', '.'), ('tools/ff_list.txt', '.'), ('tools/waw_original_gamefonts_pc.iwi', '.'), ('work/arabic', 'work_arabic')],
    hiddenimports=['gui_app', 'tkinter'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WaW_Arabic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
