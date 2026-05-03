#Requires -Version 5.1
<#
.SYNOPSIS
    BruV AI 開發模式啟動腳本
.DESCRIPTION
    1. 確認 Docker Desktop 已就緒
    2. docker compose up -d（含熱重載 volume）
    3. 並行等待各服務健康檢查
    4. 啟動 Electron（npm start）
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

$TOTAL_STEPS = 4

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

# ── Step 2：docker compose up ─────────────────────────────────────────────────
Write-Step 2 $TOTAL_STEPS "啟動 / 確認後端容器..."

$dcOutput = docker compose up -d --remove-orphans 2>&1
$dcExit = $LASTEXITCODE

if ($dcExit -ne 0) {
    # compose 失敗可能是 name conflict（容器由另一個 project 啟動）
    # 直接檢查關鍵容器是否已在運行，若是就繼續
    $running = docker ps --filter "name=bruv_ai_backend" --filter "status=running" -q 2>$null
    if ($running) {
        Write-Warn "docker compose 回報非零（可能 project 名稱不符），但容器已在運行，繼續..."
    } else {
        $dcOutput | ForEach-Object { Write-Info $_ }
        Write-Fail "docker compose 啟動失敗，請檢查 .env 設定與 Docker 狀態。"
        Read-Host "按 Enter 結束"
        exit 1
    }
}

Write-Ok "所有容器已啟動"

# ── Step 3：並行等待各服務健康檢查 ───────────────────────────────────────────
Write-Step 3 $TOTAL_STEPS "等待各服務就緒..."
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

# ── Step 4：啟動 Electron ─────────────────────────────────────────────────────
Write-Step 4 $TOTAL_STEPS "啟動 Electron（開發模式，熱重載後端）..."
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

# ── 結束 ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Electron 已關閉。" -ForegroundColor DarkGray
Write-Host "  容器仍在背景執行，若要停止請執行「停止.bat」。" -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Read-Host "按 Enter 關閉視窗"
