@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Copies the TEST files made by 10_تجربة_تكبير_الملف.bat into the game (originals are kept as .bak). Use 5_استرجاع_الأصلي.bat afterwards.
if not exist game_path.txt (
  echo Type the World at War folder path (the one that has zone\english)
  set /p GAME=Path: 
  echo %GAME%> game_path.txt
)
set /p GAME=<game_path.txt
python tools\cod4.py install "%GAME%" --from=growtest %*
echo.
pause
