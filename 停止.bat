@echo off
chcp 65001 >nul
title BruV AI 知識庫 — 停止中...

cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║        BruV AI 知識庫  —  停止中         ║
echo  ╚══════════════════════════════════════════╝
echo.

:: 關閉 Electron
echo [1/2] 關閉 Electron 視窗...
taskkill /F /IM electron.exe >nul 2>&1
echo       完成。

:: 停止 Docker 後端（保留容器與 volume）
echo [2/2] 停止後端服務 (Docker Compose stop，不刪除容器)...
docker compose stop
if %errorlevel% neq 0 (
    echo [錯誤] Docker Compose 停止失敗。
    pause
    exit /b 1
)
echo       完成。

echo.
echo  ✓ 所有服務已停止。
pause
