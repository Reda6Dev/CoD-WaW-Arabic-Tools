@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem For the TRANSLATOR (needs Python): makes ONE file, dist\WaW_Arabic.exe, that players can run without installing Python.
rem The translations in work\arabic and tools\ff_list.txt are bundled inside it (run 8_تجهيز_نسخة_للتوزيع.bat first so ff_list.txt is up to date).
python tools\cod4.py release
python -m pip install --upgrade pyinstaller pillow numpy
python -m PyInstaller --onefile --windowed --clean --hidden-import gui_app --hidden-import tkinter --name WaW_Arabic --paths tools ^
  --add-data "tools\slotmap.json;." --add-data "tools\fonts;fonts" --add-data "tools\wrap.txt;." --add-data "tools\lang.txt;." ^
  --add-data "tools\iwd_name.txt;." --add-data "tools\font_grow.txt;." --add-data "tools\keep_caps.txt;." --add-data "tools\font_weight.txt;." --add-data "tools\font_scale.txt;." --add-data "tools\size_grow.txt;." --add-data "tools\ff_list.txt;." --add-data "tools\waw_original_gamefonts_pc.iwi;." --add-data "work\arabic;work_arabic" tools\user_app.py
echo.
echo Result: dist\WaW_Arabic.exe   (give players only this file)
pause
