# Bug Fix Report — 2026-04-22

## 概覽

本次修復三個獨立 Bug，涵蓋 Qdrant 資料遷移、對話自動命名、側欄重命名互動。

---

## Bug 1：Qdrant kb_id 缺失導致 KB Scope RAG 找不到資料

### 症狀
指定知識庫範圍（KB Scope）發起對話後，回應顯示「知識庫中找不到相關資料」，即使該知識庫已有上傳文件並成功索引。

### 根本原因
`kb_id` payload 欄位是在後期功能迭代中才加入 Qdrant 索引流程的。在此之前已完成索引的舊 chunk 資料（共 203 筆）不包含 `kb_id` 欄位，導致 RAG 依 `kb_id` 篩選時召回結果為空。

### 修復方式
執行 `scripts/migrate_qdrant_kb_id.py`，讀取 PostgreSQL `document_chunks` 表中的 `kb_id` 對應關係，批次更新 Qdrant `chunks` collection 內 203 筆 point 的 payload，補寫 `kb_id` 欄位。

### 驗收結果
- 蛋白質分析知識庫可正常召回相關文件
- 相似度分數落在 52–53%，符合預期
- KB Scope 對話回應內容正常

---

## Bug 2：對話標題永遠顯示「新對話」

### 症狀
建立對話並送出第一則訊息後，側欄標題始終維持「新對話」，不會自動更新為有意義的標題。

### 根本原因
原先的命名邏輯是在 `chat_stream` 端點內以 `query[:30]` 作為標題，該邏輯在「先建立空對話（`POST /api/chat/conversations`）再送訊息」的新流程下永遠不觸發——因為對話在訊息送出前就已存在，`conv_title` 初始值即為「新對話」，條件判斷分支未進入命名流程。

### 修復方式

**後端（`backend/routers/chat.py`）：**
- `_rag_stream` 結尾（step 10）加入自動命名流程：若 `conv_title == "新對話"`，則呼叫 LLM 以使用者 query 和 AI 回應摘要生成簡短標題
- 生成後執行 `UPDATE conversations SET title = ?`
- 透過 SSE 推送 `{"type": "title", "title": "..."}` 事件通知前端

**前端（`frontend/src/views/ChatView.vue`）：**
- SSE 解析迴圈新增 `type === 'title'` 分支
- 以 `currentConvId` 在 `conversations` 陣列中找到對應對話，直接更新 `conv.title`，側欄即時反映新標題

### 驗收結果
- 第一則訊息回應結束後，側欄標題自動更新為 LLM 生成的描述性標題
- 標題生成失敗時僅記錄 warning，不影響主要對話流程

---

## Bug 3：雙擊側欄標題無法手動重命名

### 症狀
在側欄對話列表中雙擊標題文字，無反應，無法進入編輯模式（`el-input` 不出現）。

### 根本原因
`@click` 事件綁定的 `selectConversation(conv)` 是 async 函式，執行時會更新 `currentConvId`，觸發 Vue 響應式重新渲染 DOM。雙擊的第二次點擊（約 200ms 後）發生在 re-render 之後，事件目標（`event.target`）已是新的 DOM 節點，導致 `@dblclick` 事件路徑不符，無法觸發 `startRename(conv)`。

### 修復方式

**`frontend/src/views/ChatView.vue`：**
- 將 `@dblclick.stop="startRename(conv)"` 從內層 `conv-item-body` 移至外層 `conv-item` 容器
- `@click` 加入保護條件：`renamingId !== conv.id && selectConversation(conv)`，避免在重命名模式下重新選取同一對話導致額外 re-render
- 內層 `conv-item-body` 移除 `@dblclick.stop`，保留 `title="雙擊重命名"` 提示文字

### 驗收結果
- 單擊正常切換對話
- 雙擊正常進入編輯模式（`el-input` 出現並自動 focus）
- Enter 鍵確認，呼叫 `conversationsApi.rename`，側欄標題即時更新
- Escape 鍵取消，恢復原標題

---

## 受影響檔案

| 檔案 | 異動說明 |
|------|----------|
| `backend/routers/chat.py` | `_rag_stream` 加入自動命名流程與 SSE title 事件 |
| `frontend/src/views/ChatView.vue` | SSE title 分支、`@dblclick` 移至外層、`@click` 加條件 |
| `scripts/migrate_qdrant_kb_id.py` | 一次性遷移腳本，補寫 203 筆 chunk 的 kb_id payload |
