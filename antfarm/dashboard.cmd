@echo off
rem Double-click to open the antfarm dashboard in your browser. Close this window (or Ctrl+C) to stop it.
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py
%PY% dashboard.py %*
if errorlevel 1 pause
