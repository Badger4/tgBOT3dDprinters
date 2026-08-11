@echo off
set "SCRIPT_DIR=%~dp0.."
python "%SCRIPT_DIR%\orca_hook.py" %1
