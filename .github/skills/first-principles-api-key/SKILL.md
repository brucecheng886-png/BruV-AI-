---
name: first-principles-api-key
description: "API Key 讀取與 LLM 呼叫的第一原則設計準則。每次涉及 api_key、llm_stream、provider、get_llm_runtime_config、_rag_stream 的修改，都必須先讀取此 skill 作為設計基準。"
argument-hint: "指定修改場景，例如：新增 provider、修改 _rag_stream、修改 verify_model"
---

# API Key 第一原則設計準則

> **核心信念**：API Key 必須與模型綁定。Key 跟著 model 走，不跟著 provider 走。

---

## 一、觸發條件（以下任一情況必須先讀此 skill）

- 任何涉及 `api_key` 讀取或傳遞的修改
- 任何涉及 `llm_stream`、`llm_client` 的呼叫
- 任何新增或修改 `provider` 的支援邏輯
- 任何修改 `get_llm_runtime_config` 函式
- 任何修改 `_rag_stream`、`_agent_stream` 等 LLM 呼叫入口
- 任何修改 `verify_model` 或類似的 API 連線測試邏輯

---

## 二、核心原則

### 2.1 Key 跟模型綁定，不跟 provider 綁定

每個 `llm_models` 記錄可以有自己的 `api_key`（加密儲存）。  
同一個 provider（如 anthropic）可以有多個模型，每個模型可以有**不同**的 key。  
因此 **正確的查詢單位是 model，而不是 provider**。

### 2.2 system_settings 只作 Fallback

`system_settings` 表中的 `anthropic_api_key`、`openai_api_key` 等欄位是**全域預設值**，  
只有在 `llm_models` 找不到對應模型、或該模型沒有自己的 `api_key` 時，才能使用。

### 2.3 加密/解密規範

- 儲存：`encrypt_secret(raw_key)` → 存入 DB
- 讀取：`decrypt_secret(m.api_key)` → 使用前必須解密
- 來源：`from backend.utils.crypto import encrypt_secret, decrypt_secret`

---

## 三、標準 API Key 讀取流程

每次發起 LLM 呼叫前，必須依照以下順序決定 key：

```python
# Step 1：從 llm_models 查詢對應模型
result = await db.execute(
    select(LLMModel).where(
        LLMModel.name == model_name,
        LLMModel.provider == provider
    )
)
m = result.scalar_one_or_none()

# Step 2：取出並解密 api_key
model_api_key = None
if m and getattr(m, "api_key", None):
    model_api_key = decrypt_secret(m.api_key)

# Step 3：同時取出 provider、base_url（若有）
model_provider = m.provider if m else provider
model_base_url = m.base_url if m else None

# Step 4：呼叫 LLM API，優先用 model_api_key
effective_key = model_api_key or system_settings_fallback_key

# Step 5：若 llm_models 找不到模型，才使用 system_settings fallback
# （system_settings fallback 由 get_llm_runtime_config 提供）
```

---

## 四、各場景標準實作範例

### 4.1 `_rag_stream`（chat.py）

```python
# 正確做法：
runtime_config = await get_llm_runtime_config(db)  # system_settings fallback

if "claude" in model.lower():
    runtime_config = {**runtime_config, "provider": "anthropic"}

# 查詢 llm_models，覆寫 api_key（model-level key 優先）
result = await db.execute(
    select(LLMModel).where(
        LLMModel.name == model,
        LLMModel.provider == "anthropic"
    )
)
m = result.scalar_one_or_none()
if m and getattr(m, "api_key", None):
    runtime_config = {**runtime_config, "api_key": decrypt_secret(m.api_key)}
```

### 4.2 `verify_model`（wiki.py）

```python
# 正確做法：所有 provider 都使用 effective_key（包含 anthropic）
effective_key = body.api_key
if not effective_key and body.model_id:
    result = await db.execute(select(LLMModel).where(LLMModel.id == body.model_id))
    m = result.scalar_one_or_none()
    if m and getattr(m, "api_key", None):
        effective_key = decrypt_secret(m.api_key)

# anthropic 驗證
if body.provider == "anthropic":
    headers = {
        "x-api-key": effective_key or "",   # ← 必須用 effective_key，不是 body.api_key
        "anthropic-version": "2023-06-01",
    }
```

---

## 五、違反此原則的常見錯誤模式

| 錯誤模式 | 正確做法 |
|----------|----------|
| `"x-api-key": body.api_key or ""` | `"x-api-key": effective_key or ""` |
| `api_key = settings.get("anthropic_api_key")` 作為主要來源 | 先查 `llm_models`，system_settings 只作 fallback |
| 只針對部分 provider 查 DB，其他 provider 直接用 body.api_key | 所有 provider 統一走 effective_key 流程 |
| 新增 provider 支援時，忘記處理 model-level key | 每個新 provider 的呼叫路徑都必須經過 llm_models 查詢 |
| `get_llm_runtime_config` 回傳的 key 直接用，不嘗試從 llm_models 覆寫 | `get_llm_runtime_config` 只是 fallback 起點 |

---

## 六、自檢清單（修改涉及 API Key 的代碼前）

- [ ] 是否先查詢 `llm_models` 表？
- [ ] 是否對查到的 `api_key` 呼叫 `decrypt_secret`？
- [ ] `system_settings` 的 key 是否只作 fallback？
- [ ] `verify_model` 等測試端點是否所有 provider 都用 `effective_key`？
- [ ] 新增 provider 是否遵循相同的 key 優先順序？
