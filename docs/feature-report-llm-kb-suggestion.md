# Feature Report — LLM 自動 KB 分類建議

**日期**：2026-04-21  
**執行者**：GitHub Copilot  
**狀態**：✅ 端對端驗收通過，後端已重啟

---

## 1. 功能摘要

使用者上傳文件後，若未手動指定知識庫，系統於 Celery 攝取任務完成後自動呼叫 Ollama LLM 分析文件內容，從現有知識庫清單中選出最適合的一個，或於系統無任何 KB 時建議並自動建立新 KB。建議結果暫存於 `documents.suggested_kb_id` 與 `documents.suggested_kb_name`，前端 DocsView 的 polling 機制偵測到後以 `ElMessageBox.confirm` 彈出確認框，使用者確認後正式將文件歸屬到該 KB，拒絕則清空建議。

---

## 2. 完成功能清單

| # | 功能 | 狀態 |
|---|------|------|
| 1 | DB 新增 `suggested_kb_id` / `suggested_kb_name` 欄位 | ✅ |
| 2 | `models.py Document` 新增對應欄位 | ✅ |
| 3 | `_llm_suggest_kb()` 函式：有 KB 時選最適合的，無 KB 時建議新名稱 | ✅ |
| 4 | `ingest_document` 尾端插入 KB 分類 hook（不影響 indexed 狀態） | ✅ |
| 5 | 系統無任何 KB 時自動 INSERT 新 KB（LLM 命名） | ✅ |
| 6 | `DocumentOut` schema 補 `suggested_kb_id` / `suggested_kb_name` | ✅ |
| 7 | `PATCH /api/documents/{id}/knowledge-base` endpoint（confirm / reject） | ✅ |
| 8 | `docsApi.confirmKbSuggestion(docId, action)` API 封裝 | ✅ |
| 9 | DocsView polling 偵測 `suggested_kb_id` 並彈出確認框 | ✅ |
| 10 | `pendingSuggestions` Set 防止重複彈框 | ✅ |
| 11 | `distinguishCancelAndClose: true` 讓關閉視窗也視為 reject | ✅ |

---

## 3. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `backend/models.py` | 更新 | `Document` 新增 `suggested_kb_id` FK、`suggested_kb_name` Text；`KnowledgeBase.documents` / `Document.knowledge_base` 補 `foreign_keys` 參數 |
| `backend/tasks/document_tasks.py` | 更新 | 新增 `_llm_suggest_kb()` 函式；`ingest_document` 尾端插入 KB 分類 hook |
| `backend/routers/documents.py` | 更新 | `DocumentOut` 補兩個欄位；新增 `PATCH /{doc_id}/knowledge-base` endpoint |
| `frontend/src/api/index.js` | 更新 | `docsApi` 新增 `confirmKbSuggestion(docId, action)` |
| `frontend/src/views/DocsView.vue` | 更新 | 新增 `pendingSuggestions` ref；polling 補 suggested_kb_id 偵測與確認框邏輯 |
| `scripts/update_admin_password.py` | 重寫 | email / password 改從命令列參數或環境變數讀取；DB 連線參數全從環境變數讀取；rowcount=0 時印出 WARNING |

---

## 4. 關鍵技術決策

### 4.1 建議欄位放在 documents 表而非獨立表

選擇在 `documents` 表直接加 `suggested_kb_id`（UUID FK）與 `suggested_kb_name`（TEXT），而非獨立 `kb_suggestions` 表。  
理由：此功能只需記錄「最新一次建議」，無需保留歷史；直接加欄最簡單，API 不需額外 JOIN，前端也無需多一支 endpoint。`suggested_kb_name` 冗余儲存是刻意的，避免 JOIN 且方便前端直接顯示。

### 4.2 LLM 分類 hook 在 saga.commit() 之後執行

KB 分類邏輯位於 `saga.commit()` 之後，與現有 RELATED_TO Neo4j 步驟相同層級，以 `try/except` 包裹。  
好處：分類失敗不影響 `indexed` 狀態與 Saga 完整性；分類是「最後一哩路」，不應阻斷核心攝取流程。

### 4.3 條件：knowledge_base_id is None 才執行

只有在使用者上傳時未手動指定 KB 的情況下才啟動 LLM 分類，避免覆蓋使用者的明確選擇。對已指定 KB 的文件，hook 直接 skip。

### 4.4 前端用 polling 感知建議，不需新增 WebSocket / SSE

DocsView 已有 5 秒 polling 機制追蹤 `processing` 文件，直接在同一個 polling loop 內額外偵測 `suggested_kb_id` 即可，零架構成本。`pendingSuggestions` Set 確保每筆文件只彈一次確認框，`distinguishCancelAndClose: true` 讓「X 關閉」也走 reject 路徑，避免建議永遠卡住。

---

## 5. 踩坑記錄

### 5.1 Document 雙 FK 導致 SQLAlchemy AmbiguousForeignKeysError

**問題**：新增 `suggested_kb_id UUID REFERENCES knowledge_bases(id)` 後，`Document` 共有兩個 FK 指向 `knowledge_bases`（`knowledge_base_id` + `suggested_kb_id`）。SQLAlchemy 無法自動判斷 `KnowledgeBase.documents` 和 `Document.knowledge_base` relationship 應該走哪一個 FK，啟動時拋出 `AmbiguousForeignKeysError`。

**解法**：在兩個 relationship 定義上明確加入 `foreign_keys` 參數：
```python
# models.py — KnowledgeBase
documents: Mapped[list["Document"]] = relationship(
    "Document", back_populates="knowledge_base",
    foreign_keys="Document.knowledge_base_id",
)

# models.py — Document
knowledge_base: Mapped["KnowledgeBase | None"] = relationship(
    "KnowledgeBase", back_populates="documents",
    foreign_keys="Document.knowledge_base_id",
)
```

### 5.2 Celery task 是同步環境，不可用 async LLM client

**問題**：`backend/llm_client.py` 有現成的 `llm_stream()` 統一適配層，但它是 `async` 函式，Celery worker 執行於同步環境中，直接呼叫會無法執行。

**解法**：`_llm_suggest_kb()` 仿照同檔案已有的 `_llm_extract()` 寫法，用 `httpx.Client`（同步）直接呼叫 Ollama `/api/generate`，`timeout=30`，不走 `llm_client.py`。

### 5.3 LLM 回傳 kb_id 需驗證是否在現有清單中

**問題**：LLM 可能 hallucinate，回傳一個不存在於現有知識庫清單中的 UUID。若直接寫入 `suggested_kb_id`，FK 約束會讓 UPDATE 失敗。

**解法**：`_llm_suggest_kb()` 在解析 JSON 後加驗證——若回傳的 `kb_id` 不在 `valid_ids` 集合內，自動 fallback 到 `existing_kbs[0]`（第一個 KB）。

---

## 6. 後續待辦（非本次範圍）

| # | 項目 | 說明 |
|---|------|------|
| 1 | 確認彈框提供「改選其他 KB」選項 | 目前只有確認/拒絕，使用者無法在彈框中直接切換到其他 KB |
| 2 | 文件列表加「待分類」filter | 讓使用者主動查看所有 `suggested_kb_id` 非 NULL 的文件（不依賴 polling 通知） |
| 3 | `migrate_qdrant_kb_id.py` 補跑 | KB 建立後需執行一次，將舊有 Qdrant points 的 `kb_id` payload 補上，使向量搜尋的 KB 篩選生效 |
