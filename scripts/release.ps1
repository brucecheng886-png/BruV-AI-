# ============================================================
# release.ps1 — 發布保護腳本
# 使用方式：.\scripts\release.ps1 -Version v1.2.0
#
# 此腳本強制執行發布前檢查，通過後才允許推送 tag。
# 直接跑 git tag 跳過此腳本 = 違反發布規則。
# ============================================================

param (
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

# ── 顏色輸出工具 ─────────────────────────────────────────────
function Pass($msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red }
function Section($msg) { Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Fatal($msg) {
    Write-Host "`n❌ 發布終止：$msg" -ForegroundColor Red
    exit 1
}

Write-Host "`n=======================================" -ForegroundColor Yellow
Write-Host "  BruV AI 發布前檢查 — $Version" -ForegroundColor Yellow
Write-Host "=======================================`n" -ForegroundColor Yellow

$errors = 0

# ──────────────────────────────────────────────────────────────
# 一、版本號一致性
# ──────────────────────────────────────────────────────────────
Section "一、版本號一致性"

$electronVersion = (Get-Content "$ROOT\electron\package.json" | ConvertFrom-Json).version
$expectedVersion = $Version.TrimStart('v')

if ($electronVersion -eq $expectedVersion) {
    Pass "electron/package.json 版本號：$electronVersion ✓"
} else {
    Fail "electron/package.json 版本號：$electronVersion（期望：$expectedVersion）"
    $errors++
}

# git tag 是否已存在（不應事先建立）
$existingTag = git tag --list $Version
if ($existingTag) {
    Fail "tag $Version 已存在，請先刪除：git tag -d $Version"
    $errors++
} else {
    Pass "tag $Version 尚未建立（正確）"
}

# ──────────────────────────────────────────────────────────────
# 二、語法完整性
# ──────────────────────────────────────────────────────────────
Section "二、語法完整性"

# Electron main.js / preload.js
foreach ($jsFile in @("electron/main.js", "electron/preload.js")) {
    $result = node --check $jsFile 2>&1
    if ($LASTEXITCODE -eq 0) {
        Pass "$jsFile 語法正確"
    } else {
        Fail "$jsFile 語法錯誤：$result"
        $errors++
    }
}

# 所有本次變更的 .py 檔
$changedPy = git diff --name-only (git describe --tags --abbrev=0 HEAD^) HEAD 2>$null | Where-Object { $_ -match '\.py$' }
if ($changedPy) {
    foreach ($pyFile in $changedPy) {
        if (Test-Path $pyFile) {
            docker compose exec -T backend python -m py_compile $pyFile 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Pass "$pyFile 語法正確"
            } else {
                Fail "$pyFile py_compile 失敗"
                $errors++
            }
        }
    }
} else {
    Pass "無 Python 檔案變更"
}

# ──────────────────────────────────────────────────────────────
# 三、服務健康狀態
# ──────────────────────────────────────────────────────────────
Section "三、服務健康狀態"

try {
    $health = Invoke-RestMethod -Uri "http://localhost:80/api/health" -TimeoutSec 5 -ErrorAction Stop
    if ($health.status -eq "ok") {
        Pass "API health check: ok"
    } else {
        Fail "API health check 回傳異常：$($health | ConvertTo-Json -Compress)"
        $errors++
    }
} catch {
    Fail "API health check 失敗（服務未啟動？）：$_"
    $errors++
}

$containers = docker compose ps --format json 2>$null | ConvertFrom-Json
$notRunning = $containers | Where-Object { $_.State -ne "running" }
if ($notRunning) {
    foreach ($c in $notRunning) {
        Fail "Container 非 running：$($c.Name) = $($c.State)"
        $errors++
    }
} else {
    Pass "所有 container 狀態：running"
}

# ──────────────────────────────────────────────────────────────
# 四、.env.example 同步確認
# ──────────────────────────────────────────────────────────────
Section "四、.env.example 同步"

$changedEnvRelated = git diff --name-only (git describe --tags --abbrev=0 HEAD^) HEAD 2>$null | Where-Object { $_ -match 'config\.py|docker-compose' }
if ($changedEnvRelated) {
    Write-Host "  ⚠ 以下檔案有變更，請人工確認 .env.example 是否同步：" -ForegroundColor Yellow
    $changedEnvRelated | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
} else {
    Pass "無 config.py / docker-compose 變更，跳過"
}

# ──────────────────────────────────────────────────────────────
# 五、git 狀態
# ──────────────────────────────────────────────────────────────
Section "五、Git 狀態"

$dirty = git status --porcelain
if ($dirty) {
    Fail "工作目錄有未 commit 的變更："
    $dirty | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    $errors++
} else {
    Pass "工作目錄乾淨（無未 commit 變更）"
}

$currentBranch = git rev-parse --abbrev-ref HEAD
if ($currentBranch -eq "main") {
    Pass "目前在 main 分支"
} else {
    Fail "目前在 $currentBranch 分支，應在 main 才能發布"
    $errors++
}

# ──────────────────────────────────────────────────────────────
# 結果彙整
# ──────────────────────────────────────────────────────────────
Write-Host "`n=======================================" -ForegroundColor Yellow
if ($errors -gt 0) {
    Write-Host "  ❌ 發布前檢查失敗：$errors 項問題" -ForegroundColor Red
    Write-Host "  請修復後重新執行此腳本。" -ForegroundColor Red
    Write-Host "=======================================`n" -ForegroundColor Yellow
    exit 1
}

Write-Host "  ✅ 所有檢查通過！準備發布 $Version" -ForegroundColor Green
Write-Host "=======================================`n" -ForegroundColor Yellow

# ──────────────────────────────────────────────────────────────
# 執行發布
# ──────────────────────────────────────────────────────────────
Write-Host "正在建立 tag 並推送..." -ForegroundColor Cyan
git tag $Version
git push origin main $Version

if ($LASTEXITCODE -ne 0) {
    Fatal "git push 失敗，請檢查網路或 remote 狀態"
}

Write-Host "`n✅ tag $Version 已推送，等待 GitHub Actions 執行..." -ForegroundColor Green
Write-Host "執行以下指令確認 CI/CD 狀態（約 10-15 分鐘後）：" -ForegroundColor Yellow
Write-Host "  gh run list --repo brucecheng886-png/BruV-AI- --limit 5" -ForegroundColor White
