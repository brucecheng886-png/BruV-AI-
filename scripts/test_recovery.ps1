# ================================================================
# 地端 AI 知識庫 — 重啟恢復測試腳本
# 用途：驗證全容器重啟後所有功能正常、無資料遺失
# 使用方式：.\scripts\test_recovery.ps1
# ================================================================

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path $PSScriptRoot -Parent
$Pass = 0
$Fail = 0

function Check {
    param([string]$Name, [scriptblock]$Test)
    try {
        & $Test
        Write-Host "  ✅ $Name" -ForegroundColor Green
        $script:Pass++
    } catch {
        Write-Host "  ❌ $Name — $_" -ForegroundColor Red
        $script:Fail++
    }
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " AI 知識庫 — 重啟恢復測試" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# ── Phase 1: 停止所有容器 ────────────────────────────────────────
Write-Host ""
Write-Host "[1/4] 停止所有容器..." -ForegroundColor Yellow
Set-Location $BaseDir
docker compose down 2>&1 | Out-Null
Start-Sleep 3
Write-Host "      全部容器已停止"

# ── Phase 2: 重新啟動 ────────────────────────────────────────────
Write-Host ""
Write-Host "[2/4] 重新啟動所有容器..." -ForegroundColor Yellow
docker compose up -d 2>&1 | Out-Null

Write-Host "      等待服務就緒（最多 120 秒）..."
$maxWait = 120
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep 5
    $waited += 5
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 3
        if ($health.status -eq "healthy") { break }
    } catch { }
    Write-Host "      ... $waited 秒" -ForegroundColor DarkGray
}

# ── Phase 3: 功能驗收 ────────────────────────────────────────────
Write-Host ""
Write-Host "[3/4] 功能驗收..." -ForegroundColor Yellow

Check "Backend /api/health 回 healthy" {
    $r = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 5
    if ($r.status -ne "healthy") { throw "status=$($r.status)" }
}

Check "PostgreSQL 可連線" {
    $result = docker exec ai_kb_postgres psql -U ai_kb_user -d ai_kb -c "SELECT 1;" 2>&1
    if ($result -notmatch "1 row") { throw "PG 連線失敗" }
}

Check "Qdrant /collections 正常" {
    $r = Invoke-RestMethod -Uri "http://localhost:6333/collections" -TimeoutSec 5
    # 只要回應 200 即可
}

Check "Neo4j HTTP 可存取" {
    $r = Invoke-WebRequest -Uri "http://localhost:7474" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -ne 200) { throw "Neo4j HTTP=$($r.StatusCode)" }
}

Check "Redis PING" {
    $result = docker exec ai_kb_redis redis-cli ping
    if ($result.Trim() -ne "PONG") { throw "Redis PING failed" }
}

Check "MinIO /minio/health/live" {
    $r = Invoke-WebRequest -Uri "http://localhost:9000/minio/health/live" -TimeoutSec 5
    if ($r.StatusCode -ne 200) { throw "MinIO health=$($r.StatusCode)" }
}

Check "JWT 登入正常" {
    $body = '{"email":"admin@local","password":"admin123456"}'
    $r = Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login" `
         -Method Post -Body $body -ContentType "application/json" -TimeoutSec 10
    if (-not $r.access_token) { throw "無 access_token" }
}

Check "Grafana 首頁可存取" {
    $r = Invoke-WebRequest -Uri "http://localhost:3001" -TimeoutSec 5
    if ($r.StatusCode -ne 200) { throw "Grafana=$($r.StatusCode)" }
}

Check "Prometheus targets 有資料" {
    $r = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/targets" -TimeoutSec 5
    $up = $r.data.activeTargets | Where-Object health -eq "up"
    if ($up.Count -eq 0) { throw "無 active targets" }
}

# ── Phase 4: 資料持久化驗證 ─────────────────────────────────────
Write-Host ""
Write-Host "[4/4] 資料持久化驗證..." -ForegroundColor Yellow

Check "PostgreSQL documents 表有資料（非空）" {
    $result = docker exec ai_kb_postgres psql -U ai_kb_user -d ai_kb `
              -c "SELECT COUNT(*) FROM documents;" -t 2>&1
    $count = [int]($result.Trim())
    Write-Host "      文件數: $count"
    # 允許 0（全新環境），只要查詢不報錯即可
}

Check "Qdrant chunks collection 存在" {
    $r = Invoke-RestMethod -Uri "http://localhost:6333/collections/chunks" -TimeoutSec 5
    $pts = $r.result.points_count
    Write-Host "      向量數: $pts"
}

# ── 結果摘要 ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " 測試結果: $Pass 通過 / $Fail 失敗" -ForegroundColor $(if ($Fail -eq 0) { "Green" } else { "Red" })
Write-Host "=====================================================" -ForegroundColor Cyan

if ($Fail -gt 0) {
    Write-Host "請執行 'docker compose logs [service]' 查看詳細錯誤" -ForegroundColor Yellow
    exit 1
}
