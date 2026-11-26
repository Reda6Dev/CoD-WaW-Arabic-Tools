@echo off
rem Finds subtitle/text keys that the game data uses but no extracted text defines (missing subtitles). Changes nothing.
set OPEN_NOTEPAD=1
chcp 65001 >nul
cd /d "%~dp0"
python tools\cod4.py keys %*
if "%OPEN_NOTEPAD%"=="1" if exist work\missing_keys_report.txt start "" notepad work\missing_keys_report.txt
echo.
pause
