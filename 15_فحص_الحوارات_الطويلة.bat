@echo off
rem OPEN_NOTEPAD=1: opens the result in Notepad (Arabic shows correctly there, not in this black window). Set to 0 to disable.
set OPEN_NOTEPAD=1
chcp 65001 >nul
cd /d "%~dp0"
python tools\cod4.py longsubs %*
if "%OPEN_NOTEPAD%"=="1" if exist work\last_output.txt start "" notepad work\last_output.txt
echo.
pause
