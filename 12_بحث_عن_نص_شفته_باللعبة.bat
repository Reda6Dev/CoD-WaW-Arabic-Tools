@echo off
rem Looks for texts you SAW in the game (write them in work\seen_in_game.txt, one per line, exactly as shown) inside the game files.
set OPEN_NOTEPAD=1
chcp 65001 >nul
cd /d "%~dp0"
python tools\cod4.py find %*
if "%OPEN_NOTEPAD%"=="1" if exist work\find_report.txt start "" notepad work\find_report.txt
echo.
pause
