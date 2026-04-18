@echo off
chcp 65001 >nul
title BruV AI 知識庫 — 啟動中...

:: ─── 確認工作目錄為專案根目錄 ─────────────────────────────────────────────
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║        BruV AI 知識庫  —  啟動中         ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ─── Step 1: 啟動 Docker 後端服務 ─────────────────────────────────────────
echo [1/3] 啟動後端服務 (Docker Compose)...
docker compose up -d
if %errorlevel% neq 0 (
    echo.
    echo [錯誤] Docker Compose 啟動失敗。
    echo        請確認 Docker Desktop 已開啟，然後重試。
    pause
    exit /b 1
)
echo       後端服務已送出啟動指令。

:: ─── Step 2: 等待 nginx/後端 health check ─────────────────────────────────
echo [2/3] 等待後端就緒 (最多 90 秒)...
set /a count=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:80/api/health 2>nul | findstr "200" >nul
if %errorlevel% == 0 goto BACKEND_OK
set /a count+=1
if %count% geq 45 goto BACKEND_TIMEOUT
set /a secs=%count%*2
echo       已等待 %secs% 秒...
goto WAIT_LOOP

:BACKEND_TIMEOUT
echo.
echo [警告] 後端超時，嘗試直接開啟 Electron (Splash 畫面會繼續等待)。
goto LAUNCH_ELECTRON

:BACKEND_OK
echo       後端已就緒！

:: ─── Step 3: 啟動 Electron ────────────────────────────────────────────────
:LAUNCH_ELECTRON
echo [3/3] 啟動桌面程式 (Electron)...
cd /d "%~dp0electron"
start "" cmd /c "npm start"
cd /d "%~dp0"

echo.
echo  ✓ BruV AI 知識庫已啟動。
echo    網頁版：http://localhost:80
echo    桌面版：Electron 視窗
echo.
timeout /t 3 /nobreak >nul
exit /b 0
