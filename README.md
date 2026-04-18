# 地端 AI 知識庫 (BruV AI)

> 完全地端、零雲端依賴的私有 AI 知識庫系統。上傳文件，透過 RAG + LLM 智慧問答，知識圖譜自動建立。

---

## 快速開始

### 前置需求

| 工具 | 版本 |
|------|------|
| Docker Desktop | ≥ 27（含 Docker Compose v2） |
| NVIDIA GPU 驅動 | CUDA 12.x（RTX 3070+ 建議） |
| Node.js | ≥ 18（Electron） |
| Ollama | ≥ 0.3（本機安裝，非容器） |

### 安裝步驟

```powershell
# 1. 複製環境變數範本
Copy-Item .env.example .env
# 編輯 .env，修改所有 changeme_ 開頭的密碼

# 2. 拉取 Ollama 模型（需先安裝 Ollama）
ollama pull qwen2.5:14b
ollama pull bge-m3

# 3. 啟動全部服務
docker compose up -d

# 4. 初始化資料庫（首次執行）
docker exec ai_kb_postgres psql -U ai_kb_user -d ai_kb -f /docker-entrypoint-initdb.d/init_db.sql

# 5. 啟動 Electron 桌面應用
cd electron
npm install
npm start
```

### 雙擊啟動（最簡單方式）

- **啟動.bat** — 自動啟動所有 Docker 服務並開啟 Electron
- **停止.bat** — 關閉 Electron 並停止所有容器

---

## 服務入口

| 服務 | 網址 | 說明 |
|------|------|------|
| 桌面應用 | Electron 視窗 | 主要使用介面 |
| Web UI | http://localhost:80 | 瀏覽器存取 |
| Grafana 監控 | http://localhost:3001 | 帳號: admin |
| Prometheus | http://localhost:9090 | Metrics |
| MinIO 管理 | http://localhost:9001 | 帳號: minioadmin |
| Neo4j Browser | http://localhost:7474 | 圖資料庫 |
| Backend API | http://localhost:8000/docs | Swagger UI |

---

## 常用指令

```powershell
# 查看所有服務狀態
docker compose ps

# 查看特定服務 log
docker compose logs -f backend
docker compose logs -f celery-worker

# 重啟單一服務（不需重建）
docker compose restart backend

# 重建並重啟前端
docker compose build --no-cache nginx
docker compose up -d nginx

# 執行備份
.\scripts\backup.ps1

# 執行重啟恢復測試
.\scripts\test_recovery.ps1
```

---

## 系統架構

```
Electron Desktop App
    └── Vue 3 + Vite + Element Plus (Nginx :80)
            │
            ▼
        FastAPI Backend (:8000)
        ├── Celery Worker (非同步任務)
        ├── Qdrant (:6333) — 向量搜尋
        ├── PostgreSQL (:5432) — 結構資料
        ├── Neo4j (:7687) — 知識圖譜
        ├── Redis (:6379) — 訊息佇列 / 快取
        ├── MinIO (:9000) — 檔案儲存
        └── Ollama (host:11434) — LLM / Embedding

監控堆疊
    ├── Prometheus (:9090) — Metrics 收集
    ├── Loki (:3100) — 日誌聚合
    ├── Promtail — 日誌採集
    └── Grafana (:3001) — 視覺化 Dashboard
```

---

## Phase 完成狀態

| Phase | 名稱 | 狀態 |
|-------|------|------|
| 0 | 環境驗證 | ✅ 完成 |
| 1 | 基礎設施 | ✅ 完成 |
| 2 | RAG Chat MVP | ✅ 完成 |
| 3a | Playwright 爬蟲 | ⏸ 未開始 |
| 3b | 插件系統 | ⏸ 未開始 |
| 3c | Agent 整合 | ⏸ 未開始 |
| 4 | Ontology + Wiki + UI | ✅ 完成 |
| 5 | 監控 + 備份 + 生產就緒 | ✅ 完成 |

---

## 備份策略

手動執行備份：
```powershell
.\scripts\backup.ps1
```

備份內容：
- **PostgreSQL** — `pg_dump` 壓縮匯出
- **Qdrant** — 每個 collection 的 snapshot
- **Neo4j** — `neo4j-admin database dump`

備份儲存至本機 `C:\ai_kb_backups\{timestamp}\` 並同步至 MinIO `ai-kb-backups/` bucket。

設定 Windows 排程（每日凌晨 2 點）：
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -File C:\path\to\scripts\backup.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask -TaskName "AIKBBackup" -Action $action -Trigger $trigger
```

---

## 安全注意事項

- `.env` 檔案**不得** commit 至 git（已加入 .gitignore）
- 所有 `changeme_` 密碼**必須**在部署前修改
- `PLUGIN_ENCRYPT_KEY` 產生方式：
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `JWT_SECRET_KEY` 建議使用 32 字元以上隨機字串
