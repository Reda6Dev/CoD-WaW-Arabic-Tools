@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Makes TEST copies (English texts made longer, so the file must grow) of ALL .ff files in work\input, or only the ones you name.
rem Then run 11_تركيب_ملفات_التجربة.bat to put them in the game, and 5_استرجاع_الأصلي.bat to go back.
python tools\cod4.py growtest %*
echo.
pause
