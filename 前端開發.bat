@echo off
chcp 65001 >nul
title BruV AI 前端開發 — 編譯中

cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   BruV AI 前端開發  —  編譯與熱載入     ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ── Step 1: 確認 docker-compose.override.yml 存在（dev volume mount） ──
if not exist "docker-compose.override.yml" (
    echo [警告] 找不到 docker-compose.override.yml，前端熱載入無法生效。
    echo        請確認此檔案存在，否則 nginx 容器仍會使用 build 進去的舊版前端。
    pause
    exit /b 1
)

:: ── Step 2: 編譯前端 ──
echo [1/3] 編譯前端 (cd frontend ^&^& npm run build)...
pushd frontend
call npm run build
if %errorlevel% neq 0 (
    echo [錯誤] 前端編譯失敗。
    popd
    pause
    exit /b 1
)
popd
echo       前端編譯完成。

:: ── Step 3: 確認 nginx 容器已啟動，套用 override 並重載 ──
echo [2/3] 套用 docker-compose.override.yml 並重啟 nginx...
docker compose up -d nginx
if %errorlevel% neq 0 (
    echo [錯誤] nginx 啟動 / 重載失敗。
    pause
    exit /b 1
)

echo [3/3] 重新載入 nginx 設定...
docker compose restart nginx >nul 2>&1

echo.
echo  ✅ 前端已更新！直接重整 BruV AI 視窗（按 F5）即可看到最新改動。
echo.
pause
