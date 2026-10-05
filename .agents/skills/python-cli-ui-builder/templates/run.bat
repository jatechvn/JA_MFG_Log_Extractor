@echo off
setlocal

:: -----------------------------------------------------------------------------
:: Dieu huong khoi chay tren Windows:
:: - Khi chay tu CLI (CMD / PowerShell), qua Remote (WinRM / SSH), hoac co tham so:
::   -> Chay truc tiep tai console hien tai, KHONG bat cua so moi.
:: - Khi nguoi dung Double-click file .bat tu Windows Explorer:
::   1. Uu tien khoi chay trong Windows Terminal (wt.exe) neu may co cai dat.
::   2. Fallback: Chay truc tiep tren cua so CMD do Explorer mo ra.
:: -----------------------------------------------------------------------------

:: [1] Da o trong Terminal wrapper hoac bien danh dau
if defined JA_IN_TERMINAL goto launch
if /i "%~1"=="--in-terminal" goto launch
if defined WT_SESSION goto launch

:: [2] Co tham so truyen vao tu dong lenh (CLI args) -> Chay truc tiep tai console hien tai
if not "%~1"=="" goto launch

:: [3] Phien lam viec tu xa hoac non-interactive (SSH, WinRM) -> Chay truc tiep tai console hien tai
if defined SSH_CLIENT goto launch
if defined SSH_CONNECTION goto launch
if defined SSH_TTY goto launch
if not defined SESSIONNAME goto launch

:: [4] Kiem tra co phai double-click tu Windows Explorer khong
:: Khi double-click tu Explorer, Windows luon truyen: cmd /c ""duong_dan_file.bat" "
echo %cmdcmdline% | findstr /i /c:"/c \"\"" >nul
if errorlevel 1 goto launch

:: [5] Nguoi dung Double-click tu Explorer: Uu tien Windows Terminal (wt.exe) neu co
where.exe wt.exe >nul 2>&1
if errorlevel 1 goto launch
wt.exe -w new -d "%~dp0" cmd.exe /d /c "\"%~f0\" --in-terminal %*"
if not errorlevel 1 exit /b 0

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
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% neq 0 (
    echo.
    echo [THONG BAO] Co loi xay ra trong qua trinh thuc thi [Exit Code: %EXIT_CODE%].
)

:: Chi pause khi double-click tu Windows Explorer (interactive desktop va khong co tham so truyen vao)
:: Tranh treo script khi chay tu WinRM, SSH, headless, hoac batch automation
if not "%~1"=="" goto finish
if not defined SESSIONNAME goto finish
echo.
pause

:finish
exit /b %EXIT_CODE%
