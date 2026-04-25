# Feature Report — 知識庫多對多重構 + 標籤管理強化

**日期**：2026-04-22  
**執行者**：GitHub Copilot  
**狀態**：✅ Build 通過，已部署

---

## 1. 功能摘要

將文件與知識庫的關係從一對一（`documents.knowledge_base_id`）擴展為多對多（`document_knowledge_bases` 中介表），並引入向量相似度自動分類機制：Celery 任務完成索引後自動計算文件向量與各 KB 向量的 cosine 相似度，相符者自動關聯、不符者改為建議 KB 名稱。同步強化標籤管理：AI tag prompt 改為優先複用現有標籤、增加「從所有文件移除」與「徹底刪除」兩種操作。前端移除逐一彈框審核流程，改為側欄集中待審核區塊，支援批次確認或拒絕。

---

## 2. 完成功能清單

| 功能 | 說明 | 狀態 |
|------|------|------|
| `document_knowledge_bases` 多對多表 | `doc_id / kb_id / score / source / created_at`，含 CASCADE | ✅ |
| `_find_similar_kbs()` 兩階段向量比對 | 優先 kb_id payload；fallback 改用 doc_id scroll，numpy cosine 相似度 | ✅ |
| Tag prompt 優先複用現有標籤 | 列出可複用清單，≥70% 相關直接用舊 tag，無法描述才建新 tag | ✅ |
| `DocumentOut` 補 `kb_list` 欄位 | `[{kb_id, kb_name, score, source}]`，batch load，依 score 降序 | ✅ |
| `PATCH /documents/{id}/knowledge-bases` | `confirm + kb_ids` 寫 `document_knowledge_bases`；`reject` 清空 suggested | ✅ |
| `DELETE /tags/{id}/documents/all` | 移除所有文件關聯，tag 本身保留，回傳 `removed_doc_count` | ✅ |
| `DELETE /tags/{id}` 回傳 `deleted_doc_count` | 改為 HTTP 200，含影響篇數，供前端確認框顯示 | ✅ |
| DocsView 集中審核 UI | 移除逐一 `ElMessageBox`，改為側欄「待審核」區塊 + [全部確認] / [全部拒絕] | ✅ |
| 文件卡片多 KB badge | 由 `knowledge_base_name` 單一 tag 改為 `v-for kb in doc.kb_list` 多 badge | ✅ |
| 側欄新增標籤 dialog + 兩種刪除 | `el-color-picker` 建立 tag；每個 tag chip 加 `el-dropdown` 右鍵選單 | ✅ |

---

## 3. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `backend/models.py` | 更新 | 新增 `DocumentKnowledgeBase` model；`Document` / `KnowledgeBase` 補 `kb_assoc` / `doc_assoc` relationship |
| `backend/tasks/document_tasks.py` | 更新 | 重寫 `_llm_suggest_tags` prompt；新增 `_find_similar_kbs()`；KB hook 改為多對多寫入 |
| `backend/routers/documents.py` | 更新 | `DocumentOut` 加 `kb_list`；`list_documents` 補 batch JOIN；新增 `PATCH /{id}/knowledge-bases` |
| `backend/routers/tags.py` | 更新 | `DELETE /{id}` 改 HTTP 200 + `deleted_doc_count`；新增 `DELETE /{id}/documents/all` |
| `backend/config.py` | 更新 | 新增 `KB_SIMILARITY_THRESHOLD: float = 0.75` |
| `frontend/src/api/index.js` | 更新 | 新增 `docsApi.confirmKbs`、`tagsApi.removeFromAll` |
| `frontend/src/views/DocsView.vue` | 更新 | 輪詢改 `pendingReviews` 收集；側欄待審核區塊；多 KB badge；新增標籤 dialog；tag 右鍵選單 |
| `scripts/init_db.sql` *(migration)* | 新增 | `CREATE TABLE document_knowledge_bases`；`ALTER TABLE documents ADD suggested_kb_id/name` |

---

## 4. 關鍵技術決策

### 4.1 兩階段向量比對 fallback

Qdrant payload 中 `kb_id` 欄位為新增欄位，舊資料 chunks 沒有此 field。若直接用 `FieldCondition(key="kb_id")` scroll，舊 KB 的所有 chunk 都會被跳過，導致相似度比對完全失效。

解法：先嘗試 `kb_id` payload；若該 KB 取回 0 個 chunk，改從 PostgreSQL `document_knowledge_bases` 表取出該 KB 下的 `doc_id` 清單，再用 `FieldCondition(key="doc_id")` 逐一 scroll（最多前 10 篇文件 × 50 chunks），保證舊資料也能正常比對。

### 4.2 保留 `documents.knowledge_base_id` 向下相容

多對多關係建立後，原有欄位 `knowledge_base_id`（單值）保留：自動分類時寫入分數最高的 KB ID，手動確認時更新為所選 KB。舊版 API（`PATCH /knowledge-base` 單數）保留不刪除，確保其他服務的現有呼叫不受影響。

### 4.3 tag 刪除區分兩種操作的必要性

「徹底刪除」（`DELETE /tags/{id}`）會同時移除 tag 實體及所有關聯，一旦刪除無法復原；「從所有文件移除」（`DELETE /tags/{id}/documents/all`）只清除中介表關聯，tag 名稱與設定保留，可在之後重新套用。兩種操作在前端分開呈現於右鍵選單，並各自有不同的確認提示文字，避免誤操作。

### 4.4 `pendingReviews` 集中收集取代逐一彈框

原設計在輪詢中偵測到有建議的文件時立即彈出 `ElMessageBox`。批次匯入 20+ 篇文件時，會連續彈出 20+ 個對話框，使用者無法操作頁面其他元素，且關閉一個又立刻出現下一個。改為將所有有待審核建議的文件收集至 `pendingReviews` ref，在側欄顯示數量 badge，提供「全部確認」/「全部拒絕」批次操作，大幅改善 UX。

### 4.5 `_seenReviewIds` 防止輪詢重複收集

輪詢每 5 秒執行一次，若不加防重機制，同一篇文件會被反覆加入 `pendingReviews`。使用 module-level `Set` `_seenReviewIds` 記錄已收集過的 `doc_id`，確保每篇文件只會出現一次在待審核清單中。

---

## 5. 踩坑記錄

### 5.1 `_find_similar_kbs`：舊資料 kb_id payload 缺失導致比對全部跳過

**現象**：新上傳文件完成索引後，`_find_similar_kbs` 對所有 KB 均回傳 0 個 chunk，相似度比對無法執行，最終全部走「建議 KB 名稱」邏輯而非自動歸類。

**根因**：Qdrant 舊 chunk 的 payload 結構為 `{doc_id, content, page_number, title, source_url}`，不含 `kb_id`。新增的 `FieldCondition(key="kb_id")` filter 造成全部 scroll 結果為空。

**解法**：加入雙階段 fallback（詳見 4.1）。

### 5.2 批次匯入觸發大量 `ElMessageBox` 導致使用者無法操作

**現象**：一次匯入 20 筆 URL 後，輪詢連續觸發 20 次 `ElMessageBox.confirm`，關閉一個立刻彈出下一個，頁面完全無法操作。

**解法**：移除輪詢內的逐一彈框邏輯，改為 `pendingReviews` 收集機制（詳見 4.4）。

---

## 6. 後續待辦

| 項目 | 說明 | 優先級 |
|------|------|--------|
| YouTube yt-dlp 字幕擷取 | 環境已就緒（ffmpeg + nodejs + yt-dlp 已驗證），待實作 Celery task + endpoint + 前端入口 | P1 |
| Facebook 公開貼文 Playwright 爬取 | playwright-service 已部署，待實作解析邏輯 | P2 |
| Tag 相似度合併提示 | 建立新 tag 時，若與現有 tag 語意相似度 > 0.85，提示使用者考慮合併 | P2 |
| KB 相似度閾值使用者可調 | `KB_SIMILARITY_THRESHOLD` 目前固定 0.75，應在設定頁提供調整入口並寫入 DB | P2 |
