# 文件管理頁 UI 重設計規劃

**建立日期**：2026-04-18  
**狀態**：✅ 已實作（DocsView.vue v2）  
**相關檔案**：`frontend/src/views/DocsView.vue`、`frontend/src/api/index.js`

---

## 1. 設計目標

| 目標 | 說明 |
|------|------|
| 知識庫分類 | 文件可歸屬於「知識庫」，支援多個 KB 獨立管理 |
| 多模式檢視 | Grid 卡片 / Table 表格 / Node 節點圖，一鍵切換 |
| 右側詳情面板 | 點擊文件滑出詳情，不離開頁面（Notion 風格） |
| AI 語意搜尋 | 跨 KB 或指定 KB 的語意搜尋，顯示相似度分數 |
| 非破壞性操作 | 刪除 KB 時文件不消失，只解除歸屬關係 |

---

## 2. 版面結構

```
┌──────────────────────────────────────────────────────────────────┐
│  .docs-root  (flex row, height: 100vh)                           │
│                                                                  │
│  ┌──────────┐  ┌────────────────────────────┐  ┌─────────────┐  │
│  │ .kb-     │  │ .docs-main                 │  │ .detail-    │  │
│  │  sidebar │  │                            │  │  panel      │  │
│  │ 220px    │  │  toolbar (上傳/搜尋/切換)   │  │ 380px       │  │
│  │          │  │  ─────────────────────     │  │ fixed right │  │
│  │ KB list  │  │  grid | table | node       │  │ 滑入動畫    │  │
│  │ + CRUD   │  │  ─────────────────────     │  │             │  │
│  │          │  │  pagination                │  │ 3 tabs      │  │
│  └──────────┘  └────────────────────────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 左側 KB Sidebar（220px）

| 元素 | 功能 |
|------|------|
| `全部文件` 項目 | `selectedKbId = null`，顯示全部 |
| KB 清單項目 | 顯示 icon、名稱、doc_count badge |
| Hover 選單 | 編輯 / 刪除（`el-dropdown`） |
| 底部按鈕 | 新建知識庫 |

### 2.2 主區域 Toolbar

| 元素 | 說明 |
|------|------|
| Breadcrumb | 文件管理 / KB 名稱 |
| AI 搜尋輸入 | Enter 或按鈕觸發，clearable |
| 上傳按鈕 | `el-upload` custom request，支援指定 KB |
| 檢視切換 | Grid / Table / Node（`el-button-group`） |

### 2.3 主區內容（三種檢視）

**Grid**：`auto-fill minmax(175px, 1fr)`，每張卡片含縮略色塊 + 狀態燈號  
**Table**：`el-table`，row-click 開啟詳情面板  
**Node**：Cytoscape.js（動態 `import()`），KB 為 compound parent node，doc 為 child node

### 2.4 右側 Detail Panel（380px, fixed）

| Tab | 內容 |
|-----|------|
| 資訊 | 所屬 KB（含移動按鈕）、檔案類型、Chunks 數、建立時間、錯誤訊息 |
| Chunks | 分頁列表，每筆顯示 index、頁碼、字元數、內容預覽 |
| 完整內容 | 所有 chunks concat，`<pre>` 等寬字體顯示 |

---

## 3. 狀態管理（`<script setup>` refs）

```
kbs[]               知識庫清單
selectedKbId        當前選中 KB（null = 全部）
docs[]              文件清單（依 KB 過濾）
page / total        分頁狀態
viewMode            'grid' | 'table' | 'node'
panelDoc            當前展開的文件（null = 面板收起）
panelTab            'info' | 'chunks' | 'content'
chunks[] / chunksTotal / chunkPage
fullContent         完整內容字串（chunks join）
searchQuery / searchMode / searchResults / lastQuery
uploading / uploadError / uploadSuccess
showKbDialog / editKb / kbForm / kbSaving
showMoveDialog / moveTargetDoc / moveTargetKbId / moving
cyContainer / cyInstance / cyLoading
```

---

## 4. API 對應

### Frontend → `api/index.js`

| 函式 | HTTP | 說明 |
|------|------|------|
| `docsApi.list(params)` | `GET /api/documents?kb_id=&limit=&offset=` | 取文件清單 |
| `docsApi.upload(file, kbId)` | `POST /api/documents/upload` + FormData | 上傳並指定 KB |
| `docsApi.delete(id)` | `DELETE /api/documents/{id}` | 刪除文件 |
| `docsApi.getChunks(id, params)` | `GET /api/documents/{id}/chunks` | 取分塊內容 |
| `docsApi.moveToKb(docId, kbId)` | `PATCH /api/documents/{docId}/kb` | 移動至知識庫 |
| `docsApi.aiSearch(query, kbId, topK)` | `POST /api/documents/search` | AI 語意搜尋 |
| `kbApi.list()` | `GET /api/knowledge-bases` | 取 KB 清單 |
| `kbApi.create(body)` | `POST /api/knowledge-bases` | 建立 KB |
| `kbApi.update(id, body)` | `PUT /api/knowledge-bases/{id}` | 更新 KB |
| `kbApi.delete(id)` | `DELETE /api/knowledge-bases/{id}` | 刪除 KB |

### Backend（已實作）

| 路由檔 | 功能 |
|--------|------|
| `routers/knowledge_bases.py` | KB CRUD，回傳 `doc_count` |
| `routers/documents.py` | `kb_id` 過濾、`PATCH /kb`、`POST /search`（Qdrant 語意） |
| `models.py` | `KnowledgeBase` 表、`Document.knowledge_base_id` FK |

---

## 5. 設計決策記錄

| 決策 | 理由 |
|------|------|
| 刪除 KB 不刪文件 | 文件是核心資料，KB 只是分類標籤 |
| Cytoscape 動態 import | 減少初始 bundle 大小（cytoscape.esm ~440KB gzip 141KB） |
| Panel 用 fixed + transition | 不影響主區 layout，動畫流暢 |
| AI 搜尋覆蓋整個主區 | 搜尋結果與一般文件清單互斥，避免混淆 |
| `&#x1F4CB;` 代替直接寫 emoji | 避免 PowerShell 寫檔時 Unicode 損毀 |
| 分頁 PAGE_SIZE=24 | Grid 4 欄時整行填滿，視覺對稱 |

---

## 6. 色彩 Design Token

```css
--c-bg:         #f8fafc   /* 頁面底色 */
--c-surface:    #ffffff   /* 卡片/面板 */
--c-border:     #e2e8f0
--c-text:       #1e293b
--c-text-sub:   #64748b
--c-primary:    #2563eb
--c-sidebar-bg: #f1f5f9
```

檔案類型色彩：

| 類型 | 顏色 |
|------|------|
| pdf  | `#ef4444` |
| docx | `#2563eb` |
| xlsx / csv | `#16a34a` |
| md   | `#7c3aed` |
| html | `#ea580c` |
| txt  | `#64748b` |
| 其他 | `#94a3b8` |

---

## 7. 已知限制 / 未來優化方向

| 項目 | 說明 |
|------|------|
| 拖曳移動 | 目前用 Dialog 移動，未來可改為拖曳至 KB sidebar |
| 批次操作 | 多選文件批次刪除 / 移動 |
| KB 排序 | 目前依建立順序，未來可拖曳排序 |
| 文件預覽 | PDF/圖片的即時預覽（目前只有文字 chunks） |
| 全文搜尋 | 目前是 AI 語意搜尋，可加入精確全文搜尋 |
| Node 圖效能 | 文件 >500 時 cose layout 較慢，可改 dagre |
