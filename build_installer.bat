@echo off
setlocal
cd /d "%~dp0"
rem Builds installer\Output\FolderOrganizer-Setup-<version>.exe  (run build_exe.bat first)
if not exist "dist\Folder Organizer\Folder Organizer.exe" (
  echo Run build_exe.bat first.
  pause & exit /b 1
)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 is not installed. Get it from https://jrsoftware.org/isdl.php  ^(or: winget install JRSoftware.InnoSetup^)
  pause & exit /b 1
)
for /f "usebackq delims=" %%v in (`python -c "from version import __version__; print(__version__)"`) do set "VER=%%v"
"%ISCC%" /DAppVersion=%VER% installer\folder_organizer.iss || (echo Installer build failed. & pause & exit /b 1)
explorer "%~dp0installer\Output"
pause
