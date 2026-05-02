# BruV AI 知識庫

> 完全地端、零雲端依賴的私有 AI 知識庫系統。  
> 上傳文件，透過 RAG + LLM 智慧問答，知識圖譜自動建立。

[![Latest Release](https://img.shields.io/github/v/release/brucecheng886-png/BruV-AI-?label=最新版本&color=blue)](https://github.com/brucecheng886-png/BruV-AI-/releases/latest)
[![Platform](https://img.shields.io/badge/平台-Windows%2010%2F11-blue)](https://github.com/brucecheng886-png/BruV-AI-/releases/latest)

---

## 下載安裝

**[⬇️ 下載最新版安裝程式](https://github.com/brucecheng886-png/BruV-AI-/releases/latest)**

### 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 10 / 11（64-bit） |
| 記憶體 | 16 GB+（建議） |
| 硬碟空間 | 30 GB+（Docker images + AI 模型） |
| 網路 | 首次啟動需下載約 15 GB |

### 安裝步驟

1. 下載並執行 `BruV AI Setup.exe`
2. 選擇安裝路徑，完成安裝
3. 開啟 **BruV AI**，依照設定精靈（5 個步驟）完成初始設定：
   - Step 1：確認 Docker Desktop 已安裝並執行
   - Step 2：設定管理員帳號與密碼
   - Step 3：選擇 AI 模型來源（本機 Ollama / 雲端 API）
   - Step 4：下載本機 AI 模型（可選）
   - Step 5：啟動所有服務，完成設定
4. 設定完成後，每次開啟 APP 會自動啟動後台服務

### 解除安裝

透過 Windows「新增或移除程式」解除安裝時，會依序詢問：

1. **是否刪除 Docker 容器？**（選「是」停止並移除容器，資料保留；選「否」容器維持原狀）
2. **是否刪除所有資料？**（選「是」永久刪除資料庫、模型、上傳檔案，⚠️ **不可復原**）

解除安裝後應用程式設定會自動清除，重新安裝後可正常進入設定精靈。

---

## 功能特色

- 📄 **文件知識庫** — 支援 PDF、Word、網頁爬取，自動向量化索引
- 🤖 **智慧問答** — RAG + LLM，回答有依據、可追溯來源
- 🕸️ **知識圖譜** — Neo4j 自動建立概念關聯，視覺化呈現
- 🔒 **完全地端** — 所有資料留在本機，不上傳任何雲端
- 🌐 **雙模型支援** — 本機 Ollama 或雲端 OpenAI / Azure / Gemini 自由切換
- 🖥️ **桌面應用** — Electron 封裝，一鍵安裝，開機自動啟動

---

## 系統架構

```
BruV AI Electron App
    └── Vue 3 + Vite + Element Plus  (Nginx :80)
            │
            ▼
        FastAPI Backend (:8000)
        ├── Celery Worker     — 非同步任務（上傳、爬蟲）
        ├── Qdrant (:6333)    — 向量搜尋
        ├── PostgreSQL (:5432)— 結構資料
        ├── Neo4j (:7687)     — 知識圖譜
        ├── Redis (:6379)     — 訊息佇列 / 快取
        ├── MinIO (:9000)     — 檔案儲存
        └── Ollama (host)     — 本機 LLM / Embedding
```

---

## 開發者文件

### 前置需求

| 工具 | 版本 |
|------|------|
| Docker Desktop | ≥ 27（含 Docker Compose v2） |
| Node.js | ≥ 18 |
| Ollama | ≥ 0.3（本機安裝） |

### 本地開發啟動

```powershell
# 1. 複製環境變數
Copy-Item .env.example .env
# 編輯 .env，修改所有 changeme_ 開頭的密碼

# 2. 啟動後端服務
docker compose up -d

# 3. 啟動 Electron（開發模式）
cd electron
npm install
npm start
```

或直接執行 **啟動.bat** 一鍵啟動開發環境。

### 常用指令

```powershell
# 查看服務狀態
docker compose ps

# 查看 log
docker compose logs -f backend

# 重啟服務
docker compose restart backend

# 手動備份
.\scripts\backup.ps1
```

---

## 版本紀錄

| 版本 | 說明 |
|------|------|
| v1.0.18 | Docker Desktop 下載連結改為直接下載安裝檔 |
| v1.0.17 | 解除安裝自動清除設定，重裝可正常進入 setup wizard |
| v1.0.16 | 解除安裝時提供刪除容器 / 刪除全部資料選項 |
| v1.0.15 | Setup wizard 視窗高度修正，消除捲軸 |
| v1.0.14 | 自動清除殘留容器，解決跨版本升級衝突 |
| v1.0.13 | 修正 Docker Compose project name 固定為 `bruv-ai` |

---

## 安全注意事項

- `.env` 檔案**不得** commit 至 git（已加入 .gitignore）
- 所有 `changeme_` 密碼**必須**在部署前修改
- `JWT_SECRET_KEY` 建議使用 32 字元以上隨機字串

