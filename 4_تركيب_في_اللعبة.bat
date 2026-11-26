@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist game_path.txt (
  echo Type the World at War folder path (the one that has zone\english)
  set /p GAME=Path: 
  echo %GAME%> game_path.txt
)
set /p GAME=<game_path.txt
python tools\cod4.py install "%GAME%" %*
echo.
echo (If the path is wrong, delete game_path.txt and run again)
pause
