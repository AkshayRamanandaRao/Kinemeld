@echo off
setlocal
if not exist "%~dp0native\MBDynStudio.exe" (
  echo The native desktop executable has not been built yet. See native\README.md.
  pause
  exit /b 1
)
start "" "%~dp0native\MBDynStudio.exe"
