@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_v5_local_tests.ps1" %*
exit /b %errorlevel%
