# Gate Report — Phase 3c: Agent 整合

**日期**: 2025-01-XX  
**狀態**: ✅ PASSED

---

## 驗收清單

### 1. LangChain ReAct Agent 基礎框架

| 項目 | 結果 |
|------|------|
| `POST /api/agent/run` 202 Accepted | ✅ |
| `GET /api/agent/tasks/{task_id}` 狀態查詢 | ✅ |
| Agent 任務背景執行（daemon thread） | ✅ |
| Redis DB3 任務狀態持久化（TTL 24h） | ✅ |
| LangChain ReAct prompt（hub.pull + fallback） | ✅ |

---

### 2. knowledge_base_search 工具驗收

**測試任務**: "You must use knowledge_base_search tool. Action: knowledge_base_search, Action Input: Taiwan capital city"

```json
{
  "task_id": "d3bbb314-6535-40d6-b12e-36afbe7893ec",
  "status": "completed",
  "steps": [
    {"type": "action", "tool": "knowledge_base_search", "input": "台灣的首都"},
    {"type": "observation", "output": "[test_doc.txt p.1] 台灣的首都是台北市..."}
  ],
  "result": "台灣的首都是台北市。"
}
```

✅ `knowledge_base_search` 正確呼叫  
✅ Qdrant 向量搜尋返回正確知識庫內容  
✅ BGE-reranker 重排序後返回最相關片段  

---

### 3. web_search 工具驗收

**測試任務**: "I need you to search the internet right now for: current time in Tokyo Japan. Use web_search."

```json
{
  "task_id": "b3011538-c3f0-442c-a34a-ecafcd8ead73",
  "status": "completed",
  "steps": [
    {"tool": "web_search"},
    {"tool": "web_search"},
    {"tool": "web_search"},
    {"tool": "web_search"},
    {"tool": "web_search"}
  ],
  "result": "The current time in Tokyo, Japan is displayed on this page..."
}
```

✅ `web_search` 呼叫 SearXNG（`http://searxng:8080/search?format=json`）  
✅ 返回真實網路搜尋結果  

---

### 4. code_executor 沙盒驗收

**直接測試結果**:

```
Test1 (math.factorial(10)): {'output': '3628800\n', ...}
Test2 (import os blocked): {'error': "Module 'os' is not allowed..."}
Test3 (import subprocess blocked): {'error': "Module 'subprocess' is not allowed..."}
```

✅ `math.factorial(10)` = 3628800（計算正確）  
✅ `import os` — 被白名單阻擋（"Module 'os' is not allowed"）  
✅ `import subprocess` — 被白名單阻擋  
✅ RestrictedPython PrintCollector 輸出捕捉正常  
✅ 30 秒 timeout 保護機制就緒  

**允許模組白名單**: math, statistics, json, re, datetime, collections, itertools, functools, decimal, fractions, random, string

---

### 5. SearXNG 容器驗收

```bash
GET http://localhost:8080/search?q=test&format=json → 200 OK
```

✅ SearXNG 容器（ai_kb_searxng）健康運行  
✅ JSON API 已啟用（settings.yml formats: json）  
✅ 限流已關閉（limiter: false）  

---

## 踩坑記錄

1. **qdrant-client API 更新（1.11.3 → 1.17.1）**: `.search()` 改為 `.query_points()`，回傳 `result.points`
2. **LangChain/LlamaIndex 依賴衝突**: `tenacity==9.0.0` 與 `langchain<9` 要求衝突 → 改為 `tenacity>=8.1.0,<9.0.0`; `pypdf==5.0.1` → `>=4.3.1`
3. **RestrictedPython print 機制**: 需使用 `PrintCollector` 類別（非實例），並從 `exec_result["_print"].txt` 讀取輸出
4. **SearXNG 403 Forbidden**: 需在 `settings.yml` 中加入 `formats: [html, json]`
5. **bcrypt hash 損壞（psql `$12` 解析為位置參數）**: 改用 SQLAlchemy 參數化查詢更新密碼
6. **背景執行緒被 uvicorn hot-reload 殺死**: 避免在 `/app` 目錄內新建測試腳本
7. **模型 Action Input 包含 backtick/`code="..."` 包裝**: `_strip_code_fencing` 函數處理多種格式

---

## 交付物

| 檔案 | 說明 |
|------|------|
| `backend/routers/agent.py` | LangChain ReAct Agent（POST /run + GET /tasks/{id}） |
| `backend/tools/llama_retriever_tool.py` | knowledge_base_search（Qdrant + BGE-reranker） |
| `backend/tools/code_executor.py` | RestrictedPython 沙盒（白名單 + timeout） |
| `backend/tools/__init__.py` | 套件初始化 |
| `searxng/settings.yml` | JSON API 啟用 |
| `backend/requirements.txt` | LangChain 0.3.7、LlamaIndex 0.11.22 等依賴啟用 |

---

## 下一步：Phase 4

- `backend/routers/ontology.py` — Review Queue CRUD
- `backend/routers/wiki.py` — LLM Wiki 摘要生成
- Frontend：Vue 3 知識圖譜 + Ontology 審查頁面
