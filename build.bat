@echo off
setlocal

echo ========================================
echo   CHRONOS - Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller no esta instalado.
    echo Ejecuta: pip install pyinstaller
    pause
    exit /b 1
)

echo [1/3] Limpiando builds anteriores...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
if exist "Chronos.spec" del Chronos.spec

echo [2/3] Copiando spec file...
copy chronos.spec.template Chronos.spec >nul

echo [3/3] Compilando con PyInstaller...
echo (Esto puede tardar 5-10 minutos)
echo.

pyinstaller Chronos.spec --clean

if errorlevel 1 (
    echo.
    echo [ERROR] La compilacion fallo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   BUILD COMPLETADO!
echo ========================================
echo.
echo El ejecutable esta en: dist\Chronos\
echo.
echo Para crear un ZIP portable:
echo   powershell Compress-Archive -Path "dist\Chronos" -DestinationPath "Chronos-portable.zip"
echo.
pause
