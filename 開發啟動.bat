@echo off
chcp 65001 >nul
title BruV AI 開發模式啟動
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo  +==========================================+
echo  ^|      BruV AI 開發模式  --  啟動中        ^|
echo  +==========================================+
echo.

:: ===== Step 1: 檢查 Docker Desktop =====
echo [1/4] 檢查 Docker Desktop...
docker info >nul 2>&1
if %errorlevel% equ 0 goto docker_ready

echo       Docker 尚未啟動，正在嘗試啟動 Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
echo       等待 Docker daemon 就緒（最多 60 秒）...

set /a count=0
:wait_docker
timeout /t 2 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% equ 0 goto docker_ready
set /a count+=1
if !count! lss 30 goto wait_docker

echo [錯誤] Docker daemon 啟動逾時，請手動啟動 Docker Desktop 後重試。
pause
exit /b 1

:docker_ready
echo       Docker 已就緒。

:: ===== Step 2: 啟動容器 =====
echo [2/4] 啟動 / 確認後端容器（docker compose up -d）...
docker compose up -d --remove-orphans
if %errorlevel% neq 0 (
    echo [錯誤] docker compose 啟動失敗，請檢查 .env 設定與 Docker 狀態。
    pause
    exit /b 1
)
echo       容器已就緒。

:: ===== Step 3: 等待後端 health =====
echo [3/4] 等待後端 API 就緒（http://localhost:8000/api/health）...

set /a count=0
:wait_backend
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto backend_ready
set /a count+=1
if !count! geq 60 goto backend_skip
timeout /t 1 /nobreak >nul
goto wait_backend

:backend_skip
echo [警告] 後端 60 秒內未回應健康檢查，仍然啟動 Electron（可能仍在初始化）。
goto launch_electron

:backend_ready
echo       後端 API 已就緒。

:launch_electron
:: ===== Step 4: 啟動 Electron =====
echo [4/4] 啟動 Electron（讀取最新原始碼）...
pushd electron
call npm start
popd

echo.
echo  Electron 已關閉。容器仍在背景執行。
echo  若要停止容器，請執行「停止.bat」。
echo.
pause
endlocal
