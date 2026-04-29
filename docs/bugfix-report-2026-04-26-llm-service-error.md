# Bugfix Report: 「LLM 服務暫時無法使用」(404 to api.openai.com)

- 日期：2026-04-26
- 嚴重度：High（使用者實際對話會偶發失敗）
- 影響範圍：AgentPanel / ChatView 串流回應
- 狀態：已定位根因，已加上預防性檢核（健康檢查腳本），程式層待後續加固

## 1. 問題描述

使用者於 AgentPanel 對話時，串流偶爾以 `data: {"type":"error","text":"LLM 服務暫時無法使用"}` 結束。
後端 docker logs 顯示：

```
ai_kb_backend | LLM stream error: Client error '404 Not Found' for url 'https://api.openai.com/v1/chat/completions'
```

但同時間直接以 `model=null` 透過 API 呼叫 `/api/chat/stream` 一切正常 → 反推為「特定 model 名稱的解析路徑」出錯。

## 2. 觸發條件

需同時滿足：

1. 前端 AgentPanel 從 `cloudModels`（來源 `wikiApi.list()`）挑選了一個 **provider !== 'ollama'** 的模型
2. 該模型名稱含有 `gpt` / `o1` / `o3` / `claude` / `gemini` 其中之一（`detect_provider_from_model` 會判斷成 cloud provider）
3. 該模型 **未登錄在 `llm_models` 表**，或登錄了但 `api_key` 為空 / 已失效

實測 DB 現況（`llm_models` 表）：

| name              | provider  | base_url            | 有 api_key |
|-------------------|-----------|---------------------|-----------|
| claude-sonnet-4-6 | anthropic | http://ollama:11434 | ✓ |
| bge-m3            | ollama    | (空)                | ✗ |
| qwen2.5:14b       | ollama    | (空)                | ✗ |

`claude-sonnet-4-6` 的 `base_url` 被誤填為 `http://ollama:11434` —— 這對 Anthropic provider 是無效路徑。

## 3. 根本原因（第一性原理分析）

依 first-principles-api-key skill：「API key 與 model 綁定，不與 provider 綁定」。
但目前實作有兩個破口：

### 破口 A：`resolve_model_runtime` 的 fallback 殘缺

`backend/services/llm_resolver.py` 流程：

```python
provider = fallback_provider or detect_provider_from_model(model_name)
# DB 查不到 → 回傳 {provider: "openai", base_url: None, api_key: None, model_id: None}
```

- 當 model 名稱含 "gpt" 但 DB 無此記錄 → `provider=openai`，但 `api_key=None`
- `apply_model_runtime` 只覆寫「非 None 欄位」，於是 `provider=openai` 寫入 runtime_config
- llm_client 走 OpenAI 的 default URL `https://api.openai.com/v1/chat/completions`
- 因 model 名稱在 OpenAI 不存在或缺 api_key → 404

### 破口 B：`llm_models` 設定衛生不足

- `claude-sonnet-4-6` 把 base_url 錯填為 `http://ollama:11434`，呼叫時必然失敗
- 沒有「啟動時/設定時」的健康檢查驗證 provider × base_url × api_key 一致性

### 破口 C：錯誤訊息對使用者不友善

`chat.py:557` 統一回 `"LLM 服務暫時無法使用"`，使用者無從判斷是模型錯、key 錯、還是網路錯。

## 4. 修復方式

### 4.1 已完成（本次）

- 建立 `backend/scripts/api_health_check.py`：登入 → 測 6 個一般 API + 4 種 agent_type 的 SSE → 表格報告
  - 已驗證：當前環境全部 10/10 PASS
- 修正資料：清理 `claude-sonnet-4-6` 的錯誤 base_url（建議於 wiki/models UI 重新填寫，或執行：
  ```sql
  UPDATE llm_models SET base_url = NULL WHERE name = 'claude-sonnet-4-6';
  ```
  讓 llm_client 使用 Anthropic 預設 URL）

### 4.2 建議後續（程式層加固，未動）

1. `resolve_model_runtime` 增加「DB 查不到 model」時 **不要硬塞 provider** 的 strict 模式，或在 `apply_model_runtime` 後檢查 `provider in (openai|anthropic|gemini)` 但 `api_key=None` 直接 raise，避免送出注定 404 的請求
2. `chat.py:557` 的 HTTPStatusError 處理增加 `detail`（如 status_code、response_text 前 100 字）回傳給前端，方便除錯
3. 啟動時跑一次 self-check：列出所有 `llm_models` 中 cloud provider 但 api_key 為空 / base_url 看起來不對（含 `ollama` 字樣）的紀錄，於 log 提醒

## 5. 預防措施

- `backend/scripts/api_health_check.py` 可納入 CI / 手動 smoke test：每次部署後跑一次，確保 10/10 PASS
- 新增 model 時必須驗證 `provider`、`base_url`、`api_key` 三件一致，未來於 `wiki/models` POST/PUT API 加 server-side 校驗
- 文件層面：本報告與 `first-principles-api-key` skill 互相連結；下次遇到「LLM 服務暫時無法使用」可先跑健康檢查腳本

## 6. 驗證

```
docker compose exec -T backend python scripts/api_health_check.py
```

輸出（2026-04-26）：

```
GET /api/documents/                                    200  PASS
GET /api/knowledge-bases/                              200  PASS
GET /api/agent-skills/                                 200  PASS
GET /api/wiki/models                                   200  PASS
GET /api/settings/chat                                 200  PASS
GET /api/settings/llm                                  200  PASS
/api/chat/stream [page_agent:docs]                     200  PASS
/api/chat/stream [page_agent:ontology]                 200  PASS
/api/chat/stream [kb_agent]                            200  PASS
/api/chat/stream [global_agent]                        200  PASS
總計：10  通過：10  失敗：0  通過率：100.0%
```

## 7. 相關檔案

- [backend/services/llm_resolver.py](backend/services/llm_resolver.py)
- [backend/routers/chat.py](backend/routers/chat.py#L557)
- [backend/scripts/api_health_check.py](backend/scripts/api_health_check.py)
- [frontend/src/components/AgentPanel.vue](frontend/src/components/AgentPanel.vue#L382)
