@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  Build Folder Organizer.exe  (one time, about 1-2 minutes)
echo ============================================================
where python >nul 2>nul || (
  echo Python is not installed. Download it from https://www.python.org/downloads/
  pause & exit /b 1
)
echo [1/3] Installing build tools...
python -m pip install --quiet -r requirements.lock || goto :fail

echo [2/3] Building...
python -m PyInstaller --noconfirm --clean folder_organizer.spec || goto :fail

echo [3/3] Copying your rules...
if exist "rules.yaml" if not exist "dist\Folder Organizer\rules.yaml" copy /y "rules.yaml" "dist\Folder Organizer\rules.yaml" >nul

echo.
echo Done:  %~dp0dist\Folder Organizer\Folder Organizer.exe
echo Move the whole "Folder Organizer" folder anywhere you like (e.g. C:\Apps), then pin the .exe to the taskbar.
explorer "%~dp0dist\Folder Organizer"
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error message.
pause
exit /b 1
