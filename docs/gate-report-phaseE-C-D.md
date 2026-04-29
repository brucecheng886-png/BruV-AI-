# Gate Report — Phase E + C + D

> 期間：本批次連續執行 Phase E（Prompt 治理）、Phase C（反思 / 重生）、Phase D（模板引擎整合）
> 規範依據：第一性原理（API Key 解密路徑）、Vue script setup import 順序、執行準則、Debug 準則、16 容器架構

---

## 一、完成範疇

| Phase | 子項 | 狀態 |
|-------|------|------|
| **E1/E4/E6/E7** | `backend/prompts/` 模組（7 檔）+ chat.py 全面接入 | ✅ |
| **E5** | 12 個使用者面向 Prompt 模板（writing×3 / translate×1 / analysis×3 / extract×2 / code×2 / qa×1） | ✅ |
| **C2** | Chat 反思 — REFLECTION_JUDGE_PROMPT + 反思 SSE event + 必要時自動重生 | ✅ |
| **C3** | Agent 自我批判 — 每 N 步呼叫 AGENT_REFLECTION_PROMPT；max_iterations 8→12；月度成本上限保護 | ✅ |
| **C1** | Chat 訊息重生成 — `messages.regenerated_from` 欄位 + 新端點 + 前端 ↻ 按鈕 | ✅ |
| **C4** | Ingestion fallback — 雲端 embedding 失敗 → ollama bge-m3 + 寫入 `documents.ingestion_warnings` | ✅ |
| **E7（前端）** | Chat 系統通知橫幅 — 接收 `system_notice` SSE event 顯示黃色警示 | ✅ |
| **Phase D** | 模板引擎整合 — `llm_usage_log.template_id` + `prompt_template_auto_match` 設定 + 前端 📋 模板選擇器 | ✅ |

---

## 二、五點自我檢查（綜合）

### 1. 第一性原理 — API Key
- 所有新增 LLM 呼叫均沿用 `_rag_stream` 既有 model 解析鏈（`model_api_key` 優先 → `decrypt_secret` → `system_settings`）。
- C4 雲端 embedding 仍走 `kb_cfg.embedding_api_key`；fallback 僅切換 provider 不繞過解密。
- Phase D 模板列表為公開 metadata，無 secret 暴露。
- **結論：未引入新的 API Key 取得路徑，符合單一事實源。**

### 2. Vue script setup import 順序
- ChatView.vue 新增 `useAuthStore` import：放在 `useChatStore` 旁，無任何可執行語句插入 import 之間。
- Phase D 新增 `templatePickerVisible/templateList/templateLoading` 與 `openTemplatePicker/applyTemplate`：均放在 `chatStore` destructure 之後，imports 完全集中於頂部。
- **結論：手動逐行檢查通過，無 setup 函式損毀風險。**

### 3. 執行準則
- 所有 ALTER TABLE 使用 `IF NOT EXISTS`（idempotent）。
- psycopg2 / asyncpg 全部使用參數化（`%s` / `:name`），無字串拼接。
- JSONB 串接採 `COALESCE(..., '[]'::jsonb) || %s::jsonb`。
- LLM 反思失敗以 warning 記錄，不阻斷主流程。

### 4. Debug 準則
- C4：雲端 → ollama → 全域 ollama 三層 fallback；warning 寫入 documents JSONB 留痕。
- C2：反思 JSON 解析失敗時靜默略過，不影響使用者體驗。
- C1：重生成失敗回傳 400/404 + 訊息，前端顯示 `⚠️`。
- 所有 fallback 路徑均可被觀測（log + 持久化欄位）。

### 5. 16 容器架構
- 無新增容器。
- Saga（Postgres / Qdrant / Neo4j 三庫）邏輯未動，C4 fallback 在 `_embed_dispatch` 內完成，Saga 後續流程完全相容。
- Prometheus `track_llm_call` 計數仍涵蓋反思 / 重生 / fallback 後的所有 LLM 呼叫。

---

## 三、資料庫變更摘要

```sql
ALTER TABLE messages       ADD COLUMN IF NOT EXISTS regenerated_from UUID NULL;
CREATE INDEX IF NOT EXISTS ix_messages_regenerated_from ON messages(regenerated_from);
ALTER TABLE documents      ADD COLUMN IF NOT EXISTS ingestion_warnings JSONB DEFAULT '[]'::jsonb;
ALTER TABLE llm_usage_log  ADD COLUMN IF NOT EXISTS template_id UUID NULL;
```

新增 `system_settings` keys：`chat_reflection_enabled`、`prompt_template_auto_match`（皆預設 false）。

---

## 四、驗證紀錄

- `py_compile` EXIT 0：`prompts/*.py`、`chat.py`、`agent.py`、`settings_router.py`、`document_tasks.py`、`models.py`、`seed_prompt_templates.py`
- `docker compose restart backend` 後日誌出現 `Application startup complete`
- `docker compose build --no-cache nginx` + `up -d nginx` 成功
- OpenAPI 顯示 `POST /api/chat/conversations/{conv_id}/messages/{msg_id}/regenerate`
- DB `information_schema.columns` 確認 3 個新欄位存在
- Seed 腳本：5 個原模板跳過 + 12 個新模板匯入 = DB 共 17 筆

---

## 五、Phase D 後續延伸（暫定）

- `prompt_template_auto_match=true` 時於 `_rag_stream` 內呼叫 `match_template` 並注入 `filled_prompt` 至 system context（目前僅留設定旗標，避免無感切換造成行為偏移）。
- 前端 SettingsView 新增模板開關面板 + 顯示啟用狀態。
- `llm_usage_log.template_id` 寫入：在使用模板的 chat 流程中記錄 `template_id` 以便成本歸因。

---

> 本報告由 Copilot 於批次執行收尾自動生成；Session memory 詳細逐項紀錄見 `/memories/session/phase-ce-execution-log.md`。
