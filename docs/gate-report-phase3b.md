# Gate Report — Phase 3b：插件系統

**日期**：2026-04-17  
**驗收人**：AI Agent（自動驗收）  
**驗收結果**：✅ 全部通過

---

## 一、工作清單完成情況

| 項目 | 狀態 | 說明 |
|------|------|------|
| PG `plugins` 資料表（已存在） | ✅ | `id / name / endpoint / auth_header / enabled / created_at` |
| `backend/routers/plugins.py` — CRUD | ✅ | POST / GET / PATCH / DELETE / toggle / invoke |
| `auth_header` Fernet 加密寫入、讀出時不暴露 | ✅ | `has_auth: true` 取代明文 |
| `backend/tasks/webhook_tasks.py` — Celery Webhook | ✅ | `tasks.call_webhook` 注冊並執行成功 |
| 停用插件 → invoke 被攔截（不影響核心功能） | ✅ | 422 `{"detail":"插件已停用"}` |

---

## 二、容器快照

```
NAMES              STATUS
ai_kb_playwright   Up (healthy)
ai_kb_ollama       Up (healthy)
ai_kb_celery       Up
ai_kb_backend      Up (healthy)
ai_kb_postgres     Up (healthy)
ai_kb_qdrant       Up (healthy)
ai_kb_redis        Up (healthy)
ai_kb_neo4j        Up (healthy)
ai_kb_minio        Up (healthy)
```

---

## 三、Gate 3b 驗收證據

### 3.1 POST /api/plugins — 建立插件

```
POST /api/plugins
{
  "name": "test-webhook",
  "endpoint": "https://httpbin.org/post",
  "auth_header": "Bearer secret-token-123",
  "input_schema": {"query": "string"}
}
→ HTTP 201
{
  "id": "b7bfb7f2-5e35-4847-851d-c6e22f83c7ca",
  "name": "test-webhook",
  "endpoint": "https://httpbin.org/post",
  "has_auth": true,            ← 不暴露密文
  "enabled": true
}
```

**DB 密文確認**：
```sql
SELECT name, enabled, LEFT(auth_header, 20) AS auth_prefix FROM plugins;
-- test-webhook | t | gAAAAABp4a8hpo2Ydbz_   ← Fernet 格式
```

### 3.2 GET /api/plugins — 列出插件

```
GET /api/plugins → [{id, name, has_auth: true, enabled: true, ...}]
```

### 3.3 POST /api/plugins/{id}/invoke — Webhook 觸發

```
POST /api/plugins/b7bfb7f2/invoke
{"query": "hello world"}
→ {"task_id": "dee77d48-92d6-42e6-9f9a-bd8a53c85694", "status": "queued"}
```

**Celery 執行日誌**：
```
[INFO] Invoking plugin plugin_id=b7bfb7f2 endpoint=https://httpbin.org/post
[INFO] Plugin response plugin_id=b7bfb7f2 status=200
[INFO] Task tasks.call_webhook[dee77d48] succeeded in 1.12s: {'status_code': 200, ...}
```

**httpbin.org 回應驗證**：反射請求中含有解密後的 `Authorization: Bearer secret-token-123` header。

### 3.4 POST /api/plugins/{id}/toggle — 停用插件

```
POST /api/plugins/b7bfb7f2/toggle → {"enabled": false}
POST /api/plugins/b7bfb7f2/invoke → HTTP 422 {"detail": "插件已停用"}
```

### 3.5 DELETE /api/plugins/{id} — 刪除插件

```
DELETE /api/plugins/b7bfb7f2 → HTTP 204 No Content
DB: SELECT count(*) FROM plugins; → 0
```

---

## 四、新增/修改的檔案

| 檔案 | 操作 | 說明 |
|------|------|------|
| `backend/routers/plugins.py` | 修改 | 從 stub 實作完整 CRUD（POST / GET / PATCH / DELETE / toggle / invoke） |
| `backend/tasks/webhook_tasks.py` | **新建** | Celery Webhook 任務（含 Fernet 解密 + retry） |
| `backend/tasks/__init__.py` | 修改 | `include` 加入 `tasks.webhook_tasks` |

---

## 五、下一步（Phase 3c）

Phase 3c — Agent 整合：
- `backend/tools/` — LlamaIndex Retriever Tool 適配器
- `backend/tools/code_executor.py` — RestrictedPython 沙盒
- `backend/routers/agent.py` — LangChain ReAct Agent（SSE 串流）
- SearXNG 容器啟動確認（`web_search` 工具）
- Gate 3c 驗收：knowledge_base_search + web_search + code_executor
