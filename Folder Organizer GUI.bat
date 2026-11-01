@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python is not installed. Download it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^)
  pause & exit /b 1
)
python -c "import yaml, sv_ttk, PIL, ruamel.yaml" 2>nul || (
  echo Installing dependencies, one time only...
  python -m pip install --quiet -r "%~dp0requirements.txt"
)
start "" pythonw "%~dp0organizer_gui.pyw"
