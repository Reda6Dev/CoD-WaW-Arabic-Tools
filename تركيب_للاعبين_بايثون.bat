@echo off
cd /d "%~dp0"
rem Needs Python 3 + "pip install pillow numpy". For users WITHOUT Python use CoD4_Arabic.exe (see بناء_ملف_exe.bat).
python tools\user_app.py %*
