# 文件管理模組規劃架構

**版本**：v1.0  
**日期**：2026-04-18  
**範疇**：文件上傳 → 後端處理 → 前端呈現 全流程

---

## 一、支援檔案類型總覽

| 檔案類型 | 副檔名 | 後端解析器 | 分塊策略 | 前端呈現方式 |
|---------|--------|-----------|---------|------------|
| Excel 試算表 | `.xlsx` | openpyxl `load_workbook` | **TableRowChunker**（每列一 chunk） | 試算表 tab（SheetJS 渲染） |
| CSV | `.csv` | 純文字 UTF-8 / CP950 | **TableRowChunker** | 試算表 tab（SheetJS 渲染） |
| PDF | `.pdf` | pypdf `PdfReader` | **SentenceWindowNodeParser** (window=3) | 完整內容 tab（純文字） |
| Word | `.docx` | python-docx | **SentenceWindowNodeParser** | 完整內容 tab（純文字） |
| 純文字 | `.txt` | 多編碼 fallback | **SentenceWindowNodeParser** | 完整內容 tab（純文字） |
| Markdown | `.md` | 多編碼 fallback | **SentenceWindowNodeParser** | 完整內容 tab（Markdown 渲染） |
| HTML | `.html` | BeautifulSoup inner_text | **SentenceWindowNodeParser** | 完整內容 tab（純文字） |

---

## 二、後端處理管線

```
使用者上傳檔案
    │
    ▼
POST /api/documents/upload
    │  ① 儲存原始檔案到 MinIO（file_path = {doc_id}/{filename}）
    │  ② PG INSERT documents（status=pending）
    │  ③ 派發 Celery 任務 ingest_document.delay(doc_id)
    │
    ▼  （非同步）
Celery Worker: ingest_document
    │
    ├─ Step 1：MinIO 下載原始檔案 bytes
    │
    ├─ Step 2：依 file_type 選擇解析器
    │   ├─ xlsx / csv → TableRowChunker
    │   │     每列轉換為 "Header1: val | Header2: val"
    │   │     多 Sheet → sheet_idx 存入 page_number
    │   │
    │   ├─ pdf → PdfReader
    │   │     每頁 extract_text()，page_number = 頁碼
    │   │
    │   ├─ docx → python-docx
    │   │     所有段落合併成一個 text block
    │   │
    │   ├─ html → BeautifulSoup
    │   │     移除 script/style，取 inner_text
    │   │
    │   └─ txt / md / csv（純文字）→ 多編碼 fallback
    │         utf-8-sig → utf-8 → cp950 → latin-1
    │
    ├─ Step 3：分塊
    │   ├─ xlsx / csv → 每列直接 1 chunk（不做 sentence window）
    │   └─ 其他 → SentenceWindowNodeParser
    │         句子切割：以 。！？.!?\n 為邊界
    │         group = 3 句，CHUNK_SIZE 軟上限 400 字元
    │         window_context = 前後各 1 句（供 rerank 用）
    │
    ├─ Step 4：bge-m3 嵌入（1024 維）
    │     批次 8 筆，失敗自動降級逐一嵌入
    │     NaN 以 0.0 取代
    │
    ├─ Step 5：Qdrant upsert（向量 + payload）
    │
    ├─ Step 6：LLM 實體分析（qwen2.5:14b）
    │     輸入：前 2000 字
    │     輸出：{"summary", "tags", "entities"}
    │     實體類型：PERSON / PLACE / ORG / CONCEPT
    │
    ├─ Step 7：Neo4j MERGE entities / MENTIONS 關係
    │
    ├─ Step 8：PG INSERT chunks（含 embedding JSON）
    │
    └─ Step 9：PG UPDATE documents
          status = "indexed"
          chunk_count = N
          summary / tags = LLM 輸出
          （失敗則 status = "error"）
```

### Saga 保護（跨庫一致性）

任何步驟失敗，Saga 補償日誌（`/data/saga.db`）記錄並觸發逆序回滾：

```
Neo4j DETACH DELETE → Qdrant delete → PG DELETE chunks → saga_log COMPENSATED
```

---

## 三、API 端點規格

| Method | 路徑 | 說明 | 認證 |
|--------|------|------|------|
| `POST` | `/api/documents/upload` | 上傳檔案，回傳 `{doc_id, status:"pending"}` | ✅ JWT |
| `GET` | `/api/documents/` | 列表（`limit≤100, offset`） | ✅ JWT |
| `GET` | `/api/documents/{id}/status` | 輪詢處理狀態 | ✅ JWT |
| `GET` | `/api/documents/{id}/chunks` | 取分塊內容（`limit≤200`） | ✅ JWT |
| `GET` | `/api/documents/{id}/download` | 下載原始檔案 bytes（SheetJS 用） | ✅ JWT |
| `PATCH` | `/api/documents/{id}/meta` | 修改標題 / 描述 | ✅ JWT |
| `PATCH` | `/api/documents/{id}/fields` | 修改 custom_fields（不觸發 re-embed） | ✅ JWT |
| `PATCH` | `/api/documents/{id}/kb` | 移到知識庫 | ✅ JWT |
| `POST` | `/api/documents/{id}/reanalyze` | 重新觸發 LLM 分析 | ✅ JWT |
| `DELETE` | `/api/documents/{id}` | 刪除文件 + 三庫清理 | ✅ JWT |
| `POST` | `/api/documents/search` | AI 語意搜尋（向量相似度） | ✅ JWT |

---

## 四、前端呈現架構

### 4.1 文件卡片（列表頁）

```
┌─────────────────────┐
│  [ICON] [副檔名 badge] │  ← 檔案類型圖示 + 彩色 badge
│                     │
│  文件標題（截斷）      │
│  狀態 badge          │  ← pending / processing / indexed / error
│  chunk 數量          │
│  上傳日期            │
└─────────────────────┘
```

**狀態顏色規則**：
- `pending` → 灰色（等待佇列）
- `processing` → 橙色動態（Celery 處理中）
- `indexed` → 綠色（可搜尋）
- `error` → 紅色（攝取失敗）

**後台完成通知**：前端每 5 秒輪詢，狀態從 processing/pending 變 indexed 時彈出 `✅ ElMessage success`，變 error 時彈出 `❌ ElMessage error`。

---

### 4.2 文件側邊面板（Panel）

點擊卡片開啟右側 Drawer，包含以下 Tab：

```
[資訊]  [Chunks]  [試算表*]  [完整內容]  [編輯]
```
> `*` 試算表 Tab 僅 xlsx / csv 顯示

#### Tab：資訊
- 顯示：標題、狀態、chunks 數量、上傳時間、摘要、標籤
- 所屬知識庫

#### Tab：Chunks
- 分頁顯示所有 chunk（最多 200 筆）
- 每筆顯示：chunk 序號、頁碼、文字內容
- 搜尋框（客戶端篩選）

#### Tab：試算表（xlsx / csv 專屬）
- 呼叫 `GET /api/documents/{id}/download` 取得原始 bytes
- 使用 SheetJS（`window.XLSX`，靜態載入 `/xlsx.full.min.js`）解析
- 多 Sheet → 子 tab 切換
- 渲染為 HTML `<table>`，加入滾動容器

**為何不用 Chunks 顯示 xlsx？**  
Chunks 儲存的是 AI 語意索引文字（`Header: val | Header: val` 格式），可讀性低。試算表 tab 直接從 MinIO 取原始檔案渲染，保留原始格式。

#### Tab：完整內容
- 呼叫 `GET /api/documents/{id}/chunks?limit=200`
- 將所有 chunk 的 `content` 依序拼接
- xlsx / csv 顯示藍色提示橫幅，引導使用試算表 tab

#### Tab：編輯
- 修改文件標題、描述
- `PATCH /api/documents/{id}/meta`

---

### 4.3 各類型最佳呈現對應表

| 類型 | 預設開啟 Tab | 說明 |
|------|-------------|------|
| `.xlsx` | **試算表** | 直接渲染原始表格，最直觀 |
| `.csv` | **試算表** | SheetJS 支援 CSV，同 xlsx 處理 |
| `.pdf` | **資訊** | 摘要 + 標籤先行，需要再看完整內容 |
| `.docx` | **資訊** | 同 pdf |
| `.txt` | **完整內容** | 純文字直接閱讀 |
| `.md` | **完整內容** | Markdown 渲染（規劃中） |
| `.html` | **資訊** | 網頁通常依摘要決定是否深讀 |

---

## 五、各類型限制與已知問題

### 5.1 xlsx / csv
| 項目 | 現況 | 限制 |
|------|------|------|
| 試算表渲染 | SheetJS sheet_to_html | 無原始 Excel 格式（顏色/合併儲存格不保留） |
| Chunks 文字 | `Header: val | Header: val` | 非人類可讀，需透過試算表 tab |
| 大型 Excel | 無分頁 | 超過 ~5000 列可能造成 table 渲染緩慢 |
| CSV 編碼 | 純文字 fallback | BIG5 CSV 可能亂碼（需確認 CP950 fallback 覆蓋） |

### 5.2 PDF
| 項目 | 現況 | 限制 |
|------|------|------|
| 文字擷取 | pypdf extract_text | 掃描型 PDF（無 OCR）將無法取得文字 |
| 圖表 | 不支援 | 圖片內的文字無法索引 |
| 完整內容上限 | 200 chunks | 超長 PDF 僅顯示前 200 chunks |

### 5.3 DOCX
| 項目 | 現況 | 限制 |
|------|------|------|
| 段落解析 | 純文字合併 | 表格、圖片不解析 |
| 格式 | 無 | 粗體、標題層級不保留 |

---

## 六、後續規劃（優先度排序）

| 優先度 | 功能 | 說明 |
|--------|------|------|
| 🔴 高 | 試算表大型檔案虛擬捲動 | 超過 1000 列改用虛擬列表渲染 |
| 🔴 高 | PDF OCR 支援 | 整合 tesseract 或 Ollama vision 處理掃描型 PDF |
| 🟡 中 | Markdown 渲染 | 完整內容 tab 對 .md 套用 marked.js + DOMPurify |
| 🟡 中 | 完整內容分頁 | 超過 200 chunks 時提供「載入更多」按鈕 |
| 🟡 中 | xlsx 試算表搜尋 | 在試算表 tab 加入列篩選框 |
| 🟢 低 | DOCX 結構保留 | 解析標題層級、表格，以 HTML 呈現 |
| 🟢 低 | 圖片預覽 | 支援 .png / .jpg 直接預覽 |

---

## 七、前端 Token 認證規範

所有 API 呼叫**必須**透過 `frontend/src/api/index.js` 的 `docsApi.*` 方法，統一使用 `getHeaders()` → Pinia auth store 取 token。

**禁止**直接在元件內呼叫 `localStorage.getItem('token')`，避免：
- Token 過期未反映
- Pinia reactive 更新未同步
- 認證錯誤難以追蹤

```js
// ✅ 正確
const data = await docsApi.download(doc_id)

// ❌ 錯誤（已修正）
const token = localStorage.getItem('token')
const resp = await fetch(`/api/documents/${doc_id}/download`, {
  headers: { Authorization: `Bearer ${token}` }
})
```

---

## 八、相關檔案索引

| 檔案 | 說明 |
|------|------|
| `backend/routers/documents.py` | 所有文件 API 端點 |
| `backend/tasks/document_tasks.py` | Celery 攝取管線（解析 / 分塊 / 嵌入 / 寫庫） |
| `backend/services/storage.py` | MinIO 上傳 / 下載 / 刪除 |
| `backend/services/saga.py` | Saga 補償日誌 |
| `frontend/src/api/index.js` | 前端 API 封裝（docsApi.*） |
| `frontend/src/views/DocsView.vue` | 文件管理頁面（列表 + 側邊面板） |
| `frontend/public/xlsx.full.min.js` | SheetJS 靜態檔（避免 rollup 打包） |
