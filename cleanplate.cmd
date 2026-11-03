@echo off
setlocal
if exist "%~dp0dist\CleanPlateControl\CleanPlateControl.exe" (
  "%~dp0dist\CleanPlateControl\CleanPlateControl.exe" %*
) else (
  if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0tools\control_entry.py" %*
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo Instale Python 3.11 ou superior: https://www.python.org/downloads/windows/ 1>&2
      exit /b 1
    )
    python "%~dp0tools\control_entry.py" %*
  )
)
exit /b %errorlevel%
