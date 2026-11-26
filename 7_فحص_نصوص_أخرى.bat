@echo off
rem Lists readable sentences that are NOT in the normal localized texts (subtitles/dialogue check). Changes nothing.
set OPEN_NOTEPAD=1
chcp 65001 >nul
cd /d "%~dp0"
python tools\cod4.py scan %*
if "%OPEN_NOTEPAD%"=="1" if exist work\other_text_report.txt start "" notepad work\other_text_report.txt
echo.
pause
