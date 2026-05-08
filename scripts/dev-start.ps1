#Requires -Version 5.1
<#
.SYNOPSIS
    BruV AI 開發模式啟動腳本
.DESCRIPTION
    1. 確認 Docker Desktop 已就緒
    2. (選項) Build 前端 → docker compose restart nginx
    3. docker compose up -d
    4. 等待各服務健康檢查
    5. 啟動 Electron
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

# ── 工作目錄 ──────────────────────────────────────────────────────────────────
$ROOT = Split-Path $PSScriptRoot -Parent
Set-Location $ROOT

# ── 顏色工具 ──────────────────────────────────────────────────────────────────
function Write-Step   { param($n,$total,$msg) Write-Host "  " -NoNewline; Write-Host "[$n/$total]" -ForegroundColor Cyan -NoNewline; Write-Host " $msg" }
function Write-Ok     { param($msg) Write-Host "       " -NoNewline; Write-Host "✓ " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Write-Warn   { param($msg) Write-Host "       " -NoNewline; Write-Host "⚠ " -ForegroundColor Yellow -NoNewline; Write-Host $msg }
function Write-Fail   { param($msg) Write-Host "       " -NoNewline; Write-Host "✗ " -ForegroundColor Red -NoNewline; Write-Host $msg }
function Write-Info   { param($msg) Write-Host "         $msg" -ForegroundColor DarkGray }

# ── Banner ────────────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor DarkMagenta
Write-Host "  ║                                          ║" -ForegroundColor DarkMagenta
Write-Host "  ║   " -ForegroundColor DarkMagenta -NoNewline
Write-Host "BruV AI" -ForegroundColor White -NoNewline
Write-Host "  開發模式啟動              ║" -ForegroundColor DarkMagenta
Write-Host "  ║                                          ║" -ForegroundColor DarkMagenta
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor DarkMagenta
Write-Host ""

$TOTAL_STEPS = 5

# ── Step 1：Docker Desktop ────────────────────────────────────────────────────
Write-Step 1 $TOTAL_STEPS "檢查 Docker Desktop..."

$dockerReady = $false
try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $dockerReady = $true }
} catch {}

if (-not $dockerReady) {
    Write-Warn "Docker 尚未啟動，正在啟動 Docker Desktop..."
    $dockerExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
    } else {
        Write-Fail "找不到 Docker Desktop，請手動啟動後重試。"
        Read-Host "按 Enter 結束"
        exit 1
    }

    Write-Info "等待 Docker daemon 就緒（最多 90 秒）..."
    $waited = 0
    while ($waited -lt 90) {
        Start-Sleep 3
        $waited += 3
        try {
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break }
        } catch {}
        Write-Host "." -NoNewline -ForegroundColor DarkGray
    }
    Write-Host ""
}

if (-not $dockerReady) {
    Write-Fail "Docker daemon 啟動逾時（90s），請手動啟動後重試。"
    Read-Host "按 Enter 結束"
    exit 1
}

Write-Ok "Docker 已就緒"

# ── Step 2：前端 Build（詢問）────────────────────────────────────────────────
Write-Step 2 $TOTAL_STEPS "前端 Build..."
Write-Host ""
Write-Host "  是否重新 Build 前端？（前端有改動請選 Y）" -ForegroundColor White
Write-Host "  [Y] 是    [Enter] 跳過（預設）" -ForegroundColor DarkGray
Write-Host ""
$buildChoice = Read-Host "  選擇"

if ($buildChoice -match '^[Yy]$') {
    Write-Info "使用 Docker (node:20-alpine) build，請稍候..."
    docker run --rm -v "${ROOT}/frontend:/app" -w /app node:20-alpine `
        sh -c "npm install --silent && npm run build 2>&1 | tail -3"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "前端 Build 失敗，請檢查錯誤訊息。"
        Read-Host "按 Enter 結束"
        exit 1
    }
    Write-Ok "前端 Build 完成"
} else {
    Write-Info "跳過 Build，使用現有 dist"
}

# ── Step 3：docker compose up ─────────────────────────────────────────────────
Write-Step 3 $TOTAL_STEPS "啟動 / 確認後端容器..."

$dcOutput = docker compose up -d --remove-orphans 2>&1
$dcExit = $LASTEXITCODE

if ($dcExit -ne 0) {
    # 判斷是否為 name conflict（容器已存在但屬於其他 project）
    $isConflict = $dcOutput | Where-Object { $_ -like '*already in use*' }
    if ($isConflict) {
        Write-Warn "容器已存在（project 名稱不符），嘗試直接啟動..."
        $allContainers = @(
            'bruv_ai_postgres','bruv_ai_redis','bruv_ai_qdrant','bruv_ai_minio',
            'bruv_ai_ollama','bruv_ai_neo4j','bruv_ai_backend','bruv_ai_celery','bruv_ai_playwright'
        )
        docker start @allContainers 2>&1 | Out-Null
        Start-Sleep 2
        $running = docker ps --filter "name=bruv_ai_backend" --filter "status=running" -q 2>$null
        if ($running) {
            Write-Ok "容器已啟動"
        } else {
            Write-Fail "container 啟動失敗，請手動檢查。"
            Read-Host "按 Enter 結束"
            exit 1
        }
    } else {
        $dcOutput | ForEach-Object { Write-Info $_ }
        Write-Fail "docker compose 啟動失敗，請檢查 .env 設定與 Docker 狀態。"
        Read-Host "按 Enter 結束"
        exit 1
    }
}

# 若 build 了前端，重啟 nginx 確保 volume 內容最新（override.yml 已掛載 ./frontend/dist）
if ($buildChoice -match '^[Yy]$') {
    Write-Info "重啟 nginx 套用新 bundle..."
    docker compose restart nginx 2>&1 | Out-Null
    Write-Ok "nginx 已更新"
}

Write-Ok "所有容器已啟動"

# ── Step 4：並行等待各服務健康檢查 ───────────────────────────────────────────
Write-Step 4 $TOTAL_STEPS "等待各服務就緒..."
Write-Host ""

$checks = @(
    @{ Name = "Backend API  "; Url  = "http://localhost:8000/api/health"; Timeout = 120 }
    @{ Name = "PostgreSQL   "; Port = 5432;                               Timeout = 60  }
    @{ Name = "Qdrant       "; Url  = "http://localhost:6333/healthz";    Timeout = 60  }
    @{ Name = "Redis        "; Port = 6379;                               Timeout = 60  }
)

function Wait-Service {
    param($check)
    $name    = $check.Name
    $timeout = $check.Timeout
    $elapsed = 0

    while ($elapsed -lt $timeout) {
        $ok = $false
        try {
            if ($check.ContainsKey('Url')) {
                $r = Invoke-WebRequest -Uri $check.Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                $ok = ($r.StatusCode -lt 400)
            } elseif ($check.ContainsKey('Port')) {
                $tcp = New-Object System.Net.Sockets.TcpClient
                $result = $tcp.BeginConnect('127.0.0.1', $check.Port, $null, $null)
                $ok = $result.AsyncWaitHandle.WaitOne(1000, $false)
                $tcp.Close()
            }
        } catch {}

        if ($ok) {
            Write-Host "         " -NoNewline
            Write-Host "✓ " -ForegroundColor Green -NoNewline
            Write-Host "$name " -NoNewline
            Write-Host "就緒" -ForegroundColor Green
            return $true
        }

        Start-Sleep 2
        $elapsed += 2
    }

    Write-Host "         " -NoNewline
    Write-Host "⚠ " -ForegroundColor Yellow -NoNewline
    Write-Host "$name " -NoNewline
    Write-Host "${timeout}s 內未回應（仍會繼續啟動）" -ForegroundColor Yellow
    return $false
}

# 依序等待（並行在 PS 5.1 需要 Job，這樣更清晰）
foreach ($check in $checks) {
    Wait-Service $check | Out-Null
}

Write-Host ""

# ── Step 5：啟動 Electron ─────────────────────────────────────────────────────
Write-Step 5 $TOTAL_STEPS "啟動 Electron..."
Write-Host ""

$electronPath = Join-Path $ROOT "electron"
Set-Location $electronPath

try {
    # npm start 會阻塞直到 Electron 關閉
    & npm start
} catch {
    Write-Fail "Electron 啟動失敗：$_"
}

Set-Location $ROOT

# ── 結束（自動關閉）───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Electron 已關閉。容器仍在背景運行。" -ForegroundColor DarkGray
Write-Host ""
