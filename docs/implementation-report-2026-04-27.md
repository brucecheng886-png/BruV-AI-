# 實作報告 — 2026-04-27

**執行者**：GitHub Copilot  
**報告日期**：2026-04-27  
**涵蓋期間**：2026-04-25 ～ 2026-04-27  
**狀態**：✅ 全部實作完成並通過驗收（24/24 PASS）

---

## 一、Prompt 修復（AI 拒答 Regression）

### 問題背景

Phase E + C + D 批次部署後，使用者對任何問題提問（含「你好」「什麼是 RAG」「台灣最高的山」），AI 一律回覆：
> 「抱歉，我無法執行任何操作或回應指令。」

所有 `agent_type`（`null`、`page_agent:*`、`kb_agent`、`global_agent`）均受影響。

### 根本原因

三層 prompt 限制同時疊加，LLM 把「回答一般問題」也判定為「未授權操作」：

1. `RAG_SYSTEM_PROMPT` 包含強制拒答條款（「無相關內容時必須回覆抱歉無法回答」）
2. `file_context` priming 在每一輪都注入「先確認使用者意圖」的限制語
3. `_COMMON_FOOTER` 的「不執行未授權操作」條款被 LLM 過度套用

### 修復清單

| 檔案 | 修復重點 |
|------|---------|
| `backend/prompts/rag_system.py` | 拒答條款軟化：無相關內容時改為「可基於通用知識回答並加註非來自知識庫」；移除「禁止用我認為」改為「避免過度主觀推測」 |
| `backend/routers/chat.py` | `file_context` priming 拆成靜態標註 vs 動態 priming；priming 僅在第一輪（`_msg_count == 0`）注入 |
| `backend/prompts/page_agents.py` | 新增 `_COMMON_HEADER`：「對於一般知識性問題，請直接正常回答。只有在使用者明確要求執行頁面操作時才遵守操作清單。」；移除 `_COMMON_FOOTER` 三條過度限制 |

### Before / After 對比

**Before（`_COMMON_FOOTER` 舊版）**：
```
不執行未經明確授權的操作
不操作其他頁面功能
預設不超過 200 字
```

**After（`_COMMON_HEADER` 新版）**：
```
對於一般知識性問題，請直接正常回答。
只有在使用者明確要求執行頁面操作時，才遵守以下操作清單。
```

### 驗證結果

| 案例 | query | agent_type | 結果 |
|------|-------|-----------|------|
| 一般知識 | 什麼是 RAG 檢索增強生成？ | null | ✅ 正常回答 |
| 自我介紹 | 你好，你可以幫我做什麼？ | page_agent:docs | ✅ 正常回答 |
| 地理知識 | 台灣最高的山是哪座？ | null | ✅ 玉山，3952m |

---

## 二、LLM 服務錯誤修復

### 問題背景

使用者在 AgentPanel 選擇雲端模型 `claude-sonnet-4-6` 發送訊息時，SSE 以錯誤結束：
```
data: {"type":"error","text":"LLM 服務暫時無法使用"}
```
後端 log：
```
LLM stream error: Client error '404 Not Found' for url 'https://api.openai.com/v1/chat/completions'
```

### 根本原因

**破口 A — 資料汙染**：`llm_models` 表中 `claude-sonnet-4-6` 的 `base_url` 被誤填為 `http://ollama:11434`（內部 ollama 服務位址），對 Anthropic provider 完全無效。

**破口 B — `llm_resolver.py` 缺少嚴格驗證**：DB 查不到 model 時，`detect_provider_from_model` 以模型名稱猜測 provider（`claude` → `anthropic`），`apply_model_runtime` 只覆寫非 None 欄位，api_key 為 None 時仍執行 cloud provider 呼叫，最終打到錯誤 URL。

### 修復清單

| 檔案 | 修復重點 |
|------|---------|
| DB `llm_models` | `UPDATE llm_models SET base_url = NULL WHERE name = 'claude-sonnet-4-6'`；讓 llm_client 使用 Anthropic 預設 URL |
| `backend/services/llm_resolver.py` | 嚴格模式：cloud provider（openai / anthropic / gemini / azure / openrouter）但 api_key 為空 → `raise ValueError("模型 {name} 缺少 API Key，請至設定頁補齊")` |
| `backend/routers/chat.py` | `resolve_model_runtime` 呼叫處包 `try/except ValueError` → SSE error event；`HTTPStatusError` 訊息改為「LLM 服務錯誤（{provider} HTTP {status}）：{response_preview}」 |
| `backend/routers/documents.py` | 智慧匯入端點的 `resolve_model_runtime` 呼叫包 `try/except ValueError` → `HTTPException(422)` |

### Before / After 對比

**`llm_resolver.py` Before**：
```python
provider = fallback_provider or detect_provider_from_model(model_name)
# DB 查不到 → 回 {provider: "openai", api_key: None}，仍繼續執行
```

**`llm_resolver.py` After**：
```python
provider = fallback_provider or detect_provider_from_model(model_name)
if provider in CLOUD_PROVIDERS and not api_key:
    raise ValueError(f"模型 {name} 缺少 API Key，請至設定頁補齊")
```

**`chat.py` 錯誤訊息 Before**：
```
LLM 服務暫時無法使用
```

**`chat.py` 錯誤訊息 After**：
```
LLM 服務錯誤（anthropic HTTP 401）：{"error":{"type":"authentication_error"...}}
```

### 驗收結果

```
端點                                           狀態   耗時(ms)  結果
/api/chat/stream [page_agent:docs]            200   3001.0   PASS
/api/chat/stream [page_agent:ontology]        200   3810.6   PASS
/api/chat/stream [kb_agent]                   200   3212.9   PASS
/api/chat/stream [global_agent]               200   5151.1   PASS
總計：10  通過：10  通過率：100.0%
```

---

## 三、AnythingLLM 借鑒功能實作

本批次參考 AnythingLLM 的設計理念，實作以下 8 個功能強化：

### 3.1 Sources 來源補齊顯示

**功能**：RAG 對話後在訊息下方顯示引用來源卡片，含文件標題、分數、snippet。  
**修改檔案**：`backend/routers/chat.py`、`frontend/src/views/ChatView.vue`  
**Before**：sources 僅在 SSE event 中出現，前端只顯示分數無詳細資訊  
**After**：sources 卡片顯示文件標題、相似度分數（百分比）、前 150 字 snippet，支援點擊查看原文

### 3.2 Chunk 跳轉（文件定位）

**功能**：點擊 sources 卡片可跳轉至對應文件詳細頁，並自動捲動到該 chunk 位置。  
**修改檔案**：`frontend/src/views/ChatView.vue`、`frontend/src/views/DocsView.vue`  
**Before**：Sources 卡片無跳轉功能  
**After**：Sources 卡片有「查看原文」連結，透過 `router.push` + `highlight_chunk` query param 定位

### 3.3 `@agent` 指令（ChatView）

**功能**：在 ChatView 輸入框輸入 `@` 可召喚 agent 選擇選單（page_agent / kb_agent / global_agent），選取後自動帶入 agent_type 參數。  
**修改檔案**：`frontend/src/views/ChatView.vue`  
**Before**：agent_type 只能透過 UI 按鈕切換  
**After**：`@` 觸發浮動選單，支援鍵盤選取

### 3.4 AgentPanel `@mention` 文件引用

**功能**：AgentPanel 輸入框支援 `@` mention 搜尋知識庫文件，選取後附加至本輪請求 `docIds` 欄位。  
**修改檔案**：`frontend/src/components/AgentPanel.vue`、`frontend/src/api/index.js`  
**Before**：AgentPanel 無法引用特定文件  
**After**：`@` 觸發文件搜尋下拉，選取後顯示文件 badge，對話請求攜帶 `docIds`

### 3.5 MCP 知識庫工具橋接

**功能**：建立 MCP Server 工具 — 提供 `list_kbs`、`list_docs_in_kb`、`search_kb` 三個工具函式，供外部 MCP Client 呼叫。  
**修改檔案**：`backend/mcp_server.py`  
**Before**：MCP server 僅有空殼結構  
**After**：三個工具函式完整實作，資料來自 PostgreSQL + Qdrant

### 3.6 KB Workspace 深化

**功能**：知識庫頁面新增「工作區模式」，進入 KB 後自動將對話範圍限定在該 KB，導航欄顯示工作區名稱。  
**修改檔案**：`frontend/src/views/DocsView.vue`、`frontend/src/views/ChatView.vue`  
**Before**：對話總是全域搜尋，無法限定 KB 範圍  
**After**：KB 詳細頁有「在此 KB 中對話」按鈕，點擊後 ChatView 自動帶入 `kb_scope_id`

### 3.7 Agent Skill Store 使用者自訂

**功能**：設定頁新增「AI Skill」tab，6 張頁面助理卡片，每張卡片支援開關（啟用/停用）與自訂 user_prompt 覆蓋。  
**修改檔案**：`backend/routers/agent_skills.py`、`frontend/src/views/SettingsView.vue`  
**Before**：page_agent prompt 為固定技術指令，使用者無法調整  
**After**：使用者可在 UI 上覆蓋 user_prompt，支援每個頁面獨立設定

### 3.8 Prompt Template 引擎

**功能**：`backend/prompts/` 完整模組化（7 個 prompt 檔），內建 12 個使用者面向 Prompt 模板（writing×3 / translate×1 / analysis×3 / extract×2 / code×2 / qa×1），ChatView 新增 📋 模板選擇器。  
**修改檔案**：`backend/prompts/rag_system.py`、`backend/prompts/page_agents.py`、`backend/routers/prompt_engine.py`、`frontend/src/views/ChatView.vue`  
**Before**：RAG system prompt 硬編碼在 `chat.py` 中  
**After**：獨立 `prompts/` 模組，seed 腳本預填 17 個模板（5 舊 + 12 新），前端模板選擇器支援一鍵套用

---

## 四、智慧文件匯入 Agent

### 功能摘要

新增 `/api/documents/smart-import` 端點與前端預覽視窗，使用者貼入 URL 後後端自動以 Playwright 抓取內容、LLM 分析摘要、建議知識庫歸屬，前端顯示預覽後一鍵確認匯入。

### 修改檔案

| 檔案 | 說明 |
|------|------|
| `backend/routers/documents.py` | 新增 `POST /api/documents/smart-import/preview` 端點（Playwright 抓取 + LLM 摘要） |
| `backend/routers/documents.py` | 新增 `POST /api/documents/smart-import/confirm` 端點（確認後正式建立文件記錄 + 觸發 Celery 索引任務） |
| `backend/services/llm_resolver.py` | smart-import LLM 呼叫點包 `try/except ValueError` 防呆 |
| `frontend/src/api/index.js` | 新增 `docsApi.smartImportPreview(url)` 和 `docsApi.smartImportConfirm(data)` |
| `frontend/src/views/DocsView.vue` | 新增 Smart Import 按鈕（`Import` 圖示）和預覽 Dialog（標題、摘要、建議 KB、標籤預覽） |

### Before / After 對比

**Before**：使用者只能上傳本機檔案，無法直接匯入網頁 URL

**After**：
1. 點擊「🔗 智慧匯入」→ 輸入 URL
2. 後端 Playwright 抓取網頁 → LLM 生成摘要、提取標題、建議 KB
3. 前端顯示預覽視窗（含摘要、建議標籤）
4. 使用者確認 → 觸發正式索引流程（Celery + Qdrant + Neo4j）

---

## 五、對話效能改善

### 5.1 Batch Action 執行

**功能**：AI 在單輪對話中可輸出多個 `__action__` 標記，前端依序全部執行（而非僅處理第一個）。  
**修改檔案**：`frontend/src/components/AgentPanel.vue`

**Before**：
```js
const match = response.match(/__action__:({.*?})\n/)
if (match) executeAction(JSON.parse(match[1]))
```

**After**：
```js
const matches = [...response.matchAll(/__action__:({.*?})\n/g)]
for (const m of matches) {
  await executeAction(JSON.parse(m[1]))
}
```

### 5.2 後端 Execute-Action 端點

**功能**：新增 `POST /api/chat/execute-action` 端點，讓前端直接觸發後端工具操作（list_kbs、list_all_docs、create_kb、delete_kb 等），回傳結構化結果。  
**修改檔案**：`backend/routers/chat.py`

**Before**：action 完全由前端執行（`docsApi.list()`、`kbApi.list()` 等），後端無統一入口

**After**：
```python
@router.post("/execute-action")
async def execute_action(req: ExecuteActionIn, ...):
    action = {"type": req.action_type, **req.params}
    result = await _execute_action_backend(action, db)
    return {"result": result}
```

### 5.3 Function Calling（FC）路徑診斷與確認

**功能**：驗證 claude-sonnet-4-6 + global_agent 的 Function Calling 路徑完全正常。  
**修改檔案**：`backend/routers/chat.py`（確認邏輯，無結構修改）

**FC 路徑條件**：
```python
FC_PROVIDERS = frozenset({"openai", "anthropic", "groq"})
_use_fc = (
    _eff_provider in FC_PROVIDERS
    and bool(_page_for_skill)
    and mode == "agent"
    and bool(_get_tools(_page_for_skill))
)
```

**驗證結果**：claude + global_agent → `_use_fc=True` → `llm_with_tools` → `action_result` SSE event 正常回傳

---

## 六、selectedModel 跨元件同步修復

### 問題描述

`ChatView.vue` 和 `AgentPanel.vue` 各自維護獨立的 `selectedModel` ref，導致在某個元件切換模型後，另一個元件的模型選擇不同步，實際 API 呼叫使用不一致的模型。

### 解決方案（Method B：提升至 Pinia chat store）

**修改檔案清單**：

| 檔案 | 修改內容 |
|------|---------|
| `frontend/src/stores/chat.js` | 新增 `selectedModel` ref（初始值讀 localStorage）和 `setSelectedModel()` action，回傳值中加入兩者 |
| `frontend/src/views/ChatView.vue` | 移除本地 `selectedModel` ref，改用 `storeToRefs(chatStore)` 取 `selectedModel`；`selectModel()` 改為呼叫 `chatStore.setSelectedModel()` |
| `frontend/src/components/AgentPanel.vue` | 移除本地 `selectedModel` ref 與 `onMounted` 中的初始化；改用 `storeToRefs(chatStore)` 取 `selectedModel`；template 點擊改為 `chatStore.setSelectedModel(m)` |

### Before / After 對比

**Before（各自獨立）**：
```js
// ChatView.vue
const selectedModel = ref(localStorage.getItem('last-selected-model') || '')

// AgentPanel.vue
const selectedModel = ref('')
onMounted(() => { selectedModel.value = availableModels.value[0] })
```

**After（共用 Pinia store）**：
```js
// stores/chat.js
const selectedModel = ref(localStorage.getItem('last-selected-model') || '')
function setSelectedModel(model) {
  selectedModel.value = model
  try { localStorage.setItem('last-selected-model', model) } catch {}
}

// ChatView.vue + AgentPanel.vue（兩者相同）
const chatStore = useChatStore()
const { selectedModel } = storeToRefs(chatStore)
```

### 附帶修復：FAB 不顯示（ESM import 順序）

在實作過程中發現 `AgentPanel.vue` 的 `const chatStore = useChatStore()` 被插入在兩個 `import` 陳述句之間，違反 ESM 規範，導致 `setup()` 在執行期崩潰，FAB 完全不渲染。

**修復**：將所有 `import` 集中至 `<script setup>` 最頂部，`const chatStore = useChatStore()` 移到最後一個 `import` 之後。

---

## 七、其他改善

### 7.1 右鍵選單（標籤管理）

**功能**：DocsView 側欄標籤列表每個 tag chip 新增 `el-dropdown` 右鍵選單，提供兩種刪除操作：
- 「從所有文件移除」：僅清除中介表關聯，tag 保留
- 「徹底刪除」：移除 tag 實體及所有關聯，顯示「將影響 N 篇文件」確認提示

**修改檔案**：`frontend/src/views/DocsView.vue`、`backend/routers/tags.py`

### 7.2 global_agent Prompt 改善

**功能**：`global_agent` system prompt 增加繁體中文回應偏好與操作邊界說明，減少無效 action 輸出。  
**修改檔案**：`backend/prompts/page_agents.py`（`_GLOBAL_AGENT_PROMPT` 段落）

**Before**：global_agent 使用通用 RAG prompt，常輸出英文或執行無效 action  
**After**：明確指示「以繁體中文回應」「僅在使用者明確要求時才輸出 action」

### 7.3 `delete_kb` Action 支援

**功能**：`execute-action` 端點新增 `delete_kb` 操作類型，AI 可在使用者要求時刪除指定知識庫。  
**修改檔案**：`backend/routers/chat.py`（`_execute_action_backend` 函式）

**Before**：execute-action 僅支援 list_kbs、list_all_docs、create_kb  
**After**：新增 `delete_kb` handler：
```python
elif action["type"] == "delete_kb":
    kb_id = action.get("kb_id")
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()
    return f"已刪除知識庫 {kb_id}"
```

### 7.4 Action 結果收合 UI

**功能**：AgentPanel 的 `action_result` 顯示區塊改為可收合面板（預設展開，點擊標題收合），避免多個 action 結果撐開對話畫面。  
**修改檔案**：`frontend/src/components/AgentPanel.vue`

**Before**：action 結果以固定高度 `el-card` 顯示，無法收合  
**After**：改用 `el-collapse` 包裝，標題顯示 action 類型，點擊切換展開/收合狀態

---

## 八、修改檔案總覽

| 檔案 | 涉及區塊 |
|------|---------|
| `backend/prompts/rag_system.py` | 一 |
| `backend/prompts/page_agents.py` | 一、七 |
| `backend/routers/chat.py` | 一、二、五 |
| `backend/routers/documents.py` | 二、四 |
| `backend/services/llm_resolver.py` | 二 |
| `backend/mcp_server.py` | 三 |
| `backend/routers/agent_skills.py` | 三 |
| `backend/routers/prompt_engine.py` | 三 |
| `backend/routers/tags.py` | 七 |
| `backend/scripts/acceptance_test.py` | 驗收修復 |
| `frontend/src/stores/chat.js` | 六 |
| `frontend/src/views/ChatView.vue` | 三、六 |
| `frontend/src/views/DocsView.vue` | 三、四、七 |
| `frontend/src/components/AgentPanel.vue` | 三、五、六、七 |
| `frontend/src/api/index.js` | 三、四、五 |
| `frontend/src/views/SettingsView.vue` | 三 |

---

## 九、驗收摘要

| 驗證項目 | 方式 | 結果 |
|---------|------|------|
| 後端 API 健康檢查 | `api_health_check.py` 10/10 | ✅ 100% |
| 完整驗收測試 T01-T24 | `acceptance_test.py` | ✅ 24/24 PASS |
| 前端 Build | `npm run build` | ✅ Exit 0 |
| Docker Deploy | `docker compose up -d` | ✅ 15/15 容器 Up |
| FC Path 驗證 | claude + global_agent SSE | ✅ action_result 正常 |
| selectedModel 共用 | ChatView ↔ AgentPanel | ✅ localStorage 持久化 |
