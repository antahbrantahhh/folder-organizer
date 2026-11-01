@echo off
chcp 65001 >nul
setlocal
set "SCRIPT=%~dp0organizer.py"

where python >nul 2>nul || (
  echo Python is not installed. Download it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
  pause & exit /b 1
)
python -c "import yaml, PIL" 2>nul || python -m pip install --quiet -r "%~dp0requirements.txt"

set "TARGET=%~1"
if "%TARGET%"=="" set /p "TARGET=Folder to organize (drag a folder here, then press Enter): "
set "TARGET=%TARGET:"=%"

:menu
echo.
echo ===== Folder Organizer =====
echo  Target: %TARGET%
echo  1. Scan      (audit only, nothing changes)
echo  2. Plan      (preview / dry run)
echo  3. Apply     (organize by rules)
echo  4. Find duplicates (dry run)
echo  5. Move duplicates to _to_delete
echo  6. Undo last batch
echo  7. Watch     (auto-organize new files)
echo  8. Apply folder labels
echo  9. Remove folder labels
echo  0. Exit
echo  Language follows the app setting. Add --lang id or --lang en when running organizer.py directly.
set /p "C=Choose: "
if "%C%"=="1" python "%SCRIPT%" scan "%TARGET%"
if "%C%"=="2" python "%SCRIPT%" plan "%TARGET%"
if "%C%"=="3" python "%SCRIPT%" apply "%TARGET%"
if "%C%"=="4" python "%SCRIPT%" dedupe "%TARGET%"
if "%C%"=="5" python "%SCRIPT%" dedupe "%TARGET%" --apply
if "%C%"=="6" python "%SCRIPT%" undo "%TARGET%"
if "%C%"=="7" python "%SCRIPT%" watch "%TARGET%"
if "%C%"=="8" python "%SCRIPT%" label "%TARGET%"
if "%C%"=="9" python "%SCRIPT%" label "%TARGET%" --remove
if "%C%"=="0" exit /b 0
goto menu
