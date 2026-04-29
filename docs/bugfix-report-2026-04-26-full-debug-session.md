# 完整除錯紀錄：2026-04-26 Full Debug Session

- 日期：2026-04-26（接續至 2026-04-27 收尾）
- 背景：Phase E + C + D 批次實作完成後的兩起連續事故
- 涉及範圍：Backend prompts / chat router / LLM resolver / DB（llm_models）/ AgentPanel 串流體驗
- 結論狀態：兩起事故皆已修復並通過健康檢查（10/10 PASS）

---

## 第一部分：AI 拒答 Regression

### 1.1 問題描述

部署 Phase E（Reflection / regenerate）+ C（Prompt Template）+ D（Auto-match）後，
使用者於 AgentPanel / ChatView 對任何問題提問，AI 一律回覆：

> 「抱歉，我無法執行任何操作或回應指令。」

包含「什麼是 RAG？」「台灣最高的山？」「你好」等與頁面操作完全無關的問題。

### 1.2 觸發條件

- 條件 A：Phase E + C + D 部署後
- 條件 B：呼叫 `/api/chat/stream` 任何 `agent_type`（含 `null`、`page_agent:*`、`kb_agent`、`global_agent`）
- 條件 C：與是否帶 doc_ids、kb_id 無關 → 一律拒答

### 1.3 根本原因

**三個 prompt 同時疊加，限制力道過強**：

1. **`backend/prompts/rag_system.py`** 中 `RAG_SYSTEM_PROMPT` 包含
   「無相關內容時必須回覆『抱歉，我無法回答』」「禁止用『我認為』填補缺漏」等強制拒答條款
2. **`backend/routers/chat.py`** 的 `file_context` 在每一輪都注入 priming：
   「在進行任何操作之前，請先確認使用者意圖…」→ 在無檔案脈絡下也被觸發
3. **`backend/prompts/page_agents.py`** 的 `_COMMON_FOOTER` 寫了
   「不執行未經明確授權的操作」「不操作其他頁面功能」「預設不超過 200 字」
   → page_agent 模式下 LLM 把「回答一般問題」也判定為「未授權操作」

三層限制疊加 → LLM 認為任何回應都違反規則 → 統一拒答。

### 1.4 修復方式

| 檔案 | 修復重點 |
|---|---|
| [backend/prompts/rag_system.py](backend/prompts/rag_system.py) | 拒答條款軟化：無相關內容時改為「可基於通用知識回答，但加註『（此回答非來自知識庫，建議查證）』」；移除「禁止用『我認為』填補缺漏」改為「避免過度主觀的推測」；保留「不得編造參考資料中沒有的事實/數字/引文/URL」 |
| [backend/routers/chat.py](backend/routers/chat.py) | `file_context` 拆成兩段：靜態 fname 標註 vs `_file_priming`；priming 僅在 `_msg_count == 0`（對話第一輪）才注入 |
| [backend/prompts/page_agents.py](backend/prompts/page_agents.py) | 新增 `_COMMON_HEADER`：「對於一般知識性問題，請直接正常回答。只有在使用者明確要求執行頁面操作時，才遵守以下操作清單。」`_COMMON_FOOTER` 移除「不執行未授權操作」「不操作其他頁面功能」「預設不超過 200 字」三條，僅保留簡潔、拒絕注入、不編造 ID |

### 1.5 測試驗證

模擬 AgentPanel 三種典型對話：

| 案例 | query | agent_type | 結果 |
|---|---|---|---|
| TEST1 | 什麼是 RAG 檢索增強生成？請簡單解釋 | null | ✅ 正常引用 [#1] 回答 |
| TEST2 | 你好，你可以幫我做什麼？ | page_agent:docs | ✅ 正常自我介紹 |
| TEST3 | 台灣最高的山是哪座？ | null | ✅ 「玉山，3,952 公尺」 |

---

## 第二部分：LLM 服務暫時無法使用

### 2.1 問題描述

第一部分修復後，使用者於 AgentPanel **選擇雲端模型** `claude-sonnet-4-6` 發送訊息時，
SSE 結束於：

```
data: {"type":"error","text":"LLM 服務暫時無法使用"}
```

Backend log：

```
LLM stream error: Client error '404 Not Found' for url 'https://api.openai.com/v1/chat/completions'
```

弔詭點：選 `claude-sonnet-4-6` 卻打 OpenAI 端點。

### 2.2 觸發條件

- 條件 A：AgentPanel 從 cloudModels（`wikiApi.list()` 結果）挑選 provider !== `ollama` 的模型
- 條件 B：該模型在 `llm_models` 表中設定不一致（base_url / api_key 任一錯誤）
- 條件 C：`detect_provider_from_model` 將模型名稱推測為 cloud provider

### 2.3 根本原因（兩個破口）

#### 破口 1：`llm_models` 資料汙染

| name | provider | base_url（錯誤） |
|---|---|---|
| claude-sonnet-4-6 | anthropic | `http://ollama:11434` |

`base_url` 被誤填為內部 ollama 服務位址，對 Anthropic provider 完全無效。

#### 破口 2：`llm_resolver.py` 缺少嚴格驗證

[backend/services/llm_resolver.py](backend/services/llm_resolver.py) 原始流程：

```python
provider = fallback_provider or detect_provider_from_model(model_name)
# DB 查不到 → 回 {provider: "openai", api_key: None, ...}
# apply_model_runtime 只覆寫非 None 欄位
# → runtime_config.provider = "openai", api_key 仍為空
```

llm_client 看到 `provider="openai"` → 走 OpenAI 預設 URL `https://api.openai.com/v1/chat/completions` → 因 model 名稱不存在於 OpenAI 而回 404。

### 2.4 修復方式

| # | 檔案 | 修復重點 |
|---|---|---|
| 1 | DB（`llm_models`） | `UPDATE llm_models SET base_url = NULL WHERE name = 'claude-sonnet-4-6';` 讓 llm_client 走 Anthropic 預設 URL |
| 2 | [backend/services/llm_resolver.py](backend/services/llm_resolver.py) | 嚴格模式：解密 api_key 後檢查 `effective_provider in {openai, anthropic, gemini, azure, openrouter}` 但 api_key 為空 → `raise ValueError("模型 {name} 缺少 API Key，請至設定頁補齊")` |
| 3 | [backend/routers/chat.py](backend/routers/chat.py) | (a) `resolve_model_runtime` 呼叫處包 `try/except ValueError` → SSE error event；(b) `HTTPStatusError` handler 的訊息改為 `「LLM 服務錯誤（{provider} HTTP {status}）：{response_preview前120字}」`，使用者與工程師均可立刻定位 |
| 4 | [backend/routers/documents.py](backend/routers/documents.py) | 智慧匯入預覽端點的 `resolve_model_runtime` 呼叫處包 `try/except ValueError` → `HTTPException(status_code=422, detail="模型設定錯誤：{詳情}")` |

---

## 第三部分：預防措施

### 3.1 Prompt 規範

- 每次新增 / 修改 system prompt、page_agent prompt、RAG prompt 後，**必須**透過 API（非僅 UI 點選）測試以下三類問題不會拒答：
  1. 一般知識（例：「台灣最高的山？」）
  2. 自我介紹（例：「你好，你可以幫我做什麼？」）
  3. RAG 檢索（例：「什麼是 RAG？」）
- Prompt 限制條款使用「軟性建議」優先於「強制拒答」，例：避免「禁止」「不得」這類絕對詞。
- 多層 prompt（system + page_agent + file_context）疊加前，**先閱讀三者全文**檢查衝突。

### 3.2 雲端模型設定衛生

- 新增雲端模型至 `llm_models` 時：
  - 若使用 provider 預設端點，`base_url` 必須為 `NULL`，**不可填寫 ollama 內網位址**
  - `api_key` 必須驗證為對應 provider 的有效 key（建議呼叫一次 list_models / ping 確認）
- 嚴禁在 `llm_models.base_url` 填寫 `http://ollama:11434` 等內部服務位址，除非 provider 真的是 `ollama`。

### 3.3 LLM 呼叫點防呆

- 任何新增的 LLM 呼叫點呼叫 `resolve_model_runtime` 時，**必須**包 `try/except ValueError`：
  - SSE 路徑 → 寫入 error 訊息 + `[DONE]` + return
  - REST 路徑 → 轉成 `HTTPException(status_code=422, detail=...)`
- 錯誤訊息統一使用「模型設定錯誤：{詳情}」前綴，便於前端統一識別。
- 後端 `HTTPStatusError` 的 fallback 訊息**必須**包含 provider 與 status code，禁止使用無資訊量的「服務暫時無法使用」。

### 3.4 健康檢查例行化

- [backend/scripts/api_health_check.py](backend/scripts/api_health_check.py) 列為部署後 smoke test：
  - 任一新模組部署後 → 執行一次
  - 任一 prompt 修改後 → 執行一次
  - 任一 `llm_models` 變更後 → 執行一次
- 通過率必須維持 **100%**，任何 FAIL 必須在合併前修復。

---

## 第四部分：健康檢查結果

執行：

```
docker compose exec -T backend python scripts/api_health_check.py
```

輸出（2026-04-27 收尾驗證）：

```
=== API 健康檢查 @ http://localhost:8000 ===

登入成功

端點                                                     狀態      耗時(ms)      結果
------------------------------------------------------------------------------------------
GET /api/documents/                                    200     21.9        PASS
GET /api/knowledge-bases/                              200     35.2        PASS
GET /api/agent-skills/                                 200     5.2         PASS
GET /api/wiki/models                                   200     4.8         PASS
GET /api/settings/chat                                 200     5.3         PASS
GET /api/settings/llm                                  200     4.7         PASS
/api/chat/stream [page_agent:docs]                     200     3001.0      PASS
/api/chat/stream [page_agent:ontology]                 200     3810.6      PASS
/api/chat/stream [kb_agent]                            200     3212.9      PASS
/api/chat/stream [global_agent]                        200     5151.1      PASS
------------------------------------------------------------------------------------------
總計：10  通過：10  失敗：0  通過率：100.0%
```

---

## 相關檔案索引

- [backend/prompts/rag_system.py](backend/prompts/rag_system.py)
- [backend/prompts/page_agents.py](backend/prompts/page_agents.py)
- [backend/routers/chat.py](backend/routers/chat.py)
- [backend/routers/documents.py](backend/routers/documents.py)
- [backend/services/llm_resolver.py](backend/services/llm_resolver.py)
- [backend/scripts/api_health_check.py](backend/scripts/api_health_check.py)
- [docs/bugfix-report-2026-04-26-llm-service-error.md](docs/bugfix-report-2026-04-26-llm-service-error.md)（前置診斷報告）
