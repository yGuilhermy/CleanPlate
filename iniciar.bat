@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\Clean Plate Studio\Clean Plate Studio.exe" (
  start "" "%~dp0dist\Clean Plate Studio\Clean Plate Studio.exe" %*
  exit /b
)
set "CLEANPLATE_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%CLEANPLATE_PYTHON%" (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Instale Python 3.11 ou superior: https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
  set "CLEANPLATE_PYTHON=python"
)
"%CLEANPLATE_PYTHON%" -c "import PySide6, cv2, numpy, PIL" >nul 2>&1
if errorlevel 1 (
  echo Instale as dependencias: "%CLEANPLATE_PYTHON%" -m pip install -r requirements-desktop.txt
  pause
  exit /b 1
)
"%CLEANPLATE_PYTHON%" -m cleanplate.desktop %*
if errorlevel 1 pause
