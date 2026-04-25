# Gate Report — Scope Feature（對話範圍綁定）

**日期**：2026-04-20  
**執行者**：GitHub Copilot  
**狀態**：✅ 全部通過

---

## 1. 驗收結果

| 項目 | 狀態 | 說明 |
|------|------|------|
| Step 1 — DB 遷移（`init_db.sql`） | ✅ | `conversations` 加 `kb_scope_id` (UUID)、`doc_scope_ids` (UUID[]) |
| Step 2 — `backend/models.py` | ✅ | SQLAlchemy `Conversation` 加兩欄位，Live DB `ALTER TABLE` 已執行 |
| Step 3 — `backend/routers/chat.py` | ✅ | `ChatRequest` 加欄位、Qdrant filter 邏輯、import 驗證 OK |
| Step 4 — `backend/tasks/document_tasks.py` | ✅ | Qdrant payload 加 `kb_id`、SQL RETURNING 加 `knowledge_base_id` |
| Step 5 — `backend/scripts/migrate_qdrant_kb_id.py` | ✅ | dry-run 成功（0 筆，正常） |
| Step 6 — `frontend/src/api/index.js` | ✅ | `chatStream` 加 `kbScopeId`, `docScopeIds` 兩個選用參數 |
| Step 7 — `frontend/src/views/ChatView.vue` | ✅ | Scope Dialog + scope badge + convScope state |
| 驗收 1 — 後端重啟 | ✅ | `docker restart ai_kb_backend ai_kb_celery` 成功 |
| 驗收 2-1 — 全域 chat | ✅ | `POST /api/chat/stream` → 200，SSE token 事件正常回傳 |
| 驗收 2-2 — KB scope chat | ⏭️ | 系統尚無 KB，跳過（NO_KB） |
| 驗收 2-3 — conversations API | ✅ | `GET /api/chat/conversations` 回傳含 `kb_scope_id`、`doc_scope_ids` 欄位 |
| 驗收 3 — 前端 build | ✅ | `npm run build`：2011 modules transformed，exit 0，`dist/` 產生 |

---

## 2. 主要程式碼改動

### 2.1 `scripts/init_db.sql` + `backend/models.py`（Steps 1–2）

**init_db.sql** 新增兩條 ALTER TABLE（若欄位已存在則忽略）：

```sql
ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS kb_scope_id  UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS doc_scope_ids UUID[] NOT NULL DEFAULT '{}';
```

**models.py** `Conversation` 類別新增：

```python
kb_scope_id   = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True)
doc_scope_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
```

Live DB 已以相同 SQL 手動執行完成（`\d conversations` 確認欄位存在）。

---

### 2.2 `backend/routers/chat.py`（Step 3）

**新增欄位（`ChatRequest` / `ConversationOut`）**：

```python
# ChatRequest
kb_scope_id:   Optional[UUID] = None
doc_scope_ids: List[UUID]     = []

# ConversationOut
kb_scope_id:   Optional[UUID]
doc_scope_ids: List[UUID]
```

**`_rag_stream()` Qdrant filter 優先級邏輯（由高至低）**：

```
message doc_ids  →  conv doc_scope_ids  →  kb_scope_id  →  全域（無 filter）
```

實作以 `qdrant_client.models.Filter / FieldCondition / MatchAny` 組裝：

```python
if effective_doc_ids:
    qfilter = Filter(must=[FieldCondition(key="doc_id",
                     match=MatchAny(any=[str(i) for i in effective_doc_ids]))])
elif kb_scope_id:
    qfilter = Filter(must=[FieldCondition(key="kb_id",
                     match=MatchValue(value=str(kb_scope_id)))])
```

**建立對話時儲存 scope，載入舊對話時讀取 scope（`chat_stream` 端點）**：
- 新對話：從 `ChatRequest` 取 `kb_scope_id`, `doc_scope_ids` 寫入 DB
- 舊對話：從 DB 回填到 `_rag_stream()` 呼叫參數

---

### 2.3 `backend/tasks/document_tasks.py`（Step 4）

SQL RETURNING 新增 `knowledge_base_id`：

```python
# before
RETURNING id, title, status
# after
RETURNING id, title, status, knowledge_base_id
```

unpack 由 3 個變數改為 4 個，並將 `kb_id` 寫入 Qdrant payload：

```python
payload = {
    "doc_id":  str(doc_id),
    "kb_id":   str(knowledge_base_id) if knowledge_base_id else None,
    "chunk_index": i,
    "text":    chunk,
}
```

---

### 2.4 `backend/scripts/migrate_qdrant_kb_id.py`（Step 5）

新建 migration 腳本，用於補寫舊有 Qdrant points 的 `kb_id` payload。

執行指令：
```bash
docker exec ai_kb_backend python scripts/migrate_qdrant_kb_id.py --dry-run
docker exec ai_kb_backend python scripts/migrate_qdrant_kb_id.py
```

注意：腳本建在 `backend/scripts/`（非根目錄 `scripts/`），因為 docker-compose volume 掛載的是 `./backend:/app`。

---

### 2.5 `frontend/src/api/index.js`（Step 6）

`chatStream` 函式簽名新增兩個選用尾端參數：

```js
// before
export async function chatStream(query, conversationId, model, signal = null, docIds = [])

// after
export async function chatStream(query, conversationId, model, signal = null,
                                  docIds = [], kbScopeId = null, docScopeIds = [])
```

request body 加入：

```js
kb_scope_id:   kbScopeId,
doc_scope_ids: docScopeIds,
```

---

### 2.6 `frontend/src/views/ChatView.vue`（Step 7）

**新增 state**：

```js
const knowledgeBases = ref([])
const convScope      = ref({ mode: 'global', kbId: null, docIds: [] })
const scopeDialog    = ref({ visible: false, tempMode: 'global', tempKbId: null, tempDocIds: [] })
```

**新增函式**：
- `loadKBs()` — 於 `onMounted` 呼叫，取 KB 列表供 Dialog 使用
- `confirmScope()` — 確認 Dialog 後設定 `convScope`，再實際建立對話
- `newConversation()` — 改為開啟 Scope Dialog（而非直接建立對話）
- `selectConversation()` — 切換對話時從 conv 物件回填 `convScope`

**Template 新增**：
- Scope Dialog（`el-dialog`）：全域 / 指定知識庫 / 指定文件 三個 `el-radio`
- 側欄 conv-item scope badge：
  - 藍色 `[KB]`：已綁定知識庫
  - 黃色 `📄 N`：已綁定 N 個文件

---

## 3. 踩坑記錄

### 3.1 UNIQUE INDEX 設計錯誤

**問題**：一開始設計 `conversations.kb_scope_id` 時差點誤加 `UNIQUE` 約束，使得一個 KB 只能被一個對話使用。

**正確設計**：`kb_scope_id` 僅加 FK（`REFERENCES knowledge_bases(id) ON DELETE SET NULL`），不加 UNIQUE INDEX。多個對話可同時綁定同一個 KB。

---

### 3.2 Migration Script 放錯目錄

**問題**：將 `migrate_qdrant_kb_id.py` 建在根目錄的 `scripts/`，`docker exec` 時找不到（`No such file or directory`）。

**原因**：docker-compose volume 掛載為 `./backend:/app`，容器內 `/app/scripts/` 對應的是 `backend/scripts/`，根目錄 `scripts/` 完全未掛入容器。

**解法**：將腳本建在 `backend/scripts/migrate_qdrant_kb_id.py`，執行時用：
```bash
docker exec ai_kb_backend python scripts/migrate_qdrant_kb_id.py
```
（容器工作目錄是 `/app`，`scripts/` 即為 `/app/scripts/`）

---

### 3.3 Windows PowerShell 的 token 展開方式與 bash 不同

**問題**：bash 的 `TOKEN=$(command)` 語法在 PowerShell 中完全不識別，導致一連串錯誤。

**解法**：PowerShell 一律改用：

```powershell
# 取 token
$loginResp = Invoke-RestMethod -Method POST -Uri http://localhost:8000/api/auth/login `
             -ContentType "application/json" -Body '{"email":"123","password":"123"}'
$TOKEN = $loginResp.access_token

# 帶 headers
$headers = @{ "Authorization" = "Bearer $TOKEN"; "Content-Type" = "application/json" }

# 呼叫 API
$resp = Invoke-RestMethod -Method GET -Uri "http://localhost:8000/api/..." -Headers $headers
```

另外，`curl` 在 PowerShell 中是 `Invoke-WebRequest` 的 alias，不接受 `-H` 旗標，需改用 `curl.exe` 或直接用 `Invoke-WebRequest`（加 `-UseBasicParsing` 避免安全性警告 prompt）。

---

### 3.4 帳號密碼非預設值

**問題**：規格文件中標示帳號為 `admin@local / admin123456`，但實際 DB 中只有一筆 `email=123, password=123` 的 admin 帳號，導致登入一直回傳「帳號或密碼錯誤」。

**解法**：以 `SELECT email FROM users` 查表確認後，改用 `123/123`。

---

### 3.5 documents.py upload endpoint 靜默丟棄 knowledge_base_id

**問題**：前端 `docsApi.upload(file, kbId)` 已將 `knowledge_base_id` 放入 FormData 傳送，但後端 `POST /api/documents/upload` 函式簽名只接收 `file: UploadFile`，完全未宣告 `knowledge_base_id` 參數，導致 form field 被 FastAPI 靜默丟棄，Document 記錄的 `knowledge_base_id` 永遠為 NULL。

**根本原因**：前後端實作時間差——前端先補了傳參邏輯，後端 endpoint 未同步更新。

**修復**（`backend/routers/documents.py`）：
1. `import` 補上 `Form`
2. 函式簽名加 `knowledge_base_id: Optional[str] = Form(None)`
3. `Document()` 建立時加 `knowledge_base_id=knowledge_base_id or None`

**驗收**：上傳後查 DB `SELECT knowledge_base_id FROM documents WHERE id=...`，確認值等於傳入的 KB UUID，status=indexed，chunk_count=9。

---

### 3.6 update_admin_password.py 寫死 email 導致重設無效

**問題**：`scripts/update_admin_password.py` 將目標帳號寫死為 `admin@local`，但實際 DB 中 admin email 為 `123`。執行腳本時 `rowcount=0`（無任何更新），密碼從未被改過，驗收登入持續失敗。

**解法**：重寫腳本，email 與 password 改為從命令列參數（`sys.argv`）或環境變數（`ADMIN_EMAIL` / `ADMIN_PASSWORD`）讀取，所有 DB 連線參數也改從環境變數讀取。並在 `rowcount=0` 時印出 WARNING 提醒。

**使用方式**：
```bash
# 在容器內執行，傳入實際 email
docker exec ai_kb_backend python scripts/update_admin_password.py 123 new_password
```

---

## 4. 下一步待辦（本次範圍外）

| # | 項目 | 說明 |
|---|------|------|
| 1 | 補跑 `migrate_qdrant_kb_id.py` | 新增 KB 並上傳文件後，需執行一次（不含 `--dry-run`）補寫舊 Qdrant points 的 `kb_id` payload |
| 2 | Scope Dialog「指定文件」多選清單 | 目前文件沒有 `knowledge_base_id` 時無法按 KB 篩選可選清單；需等文件管理 UI 支援 KB 指派後才能完整運作 |
| 3 | highlight.js 按需載入 | 延續自 `feature-report-chat-upgrade.md`：目前全量引入 highlight.js，應改為僅按需載入常用語言包（js/python/bash），減少 bundle 體積 |
| 4 | KB scope chat 端對端驗收 | 驗收 2-2 因系統尚無 KB 而跳過，建立第一個 KB 後需補測 `POST /api/chat/stream` 帶 `kb_scope_id` 的完整流程 |
| 5 | `doc_scope_ids` UI 入口 | 目前 Scope Dialog 的「指定文件」需手動輸入 UUID；後續應改為從文件列表多選（勾選器或搜尋框） |
