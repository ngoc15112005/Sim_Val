@echo off
chcp 65001 >nul
title Sim_Val - VCT Tournament Simulator
cd /d "%~dp0"

echo ===================================================================
echo     CHƯƠNG TRÌNH MÔ PHỎNG GIẢI ĐẤU VALORANT (CHẠY LOCAL 100%%)
echo ===================================================================
echo.

rem Kiem tra file database local
if not exist "instance\val.db" (
    echo [LOI] Khong tim thay file du lieu instance\val.db!
    pause
    exit /b 1
)

echo [OK] Du lieu: instance\val.db da san sang (285 MB, 1175 chien dich).
echo.

rem Dam bao bo qua moi ket noi cloud (Neon / Turso) de chi chay 100% tren SQLite may ban
set DATABASE_URL=
set TURSO_DATABASE_URL=
set TURSO_AUTH_TOKEN=

echo Dang khoi dong Web Server tai http://127.0.0.1:5000 ...
start "" http://127.0.0.1:5000

echo.
echo [Luu y] De tat web app, chi can dong cua so den nay lai (hoac an Ctrl + C).
echo.
.venv\Scripts\python.exe app.py
pause
