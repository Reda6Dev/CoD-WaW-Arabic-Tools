@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist game_path.txt ( echo Run 4_تركيب_في_اللعبة.bat first. & pause & exit /b )
set /p GAME=<game_path.txt
python tools\cod4.py restore "%GAME%" %*
pause
