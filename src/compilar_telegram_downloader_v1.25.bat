@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=..\.venv311\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --noconsole ^
 --name "TelegramDownloader_v1.25" --icon "imagenes\icono.ico" ^
 --add-data "imagenes;imagenes" --collect-all pyrogram --hidden-import tgcrypto auto.py
if errorlevel 1 exit /b 1
echo Ejecutable generado: dist\TelegramDownloader_v1.25.exe
