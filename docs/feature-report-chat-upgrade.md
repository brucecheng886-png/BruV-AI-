# Feature Report — 對話頁面完整升級

**日期**：2026-04-19  
**Commit**：`abc92cd`  
**執行者**：GitHub Copilot  
**狀態**：✅ Build 通過，已部署

---

## 1. 本次升級範圍

本次為 ChatView 的全面功能補完，對應規劃中的 P0 + P1 + P2 三個優先級。

| 優先級 | 功能 | 狀態 |
|--------|------|------|
| P0 | Markdown 渲染（marked v12 + highlight.js v11） | ✅ |
| P0 | 程式碼區塊語言標籤 + 複製按鈕 | ✅ |
| P0 | ■ 停止串流按鈕（AbortController） | ✅ |
| P1 | 思考動畫（等待第一個 token 時顯示） | ✅ |
| P1 | 訊息 hover 操作欄（複製 / 重試） | ✅ |
| P1 | 對話重命名（雙擊側欄 inline 編輯） | ✅ |
| P1 | 捲底 FAB（離開底部顯示 ↓ 按鈕） | ✅ |
| P2 | `/` slash 命令選單 | ✅ |
| P2 | `@` 文件引用（搜尋知識庫 + 附加至請求） | ✅ |
| P2 | 對話 / Agent 模式切換 | ✅ |
| P2 | Agent 任務輪詢 + 步驟顯示 | ✅ |

---

## 2. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `frontend/src/views/ChatView.vue` | 完整重寫 | 全部功能實作，~660 行 |
| `frontend/src/api/index.js` | 更新 | 新增 `conversationsApi.rename`、`agentApi`、`chatStream` 加入 signal + docIds |
| `frontend/package.json` | 更新 | 新增 `marked ^12.0.0`、`highlight.js ^11.11.1`、`dompurify ^3.2.4` |
| `frontend/package-lock.json` | 更新 | 對應 lock |
| `backend/routers/chat.py` | 更新 | 新增 `ConversationRenameIn` schema + `PATCH /api/chat/conversations/{id}` |

---

## 3. 關鍵技術決策

### 3.1 marked v12 renderer API
```js
// ✅ 正確（v12+）
marked.use({ renderer: { code({ text, lang }) { ... } } })

// ❌ 舊 API（v4 以前）
renderer.code = function(code, lang) { ... }
```

### 3.2 程式碼複製使用事件委派
訊息列表使用 `@click="onMsgAreaClick"` 統一處理 `.code-copy-btn` 點擊，避免在 `v-html` 產生的 DOM 上綁定事件失效問題。
程式碼明文以 `data-code="${encodeURIComponent(text)}"` 存在 DOM，複製時 `decodeURIComponent()` 解碼。

### 3.3 Stop 串流
```js
abortController = new AbortController()
fetch(url, { signal: abortController.signal })
// 中止：
abortController.abort()
// 捕捉：e.name === 'AbortError'
```

### 3.4 Agent 模式輪詢
`POST /api/agent/run` → 取得 `task_id` → 每 2 秒 `GET /api/agent/tasks/{id}`，最多 60 次（2 分鐘），`status: completed/failed` 時停止。

---

## 4. Build 產物

| 檔案 | 大小 | gzip |
|------|------|------|
| `ChatView-CPyNO9IF.js` | 113.80 kB | 36.53 kB |
| `ChatView-CVgRl5eN.css` | 11.25 kB | 2.75 kB |

---

## 5. 後續待辦（非本次範圍）

- [ ] highlight.js 按需載入（目前 8 個語言 bundle 進去，可再縮小）
- [ ] `@` mention 支援多個文件顯示 tag 方式確認
- [ ] Agent 步驟顯示可升級為 collapsible 摺疊面板
- [ ] 對話歷史支援搜尋 / 過濾
