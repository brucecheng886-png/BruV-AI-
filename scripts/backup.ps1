# ================================================================
# 地端 AI 知識庫 — 備份腳本
# 用途：定期備份 PostgreSQL、Qdrant snapshot、Neo4j 至本機目錄
#       備份完後上傳至 MinIO
# 使用方式：
#   .\scripts\backup.ps1
#   或透過 Windows 工作排程器每日執行
# ================================================================

param(
    [string]$BackupRoot = "C:\ai_kb_backups",
    [string]$Retention  = 7   # 保留天數
)

$ErrorActionPreference = "Stop"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $BackupRoot $Timestamp

Write-Host "=== AI 知識庫備份開始 === $Timestamp" -ForegroundColor Cyan
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

# ── 1. PostgreSQL pg_dump ────────────────────────────────────────
Write-Host "[1/4] PostgreSQL 備份..." -ForegroundColor Yellow
$PgFile = Join-Path $BackupDir "postgres_$Timestamp.sql.gz"
try {
    docker exec ai_kb_postgres sh -c `
        "pg_dump -U `$POSTGRES_USER `$POSTGRES_DB | gzip" | `
        Set-Content -AsByteStream $PgFile
    Write-Host "      ✅ PG 備份完成: $PgFile"
} catch {
    Write-Warning "      ❌ PG 備份失敗: $_"
}

# ── 2. Qdrant Snapshot ───────────────────────────────────────────
Write-Host "[2/4] Qdrant Snapshot 備份..." -ForegroundColor Yellow
$QdrantSnapshotDir = Join-Path $BackupDir "qdrant_snapshots"
New-Item -ItemType Directory -Path $QdrantSnapshotDir -Force | Out-Null
try {
    # 取得所有 collections
    $collections = (Invoke-RestMethod -Uri "http://localhost:6333/collections").result.collections
    foreach ($col in $collections) {
        $name = $col.name
        # 建立 snapshot
        $snap = Invoke-RestMethod -Uri "http://localhost:6333/collections/$name/snapshots" -Method Post
        $snapName = $snap.result.name
        # 下載 snapshot
        $dest = Join-Path $QdrantSnapshotDir "$name-$snapName"
        Invoke-WebRequest -Uri "http://localhost:6333/collections/$name/snapshots/$snapName" `
                          -OutFile $dest
        Write-Host "      ✅ Qdrant $name 備份完成"
    }
} catch {
    Write-Warning "      ❌ Qdrant 備份失敗: $_"
}

# ── 3. Neo4j Dump ────────────────────────────────────────────────
Write-Host "[3/4] Neo4j 資料庫備份..." -ForegroundColor Yellow
$Neo4jFile = Join-Path $BackupDir "neo4j_$Timestamp.dump"
try {
    # Neo4j CE 使用 neo4j-admin database dump（需先停止資料庫或使用 online backup）
    docker exec ai_kb_neo4j neo4j-admin database dump neo4j --to-stdout 2>$null | `
        Set-Content -AsByteStream $Neo4jFile
    Write-Host "      ✅ Neo4j 備份完成: $Neo4jFile"
} catch {
    Write-Warning "      ❌ Neo4j 備份失敗（CE 版不支援 online dump，請參考文件）: $_"
}

# ── 4. 上傳至 MinIO ─────────────────────────────────────────────
Write-Host "[4/4] 上傳備份至 MinIO..." -ForegroundColor Yellow
try {
    # 使用 MinIO mc 客戶端（docker run）上傳整個備份目錄
    $localPath = $BackupDir -replace "\\", "/"
    docker run --rm --network ai_kb_network `
        -v "${BackupDir}:/backup" `
        minio/mc:latest sh -c `
        "mc alias set myminio http://minio:9000 minioadmin minioadmin 2>/dev/null; mc cp -r /backup myminio/ai-kb-backups/$Timestamp/"
    Write-Host "      ✅ MinIO 上傳完成: ai-kb-backups/$Timestamp/"
} catch {
    Write-Warning "      ❌ MinIO 上傳失敗: $_"
}

# ── 5. 清理舊備份（本機） ────────────────────────────────────────
Write-Host "[5/5] 清理 $Retention 天前的本機備份..." -ForegroundColor Yellow
$cutoff = (Get-Date).AddDays(-$Retention)
Get-ChildItem -Path $BackupRoot -Directory | Where-Object {
    $_.LastWriteTime -lt $cutoff
} | ForEach-Object {
    Remove-Item $_.FullName -Recurse -Force
    Write-Host "      🗑  已刪除舊備份: $($_.Name)"
}

Write-Host ""
Write-Host "=== 備份完成 === 儲存位置: $BackupDir" -ForegroundColor Green
Write-Host "MinIO 管理介面: http://localhost:9001 (帳號: minioadmin)"
