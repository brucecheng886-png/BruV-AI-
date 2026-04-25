# Feature Report — 頁面 AI 助理系統完整實作

**日期**：2026-04-24  
**執行者**：GitHub Copilot  
**狀態**：✅ Build 通過，已部署（`[+] up 8/8`）

---

## 1. 功能摘要

本次實作以「每個頁面都有自己的 AI 助理」為核心目標，打通從 UI 工具列 → 模式選擇 → 上下文收集 → system prompt 組裝 → action 執行 → 結果回饋 的完整鏈路，並建立使用者可自訂的 AI Skill 管理系統。

---

## 2. 完成功能清單

| 功能 | 說明 | 狀態 |
|------|------|------|
| AgentPanel 工具列重設計 | `[+]`、`[Agent▾]`、`[Model▾]`、`[↑]` 四區段佈局，lucide 圖示 | ✅ |
| Agent / Ask / Plan 三種模式 | Bot / MessageCircle / ListChecks 圖示；後端 system prompt 附加行為說明 | ✅ |
| AI Skill 管理系統（DB） | `agent_skills` 資料表，6 筆頁面對應記錄，預設 user_prompt | ✅ |
| AI Skill 管理系統（API） | `GET /api/agent-skills/`、`PATCH /api/agent-skills/{page_key}` | ✅ |
| AI Skill 管理系統（設定頁 tab） | SettingsView「AI Skill」tab，6 張卡片含開關 + 自訂指令輸入 | ✅ |
| 頁面上下文自動注入 `buildPageContext()` | docs 頁：總數/KB 清單/處理中/失敗文件；ontology 頁：待審核數 | ✅ |
| `search_docs` action 閉環 | AI 輸出 action → 前端呼叫 `docsApi.list()` → 結果格式化 → 自動觸發下一輪 AI 回應 | ✅ |
| `_PAGE_AGENT_PROMPTS` 完整技術指令 | 每頁面含可執行操作、限制、回應格式說明（Markdown 格式） | ✅ |
| 對話記憶管理（自動摘要壓縮） | `_summarize_history()`；超過 20 筆時壓縮舊訊息，摘要存回 DB | ✅ |
| 各頁面預設 `user_prompt` | 6 個頁面助理各自有有意義的預設繁體中文指令 | ✅ |

---

## 3. 架構說明

### 3.1 兩層 Prompt 設計

```
system_prompt
├── _agent_prefix（後台技術指令）
│   ├── _PAGE_AGENT_PROMPTS[page]  ← 定義可執行操作、格式、限制
│   └── agent_skills.user_prompt  ← 使用者在設定頁自訂（可覆蓋）
├── kb_schema_section
├── extra_system（DB 全域設定）
├── _mode_suffix（agent / ask / plan 行為說明）
└── 參考資料（RAG chunks）
```

後台技術指令由開發者維護，使用者自訂指令通過設定頁 UI 覆蓋，互不干擾。

### 3.2 Action 執行機制

AI 在回應末尾輸出單行 JSON 標記：
```
__action__:{"type":"search_docs","query":"關鍵字","include_status":true}
```

前端 `handlePageAction()` 以 regex 擷取所有 `__action__` 標記：
1. 從顯示文字移除標記（保持回應乾淨）
2. 依 `type` 執行對應 API 操作
3. 結果以 `actionResults[]` 顯示在訊息下方
4. 廣播 `CustomEvent('ai-action', ...)` 通知頁面元件刷新

`search_docs` 特殊處理：搜尋結果格式化後自動觸發下一輪 `runChat(followUp)`，形成閉環。

### 3.3 三種 Agent 定位

| Agent 類型 | 觸發條件 | 特性 |
|---|---|---|
| 頁面助理（`page_agent:xxx`） | AgentPanel page tab | 注入頁面角色 + 上下文，可執行頁面操作 |
| 全域助理（`global`） | AgentPanel global tab | 輪詢 Agent task，支援跨服務操作 |
| 知識庫助理（`kb_agent`） | AgentPanel kb tab | 限定在選取的知識庫 scope |

---

## 4. 對話記憶管理

```
每次 _rag_stream：
  ├── 查詢 conversations.summary（現有摘要）
  ├── 查詢 total_msg_count
  ├── 取最近 RECENT_ROUNDS * 2 = 12 筆完整對話
  └── 若 total_msg_count > 20 且無摘要：
        取舊訊息 → _summarize_history() → 存回 conversations.summary
        
messages_payload 結構：
  [system]
  [assistant: "以下是先前對話的摘要：{summary}"]（若有）
  [最近 6 輪完整對話]
  [user: 當前問題]
```

---

## 5. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `backend/routers/chat.py` | 更新 | `_PAGE_AGENT_PROMPTS` 完整版、`_summarize_history()`、step 5 記憶邏輯、`ConversationOut` 加 `summary`、`_history_rounds` 改用 RECENT_ROUNDS |
| `backend/routers/agent_skills.py` | 新建 | `GET /` `GET /{page_key}` `PATCH /{page_key}` |
| `backend/main.py` | 更新 | 掛載 `/api/agent-skills` 路由 |
| `backend/models.py` | 更新 | `Conversation` 加 `summary`、`summarized_up_to`、`summary_updated_at`；兩側 relationship 加 `foreign_keys` |
| `frontend/src/components/AgentPanel.vue` | 更新 | 工具列重設計、三模式 dropdown、`buildPageContext()`、`search_docs` 閉環 |
| `frontend/src/views/ChatView.vue` | 更新 | 三模式 dropdown、`search_docs` 閉環 |
| `frontend/src/views/SettingsView.vue` | 更新 | AI Skill tab（template + script + CSS） |
| `frontend/src/api/index.js` | 更新 | `chatStream` / `chatStreamWithFile` 加 `mode` 參數、新增 `agentSkillsApi` |
| `frontend/src/design/icon-spec.md` | 新建 | lucide 圖示規格文件 |
| DB migration | 執行 | `agent_skills` 建表、`conversations` 加三欄位 |

---

## 6. 踩坑記錄

### 6.1 SQLAlchemy `AmbiguousForeignKeysError`

**問題**：`Conversation.summarized_up_to` 是 FK → `messages.id`，而 `Message.conv_id` 也是 FK → `conversations.id`，兩資料表之間存在雙向 FK 路徑，SQLAlchemy 無法自動判斷 relationship 的 join key。

**錯誤訊息**：
```
sqlalchemy.exc.AmbiguousForeignKeysError: Could not determine join condition 
between parent/child tables on relationship Message.conversation
```

**修正**：在 `Conversation.messages` 和 `Message.conversation` 兩側 relationship 都明確指定 `foreign_keys="Message.conv_id"`。

---

### 6.2 `buildPageContext()` 初版缺少處理中文件詳細資訊

**問題**：初版只用 `docsApi.count({ status: 'processing' })` 取數量，AI 無法得知具體是哪些文件在處理。

**修正**：改成並發呼叫 `docsApi.list({ status: 'processing', limit: 10 })` 和 `docsApi.list({ status: 'error', limit: 10 })`，注入每筆文件的標題、chunk 數或錯誤訊息。

---

## 7. 後續待辦

| 項目 | 優先級 | 說明 |
|------|--------|------|
| YouTube yt-dlp 字幕擷取 | P1 | 讓使用者可以把 YouTube 影片內容納入知識庫 |
| Facebook 公開貼文爬取 | P2 | 公開粉絲頁貼文解析與索引 |
| Plan 模式步驟確認 UI | P1 | 前端顯示 AI 規劃步驟，使用者按「確認」才執行 |
| 對話記憶摘要觸發測試驗收 | P1 | 建立 20 筆以上訊息的對話，確認摘要正確寫入 DB |
| `search_convs` action 閉環 | P2 | 對話管理頁搜尋結果回傳 AI（類似 search_docs） |
| AgentPanel stores/auth.js 動態 import 警告 | Low | Vite 警告：auth.js 同時被靜態與動態 import |
