@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Installs ONLY the Arabic font (texts stay English). Needs the ORIGINAL code_post_gfx.ff and localized_code_post_gfx_mp.ff in work\input.
python tools\cod4.py build --ff=code_post_gfx,localized_code_post_gfx_mp --no-text
if errorlevel 1 ( pause & exit /b )
if not exist game_path.txt (
  echo Type the World at War folder path (the one that has zone\english)
  set /p GAME=Path: 
  echo %GAME%> game_path.txt
)
set /p GAME=<game_path.txt
python tools\cod4.py install "%GAME%" --ff=code_post_gfx,localized_code_post_gfx_mp
pause
