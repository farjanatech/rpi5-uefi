@echo off
setlocal
cd /d "%~dp0"
echo Raspberry Pi 5 Fan Control exp.6 installer
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-RPi5FanSuite.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="194" (
  echo Windows test-signing was enabled. Reboot, then run Install.cmd again.
) else if not "%RC%"=="0" (
  echo Installation failed with exit code %RC%.
  echo Check RPi5Fan-exp6-install.log on the Desktop.
)
pause
exit /b %RC%
