@echo off
set "SCRIPT_DIR=%~dp0.."
if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%\.venv\Scripts\python.exe" "%SCRIPT_DIR%\orca_hook.py" %1
) else (
    python "%SCRIPT_DIR%\orca_hook.py" %1
)
