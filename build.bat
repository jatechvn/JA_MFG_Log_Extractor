@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ===============================================================================
echo   DONG GOI BAN PHAT HANH JA_MFG_Log_Extractor v1.6.0
echo ===============================================================================

set "APP_NAME=JA_MFG_Log_Extractor"
set "APP_VERSION=1.6.0"
set "ZIP_NAME=%APP_NAME%_v%APP_VERSION%_Windows_x64.zip"
set "DIST_DIR=%~dp0dist"
set "PACK_DIR=%~dp0dist_pack\%APP_NAME%_v%APP_VERSION%_Windows_x64"

:: 1. Khoi tao thu muc dong goi tam & bao toan python_runtime tu dist/
if exist "%~dp0dist_pack" (
    rmdir /s /q "%~dp0dist_pack"
)
mkdir "%PACK_DIR%"
mkdir "%PACK_DIR%\reports"

if exist "%~dp0python_runtime" (
    echo [*] Dang dong goi Python Runtime tu thu muc goc...
    xcopy /e /i /y "%~dp0python_runtime" "%PACK_DIR%\python_runtime" >nul
) else if exist "%DIST_DIR%\python_runtime" (
    echo [*] Dang bao toan va dong goi Python Runtime tu dist\python_runtime...
    move /y "%DIST_DIR%\python_runtime" "%PACK_DIR%\python_runtime" >nul
)

if exist "%DIST_DIR%" (
    echo [*] Lam sach thu muc dist cu...
    rmdir /s /q "%DIST_DIR%"
)
mkdir "%DIST_DIR%"

:: 2. Sao chep tap tin cot loi vao goi
echo [*] Dang sao chep ma nguon, module va tai lieu...
copy /y "%~dp0extract_mfg_logs.py" "%PACK_DIR%\" >nul
copy /y "%~dp0Chay_Tool_Log.bat" "%PACK_DIR%\" >nul
copy /y "%~dp0config_sample.json" "%PACK_DIR%\" >nul
copy /y "%~dp0mau_danh_sach_log.csv" "%PACK_DIR%\" >nul
copy /y "%~dp0ABOUT.txt" "%PACK_DIR%\" >nul
copy /y "%~dp0README.md" "%PACK_DIR%\" >nul
copy /y "%~dp0CHANGELOG.md" "%PACK_DIR%\" >nul
copy /y "%~dp0USERGUIDE.md" "%PACK_DIR%\" >nul
copy /y "%~dp0RELEASE_NOTES.md" "%PACK_DIR%\" >nul
copy /y "%~dp0LICENSE" "%PACK_DIR%\" >nul
copy /y "%~dp0requirements.txt" "%PACK_DIR%\" >nul

:: Sao chep thu muc module/ (loai bo __pycache__)
mkdir "%PACK_DIR%\module"
copy /y "%~dp0module\*.py" "%PACK_DIR%\module\" >nul
copy /y "%~dp0module\*.ps1" "%PACK_DIR%\module\" >nul

:: 3. Bung san ung dung truc tiep vao dist/
echo [*] Dang bung san ung dung vao dist/...
xcopy /e /i /y "%PACK_DIR%\*" "%DIST_DIR%\" >nul

:: 4. Nen thanh goi zip
echo [*] Dang tao goi zip %ZIP_NAME%...
powershell -NoProfile -Command "Compress-Archive -Path '%PACK_DIR%' -DestinationPath '%DIST_DIR%\%ZIP_NAME%' -Force"

:: 5. Tao ma bam SHA256 va version.json manifest
echo [*] Dang tao SHA256SUMS.txt va version.json...
powershell -NoProfile -Command "$hash = (Get-FileHash -Algorithm SHA256 '%DIST_DIR%\%ZIP_NAME%').Hash.ToLower(); \"$hash  %ZIP_NAME%\" | Out-File -FilePath '%DIST_DIR%\SHA256SUMS.txt' -Encoding utf8; $notes = [IO.File]::ReadAllText('%~dp0RELEASE_NOTES.md', [System.Text.Encoding]::UTF8); $manifest = [ordered]@{ version = '%APP_VERSION%'; fileName = '%ZIP_NAME%'; sha256 = $hash; releaseDate = (Get-Date -Format 'yyyy-MM-dd'); releaseNotes = $notes }; $manifest | ConvertTo-Json -Depth 4 | Set-Content -Path '%DIST_DIR%\version.json' -Encoding UTF8"

:: 6. Don dep thu muc tam
if exist "%~dp0dist_pack" (
    rmdir /s /q "%~dp0dist_pack"
)

echo.
echo ===============================================================================
echo   DONG GOI THANH CONG!
echo   Thu muc phat hanh: %DIST_DIR%
echo   Goi zip: %DIST_DIR%\%ZIP_NAME%
echo ===============================================================================
