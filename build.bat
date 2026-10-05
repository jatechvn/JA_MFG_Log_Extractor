@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ===============================================================================
echo   DONG GOI BAN PHAT HANH JA_MFG_Log_Extractor v1.3.1
echo ===============================================================================

set "APP_NAME=JA_MFG_Log_Extractor"
set "APP_VERSION=1.3.1"
set "ZIP_NAME=%APP_NAME%_v%APP_VERSION%_Windows_x64.zip"
set "DIST_DIR=%~dp0dist"
set "PACK_DIR=%~dp0dist_pack\%APP_NAME%_v%APP_VERSION%_Windows_x64"

:: 1. Don dep thu muc cu
if exist "%DIST_DIR%" (
    echo [*] Lam sach thu muc dist cu...
    rmdir /s /q "%DIST_DIR%"
)
if exist "%~dp0dist_pack" (
    rmdir /s /q "%~dp0dist_pack"
)
mkdir "%DIST_DIR%"
mkdir "%PACK_DIR%"

:: 2. Sao chep tap tin cot loi vao goi
echo [*] Dang sao chep ma nguon va tai lieu...
copy /y "%~dp0extract_mfg_logs.py" "%PACK_DIR%\" >nul
copy /y "%~dp0Chay_Tool_Log.bat" "%PACK_DIR%\" >nul
copy /y "%~dp0mau_danh_sach_log.csv" "%PACK_DIR%\" >nul
copy /y "%~dp0ABOUT.txt" "%PACK_DIR%\" >nul
copy /y "%~dp0README.md" "%PACK_DIR%\" >nul
copy /y "%~dp0CHANGELOG.md" "%PACK_DIR%\" >nul
copy /y "%~dp0USERGUIDE.md" "%PACK_DIR%\" >nul
copy /y "%~dp0RELEASE_NOTES.md" "%PACK_DIR%\" >nul
copy /y "%~dp0LICENSE" "%PACK_DIR%\" >nul
copy /y "%~dp0requirements.txt" "%PACK_DIR%\" >nul

:: Sao chep python_runtime neu co san
if exist "%~dp0MFG_Log_Extractor_PythonPortable\python_runtime" (
    echo [*] Dang dong goi Python Runtime di kem...
    xcopy /e /i /y "%~dp0MFG_Log_Extractor_PythonPortable\python_runtime" "%PACK_DIR%\python_runtime" >nul
)

:: 3. Bung san ung dung truc tiep vao dist/
echo [*] Dang bung san ung dung vao dist/...
xcopy /e /i /y "%PACK_DIR%\*" "%DIST_DIR%\" >nul

:: 4. Nen thanh goi zip
echo [*] Dang tao goi zip %ZIP_NAME%...
powershell -NoProfile -Command "Compress-Archive -Path '%PACK_DIR%' -DestinationPath '%DIST_DIR%\%ZIP_NAME%' -Force"

:: 5. Tao ma bam SHA256
echo [*] Dang tao SHA256SUMS.txt...
powershell -NoProfile -Command "$hash = (Get-FileHash -Algorithm SHA256 '%DIST_DIR%\%ZIP_NAME%').Hash; \"$hash  %ZIP_NAME%\" | Out-File -FilePath '%DIST_DIR%\SHA256SUMS.txt' -Encoding utf8"

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
