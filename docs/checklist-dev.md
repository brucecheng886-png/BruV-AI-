# 測試清單 — 我的電腦（主開發機）

> 角色：Docker 服務 / 原始碼 / API 驗證
> 更新日期：2026-05-11

---

## 登入頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-L1 | 正確帳號密碼登入 | `POST /api/auth/login` | 取得 JWT，跳轉對話頁 | ✅ |
| D-L2 | 錯誤密碼登入 6 次 → Rate Limit | `POST /api/auth/login` | dev 模式 50/min，prod 模式 5/min | ✅ |
| D-L3 | 點擊「忘記密碼」 | 路由跳轉 | 頁面正常跳轉（前端 UI 測試） | ⬜ |

---

## 對話頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-C1 | 發送訊息，LLM 正常回覆 | `POST /api/chat/stream` (SSE) | 有文字回應，無 dim=0 錯誤 | ✅ |
| D-C2 | 新建對話 | `POST /api/chat/conversations` | 對話列表新增一筆 | ✅ |
| D-C3 | 切換已有對話 / 取得清單 | `GET /api/chat/conversations` | 歷史對話清單正常載入 | ✅ |
| D-C4 | 重命名對話 | `PATCH /api/chat/conversations/{id}` | 標題更新 | ✅ |
| D-C5 | 刪除對話 | `DELETE /api/chat/conversations/{id}` | 對話從列表消失 | ✅ |
| D-C6 | 取得對話歷史訊息 | `GET /api/chat/conversations/{id}` | 訊息列表正常回傳 | ✅ |
| D-C7 | 附加文件發送對話 | `POST /api/chat/stream-with-file` | 讀取文件內容回答 | ⬜ |
| D-C8 | 儲存訊息到知識庫 | `POST /api/chat/messages/{id}/save-to-kb` | 成功提示 | ⬜ |
| D-C9 | 切換 Agent 模式發送 | `POST /api/agent/run` → `GET /api/agent/tasks/{id}` | Agent 執行結果回報 | ⬜ |
| D-C10 | 選擇知識庫 Scope 發送 | `POST /api/chat/stream` (kbScopeId) | 僅搜尋指定 KB | ⬜ |
| D-C11 | 套用 Prompt 模板 | `GET /api/prompt-templates/` | 模板內容填入輸入框 | ⬜ |

---

## 文件管理頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-D1 | 上傳文件（txt/PDF） | `POST /api/documents/upload` | 回報 202，Celery 任務開始處理 | ✅ |
| D-D2 | 查看文件處理狀態 | `GET /api/documents/{id}/status` | 回傳 pending/processing/done | ✅ |
| D-D3 | 關鍵字搜尋文件 | `GET /api/documents?search=xxx` | 篩出相關結果 | ✅ |
| D-D4 | 文件計數 | `GET /api/documents/count` | 回傳 total 數字 | ✅ |
| D-D5 | 建立知識庫 | `POST /api/knowledge-bases` | 新 KB 建立成功（201） | ✅ |
| D-D6 | 知識庫清單 | `GET /api/knowledge-bases` | KB 列表正常載入 | ✅ |
| D-D7 | 知識庫詳情 | `GET /api/knowledge-bases/{id}` | KB 名稱/描述正確 | ✅ |
| D-D8 | 知識庫統計 | `GET /api/knowledge-bases/{id}/stats` | 回傳文件數等統計 | ✅ |
| D-D9 | 刪除文件 | `DELETE /api/documents/{id}` | 文件軟刪除成功 | ✅ |
| D-D10 | 文件 AI 語意搜尋 | `POST /api/documents/search` (SSE) | 回報相似文件 | ⬜ |
| D-D11 | 查看垃圾桶 | `GET /api/documents/trash` | 垃圾桶文件列表 | ⬜ |
| D-D12 | 清空垃圾桶 | `DELETE /api/documents/trash/empty` | 永久刪除 | ⬜ |

---

## 標籤 / Ontology 頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-O1 | 標籤清單 | `GET /api/tags/` | 標籤列表正常 | ✅ |
| D-O2 | 建立標籤 | `POST /api/tags/` | 新標籤建立（201） | ✅ |
| D-O3 | 更新標籤 | `PATCH /api/tags/{id}` | 名稱/顏色更新成功 | ✅ |
| D-O4 | 刪除標籤 | `DELETE /api/tags/{id}` | 標籤移除成功 | ✅ |
| D-O5 | 標籤附加文件 | `POST /api/tags/{id}/documents/{doc_id}` | 文件貼標籤成功 | ⬜ |
| D-O6 | 標籤移除文件 | `DELETE /api/tags/{id}/documents/{doc_id}` | 文件移除標籤成功 | ⬜ |

---

## 插件管理頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-P1 | 列表已安裝插件 | `GET /api/plugins` | 插件列表顯示 | ✅ |
| D-P2 | 插件 Catalog | `GET /api/plugins/catalog/list` | 可安裝插件清單 | ✅ |
| D-P3 | 建立插件 | `POST /api/plugins` | 插件建立成功（201） | ✅ |
| D-P4 | 啟用 / 停用插件 | `POST /api/plugins/{id}/toggle` | 狀態切換成功 | ✅ |
| D-P5 | 刪除插件 | `DELETE /api/plugins/{id}` | 插件從列表消失（204） | ✅ |
| D-P6 | 執行插件 | `POST /api/plugins/{id}/invoke` | 回傳執行結果 | ⬜ |
| D-P7 | Notion 同步 | `POST /api/plugins/notion/sync` | 回報 202，同步任務建立 | ⬜ |

---

## 設定頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-S1 | 取得模型清單 | `GET /api/settings/models` | Ollama 模型列表 | ✅ |
| D-S2 | 取得 LLM 設定 | `GET /api/settings/llm` | 設定回傳成功 | ✅ |
| D-S3 | 取得 RAG 設定 | `GET /api/settings/rag` | 設定回傳成功 | ✅ |
| D-S4 | 取得 Chat 設定 | `GET /api/settings/chat` | 設定回傳成功 | ✅ |
| D-S5 | 修改帳號密碼 | `POST /api/settings/user/change-password` | 成功提示 | ✅ |
| D-S6 | 取得 Schema 設定 | `GET /api/settings/schema` | Schema 正常回傳 | ✅ |
| D-S7 | 備份清單 | `GET /api/settings/backup/list` | 備份檔案列表 | ✅ |
| D-S8 | 測試 LLM 連線 | `POST /api/settings/llm/test` | 回報連線成功 / 失敗 | ⬜ |
| D-S9 | 更新 LLM 設定 | `POST /api/settings/llm` | 儲存成功提示 | ⬜ |

---

## Agent Skills 頁面

| # | 操作 | 觸發 API | 預期結果 | 狀態 |
|---|------|---------|---------|------|
| D-G1 | 已安裝 Skills 清單 | `GET /api/agent-skills/` | Skills 列表正常 | ✅ |
| D-G2 | 可安裝 Skills Store | `GET /api/agent-skills/store/available` | Store 清單正常 | ✅ |
| D-G3 | 系統 Health Check | `GET /api/health` | 200 OK | ✅ |
| D-G4 | 服務狀態細節 | `GET /api/health/services` | Qdrant/Ollama ok，Playwright ❌ DNS | ⚠️ |

---

## 基礎服務驗證

| # | 項目 | 狀態 | 備註 |
|---|------|------|------|
| D-I1 | Qdrant 不帶 key → 401 | ✅ | 2026-05-10 |
| D-I2 | Redis 不帶密碼 PING → NOAUTH | ✅ | 2026-05-10 |
| D-I3 | Ollama localhost:11434 可連通 | ✅ | 2026-05-11 |
| D-I4 | bge-m3 embedding 回傳 1024 維 | ✅ | 2026-05-11 |
| D-I5 | docker compose config 語法驗證 | ✅ | 2026-05-10 |

---

## 已修復的問題（本次測試發現）

| # | 問題 | 修復方式 | 日期 |
|---|------|---------|------|
| F-1 | `requirements.txt` 兩行合併（slowapi、webauthn） | 拆分成獨立兩行 | 2026-05-11 |
| F-2 | `FIDOCredential` 類別未定義 | 在 `models.py` 新增完整類別 | 2026-05-11 |
| F-3 | Qdrant SSL 錯誤（有 api_key 時自動 HTTPS） | 加 `https=False` 到所有 4 個 Qdrant 初始化 | 2026-05-11 |
| F-4 | admin@local 密碼 hash 為 placeholder | 用 psycopg2 參數化查詢設定正確 bcrypt hash | 2026-05-11 |
| F-5 | `CELERY_BROKER_URL` 無密碼 → Celery 認證失敗 | `.env` 改為 `redis://:密碼@redis:6379/1` | 2026-05-11 |
| F-6 | `REDIS_URL` 無密碼 → rate limiter 可能失效 | `.env` 加入密碼 | 2026-05-11 |

---

## 已知問題（待跟進）

| # | 問題 | 影響 | 優先 |
|---|------|------|------|
| K-1 | Playwright service DNS 解析失敗（`health/services` 回報 error） | 網頁爬取功能不可用 | 中 |
| K-2 | `POST /api/tags`（無尾斜線）回 307 Redirect，PS Invoke-WebRequest 不跟進 | 前端需確認使用 trailing slash | 低 |
