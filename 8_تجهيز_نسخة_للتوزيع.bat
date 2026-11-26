@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem For the translator: makes work\release\cod4_arabic_translation.zip (tools + your translations, without game files)
python tools\cod4.py release
echo.
pause
