@echo off
setlocal

:: -----------------------------------------------------------------------------
:: Dieu huong khoi chay tren Windows:
:: 1. Mac dinh chay bang Windows Terminal (wt.exe)
:: 2. Neu khong co wt.exe hoac that bai -> Fallback sang PowerShell (powershell.exe)
:: 3. Neu khong co PowerShell hoac that bai -> Fallback sang CMD (cmd.exe)
:: -----------------------------------------------------------------------------

:: Kiem tra neu da o trong Terminal hoac duoc goi boi wrapper
if defined JA_IN_TERMINAL goto launch
if /i "%~1"=="--in-terminal" goto launch
if defined WT_SESSION goto launch

:: [1] Uu tien 1: Windows Terminal (wt.exe)
where.exe wt.exe >nul 2>&1
if not errorlevel 1 (
    wt.exe -w new -d "%~dp0." cmd.exe /d /c ""%~f0" --in-terminal %*"
    if not errorlevel 1 exit /b 0
)

:: [2] Fallback 1: PowerShell (powershell.exe)
where.exe powershell.exe >nul 2>&1
if not errorlevel 1 (
    start "" powershell.exe -NoLogo -NoProfile -Command "& '%~f0' --in-terminal %*"
    if not errorlevel 1 exit /b 0
)

:: [3] Fallback 2: CMD (Chay truc tiep tai cua so cmd hien tai)
:launch
cd /d "%~dp0"
chcp 65001 >nul
title Python CLI Tool
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH="

:: Tu dong nhan dien Python Runtime:
:: Uu tien thu muc python_runtime noi bo (ban portable), neu khong co thi dung python he thong
if exist "%~dp0python_runtime\python.exe" (
    set "PY_EXE=%~dp0python_runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo Dang khoi dong Python CLI Tool...
"%PY_EXE%" -X utf8 cli_app_template.py %*

if errorlevel 1 (
    echo.
    echo [THONG BAO] Co loi xay ra trong qua trinh thuc thi.
)

echo.
pause
