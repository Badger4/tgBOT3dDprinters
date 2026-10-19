@echo off
set "SCRIPT_DIR=%~dp0.."
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%\.venv\Scripts\python.exe" "%~dp0orca_hook.py" %1
) else (
    python "%~dp0orca_hook.py" %1
)
