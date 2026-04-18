56vu---
name: 執行架構
description: "地端 AI 知識庫最終可執行架構。包含修正後的三庫一致性、容器定義、資料流邂輯、API 規格、Phase 工作清單、Phase 完成報告規範。使用時機：開始實作任一模組前、查詢技術決策依據、Phase 驗收報告產出、解決架構歧義時。"
argument-hint: "指定查詢範圍，例如：三庫一致性、容器、API、資料流"
---

# 地端 AI 知識庫 — 最終可執行架構 v2.0

> 基於 v1.0 的九項邏輯漏洞修正版。每個決策背後均附修正理由。

---

## 一、修正清單總覽

| # | 問題 | 修正方式 |
|---|------|---------|
| 1 | 三庫寫入無交易保護 | Saga 補償日誌改為**必要**元件 |
| 2 | code_executor 無規格 | 定義 RestrictedPython 沙盒 + 白名單 |
| 3 | auth_header 明文儲存 | Fernet 加密，金鑰存 .env |
| 4 | Re-ranker 無容器歸屬 | 定義為 backend 容器內 CPU 推理 |
| 5 | Playwright 無通訊介面 | 獨立 HTTP 服務，內部 :3002 |
| 6 | LlamaIndex + LangChain 無整合層 | 定義 `LlamaIndexRetrieverTool` 適配器 |
| 7 | 改 custom_fields 觸發 re-embedding | 分類為 payload update，不觸發 re-embedding |
| 8 | Excel 套用 SentenceWindowNodeParser | Excel 使用 TableRowParser，文字另用 SentenceWindowNodeParser |
| 9 | Phase 3 塞太多 | 拆為 3a / 3b / 3c 三個可獨立驗收的子 Phase |

---

## 二、完整技術棧（修正版）

```
Frontend  : Vue 3.4 + Vite + Pinia + Element Plus（全域註冊）
            Cytoscape.js（Ontology）、marked.js + DOMPurify（Markdown）
            純 JavaScript（非 TypeScript）、原生 fetch（非 axios）
            SheetJS 靜態載入（window.XLSX，避免 Node 24 rollup 問題）

Backend   : FastAPI 0.104 + Uvicorn（ASGI）
            asyncio + httpx
            Celery + Redis Broker
            Re-ranker：BAAI/bge-reranker-large（CPU，backend 容器內載入）
            加密：cryptography.Fernet（用於 plugin auth_header）

LLM       : Ollama :11434（主推理 qwen2.5:14b / 72b）
            Embedding：bge-m3 1024d（Ollama 載入）

RAG框架   : LlamaIndex（VectorStoreIndex + SentenceWindowNodeParser）
            LangChain（Agent ReAct 框架）
            整合層：LlamaIndexRetrieverTool（自製適配器，見第六節）

資料庫    : Qdrant :6333（向量 + payload）
            Neo4j CE :7474/:7687（圖）
            PostgreSQL 16 :5432（結構 + JSONB）
            Saga 補償日誌：SQLite（backend 容器內，/data/saga.db）【必要，非選配】

輔助      : Redis 7 :6379、MinIO :9000/:9001
            Playwright 爬蟲服務 :3002（內部）
            SearXNG :8080（搜尋插件，核心工具預設啟用保護）

監控      : Loki :3100、Promtail、Grafana :3001、Prometheus :9090

代理      : Nginx :80/:443
部署      : Docker Compose（16 個容器）
```

---

## 三、容器清單（修正版，共 16 個）

| 服務名 | 映像 | 外部 Port | 內部 Port | 說明 |
|--------|------|-----------|-----------|------|
| `nginx` | nginx:alpine | 80, 443 | — | 反向代理 |
| `postgres` | postgres:16 | 5432 | 5432 | 主 DB |
| `qdrant` | qdrant/qdrant | 6333 | 6333 | 向量 DB |
| `neo4j` | neo4j:5-community | 7474, 7687 | — | 圖 DB |
| `redis` | redis:7-alpine | 6379 | 6379 | Broker / Cache |
| `minio` | minio/minio | 9000, 9001 | — | 物件儲存 |
| `ollama` | ollama/ollama | 11434 | 11434 | LLM 推理（GPU） |
| `backend` | 自建 | 8000 | 8000 | FastAPI + Re-ranker |
| `celery-worker` | 自建（同 backend image）| — | — | Celery 非同步任務 |
| `playwright-service` | 自建 | — | **3002** | Playwright HTTP API |
| `searxng` | searxng/searxng | 8080 | 8080 | 私有搜尋引擎 |
| `loki` | grafana/loki | 3100 | 3100 | 日誌聚合 |
| `promtail` | grafana/promtail | — | — | 日誌採集 |
| `prometheus` | prom/prometheus | 9090 | 9090 | Metrics |
| `grafana` | grafana/grafana | 3001 | 3001 | 監控 |
| `frontend`（生產）| 自建 nginx | 3000 | 80 | Vue 靜態服務 |

> `backend` 和 `celery-worker` 使用同一個 Docker image，共享 `/app` 程式碼，指令不同：
> - backend：`uvicorn main:app --host 0.0.0.0 --port 8000`
> - celery-worker：`celery -A tasks worker --loglevel=info`

---

## 四、修正後的三庫一致性（Saga 必要元件）

### 原則
- 任何跨資料庫操作（寫入 / 刪除）必須透過 Saga 協調器
- SQLite `/data/saga.db` 為補償日誌（backend 容器內，不需額外容器）
- 失敗時按逆序補償，保證最終一致性

### 寫入順序（向前）
```
1. PostgreSQL INSERT chunks（可 rollback）
2. Qdrant upsert vectors
3. Neo4j MERGE entities
4. SQLite saga_log → status='COMMITTED'
```

### 補償順序（向後，任一步驟失敗觸發）
```
Neo4j DETACH DELETE entities（若已寫入）
→ Qdrant delete points（若已寫入）
→ PostgreSQL DELETE chunks（若已寫入）
→ SQLite saga_log → status='COMPENSATED'
```

### 刪除文件的 Entity 處理
- 刪除 `(:Document)-[:MENTIONS]->(:Entity)` 關係
- 若 Entity 節點的 `MENTIONS` in-degree 變為 0 且無 `INSTANCE_OF` 關係 → 一併刪除 Entity 節點
- 若 Entity 仍被其他文件引用 → 僅刪除關係，保留節點

---

## 五、各元件修正說明

### 5.1 Re-ranker（修正：定義容器歸屬）
- **位置**：`backend` 容器內，啟動時載入模型至記憶體
- **硬體**：CPU 推理（~300ms / batch，可接受）
- **載入方式**：
```python
# backend/services/reranker.py
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch

class Reranker:
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-reranker-large")
        self.model = AutoModelForSequenceClassification.from_pretrained("BAAI/bge-reranker-large")
        self.model.eval()
    
    def rerank(self, query: str, passages: list[str], top_k: int = 5) -> list[int]:
        pairs = [[query, p] for p in passages]
        with torch.no_grad():
            inputs = self.tokenizer(pairs, padding=True, truncation=True,
                                    max_length=512, return_tensors="pt")
            scores = self.model(**inputs).logits.squeeze(-1)
        ranked = scores.argsort(descending=True).tolist()
        return ranked[:top_k]
```

### 5.2 Playwright 服務（修正：定義 HTTP 介面）
```
playwright-service 容器（內部 :3002）
  POST /fetch     → { url } → { html, text, status_code }
  POST /screenshot → { url } → { minio_key }
  POST /fill_form  → { url, selector, value } → { success }
```

FastAPI 透過 `httpx.AsyncClient` 呼叫：
```python
PLAYWRIGHT_URL = "http://playwright-service:3002"
async def fetch_page(url: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(f"{PLAYWRIGHT_URL}/fetch", json={"url": url})
        res.raise_for_status()
        return res.json()
```

### 5.3 LlamaIndex + LangChain 整合層（修正：定義適配器）
```python
# backend/tools/llama_retriever_tool.py
from langchain.tools import Tool
from llama_index.core import VectorStoreIndex

class LlamaIndexRetrieverTool:
    """將 LlamaIndex QueryEngine 包裝成 LangChain Tool"""
    
    def __init__(self, index: VectorStoreIndex):
        self._engine = index.as_query_engine(
            similarity_top_k=20,
            node_postprocessors=[reranker_postprocessor]
        )
    
    def query(self, input: str) -> str:
        response = self._engine.query(input)
        sources = [
            f"[{n.metadata['doc_title']} p.{n.metadata.get('page','')}]"
            for n in response.source_nodes
        ]
        return f"{response.response}\n\n來源：{', '.join(sources)}"
    
    def as_langchain_tool(self) -> Tool:
        return Tool(
            name="knowledge_base_search",
            func=self.query,
            description="搜尋本地知識庫，回答與已上傳文件相關的問題"
        )
```

### 5.4 auth_header 加密（修正：Fernet 加密）
```python
# backend/utils/crypto.py
from cryptography.fernet import Fernet
import os

_fernet = Fernet(os.environ["PLUGIN_ENCRYPT_KEY"].encode())

def encrypt_secret(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()

def decrypt_secret(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
```

PostgreSQL 儲存加密後字串，使用插件時才解密，金鑰僅存 `.env`。

### 5.5 code_executor 沙盒規格（修正：定義規格）
```python
# backend/tools/code_executor.py
from RestrictedPython import compile_restricted, safe_globals
import signal

ALLOWED_IMPORTS = {"math", "statistics", "json", "re", "datetime", "collections"}
TIMEOUT_SECONDS = 30

def execute_code(code: str) -> dict:
    # 1. 白名單 import 檢查
    for line in code.splitlines():
        if line.strip().startswith("import") or line.strip().startswith("from"):
            module = line.split()[1].split(".")[0]
            if module not in ALLOWED_IMPORTS:
                return {"error": f"Module '{module}' not allowed"}
    
    # 2. 編譯時靜態分析
    try:
        byte_code = compile_restricted(code, "<string>", "exec")
    except SyntaxError as e:
        return {"error": str(e)}
    
    # 3. 執行時 timeout
    result = {}
    def _run():
        exec(byte_code, {**safe_globals, "_print_": print, "result": result})
    
    import threading
    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=TIMEOUT_SECONDS)
    if t.is_alive():
        return {"error": "Execution timeout (30s)"}
    
    return {"output": result}
```

### 5.6 Re-embedding 觸發邏輯（修正：分類處理）

| 修改類型 | 處理方式 | 說明 |
|---------|---------|------|
| `custom_fields` 變更 | `qdrant.set_payload()` | 僅更新 metadata，不動向量 |
| Chunk 文字內容變更 | 刪除舊 point → 重新 embed → upsert | 需要 Saga 保護 |
| 文件重新上傳 | 走完整攝取管線 | 先刪除舊記錄再重建 |

### 5.7 Excel / 表格 Chunking（修正：分類解析器）

```python
class DocumentChunkerFactory:
    @staticmethod
    def get_chunker(file_type: str):
        if file_type in ("xlsx", "csv"):
            return TableRowChunker()        # 每列 → "Col1: val | Col2: val"
        elif file_type == "pdf":
            return PDFChunker()             # OCR + SentenceWindowNodeParser
        elif file_type in ("docx", "txt", "md"):
            return TextChunker()            # SentenceWindowNodeParser(window=3)
        elif file_type == "html":
            return HTMLChunker()            # inner_text → TextChunker
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
```

### 5.8 SearXNG 定位修正（核心工具保護）
- SearXNG 作為 **核心工具**（非可停用插件）存在
- 插件系統的「停用」不影響 `web_search` Agent 工具
- 架構分層：
  - `web_search tool` → 永遠對應 SearXNG
  - 使用者插件 → 動態工具，停用只影響自訂工具集

### 5.9 JWT + Redis Session 邊界定義
- JWT：用於身份驗證（stateless，payload 含 user_id, role, exp）
- Redis Session（`session:{conv_id}`）：用於對話上下文快取（TTL 24h）
- Redis 掛掉：對話上下文遺失但 API 仍可使用（降級為無記憶模式）
- Token 儲存：`localStorage`（前端 Pinia `useAuthStore` 初始化時讀取，API 層統一注入 Bearer header）
  - 注意：localStorage 有 XSS 風險，已透過 CSP header + DOMPurify 降低攻擊面
  - 未來可考慮遷移至 httpOnly cookie，但需後端配合 Set-Cookie + CSRF 雙重保護

### 5.10 Ontology 衝突解決機制

新增 `ontology_review_queue` 表：
```sql
ontology_review_queue(
  id UUID PK,
  entity_name TEXT,
  entity_type TEXT,
  action TEXT,         -- 'create' | 'update' | 'delete'
  source_doc_id UUID,
  status TEXT,         -- 'pending' | 'approved' | 'rejected'
  created_at TIMESTAMPTZ
)
```
- LLM 自動生成的 Concept / Entity 先進入 review queue，狀態 `pending`
- 使用者在 Ontology 頁面審查後 approve（寫入 Neo4j）或 reject（加入封鎖清單）
- 使用者手動刪除的概念加入 `ontology_blocklist`，LLM 不得重新建立

---

## 六、修正後的 Phase 規劃

| Phase | 目標 | 驗收條件 |
|-------|------|---------|
| **Phase 0** | 環境驗證 | 所有工具版本確認、Port 無衝突 |
| **Phase 1** | 基礎設施 + Ollama | 14 個容器 healthy、LLM API 可呼叫 |
| **Phase 2** | RAG Chat MVP | 上傳 PDF → SSE 對話含引用來源 |
| **Phase 3a** | Playwright 管線 | 爬蟲服務可透過 API 呼叫、網頁 chunk 寫入三庫 |
| **Phase 3b** | 插件系統 | 插件 CRUD、Webhook 呼叫成功、auth_header 加密驗證 |
| **Phase 3c** | Agent 整合 | Agent 呼叫 knowledge_base_search + web_search + code_executor |
| **Phase 4** | Ontology + Wiki + 完整 UI | 圖譜可視化 + 模型比較頁 + Review Queue（前端已部分完成） |
| **Phase 5** | 監控 + 備份 + 生產就緒 | Grafana Dashboard、重啟恢復測試 |

---

### Phase 0 — 環境驗證（已完成 ✅）

**工作清單**
- [x] 確認 Docker 版本 ≥ 27、Docker Compose v2
- [x] 確認 Node.js ≥ 18、Python ≥ 3.10（容器用 3.11）
- [x] 確認 Ollama 已安裝並可呼叫（`ollama list`）
- [x] 確認 GPU 驅動 + CUDA 可用（RTX 4070 Super 12GB）
- [x] 確認 RAM ≥ 16GB（實際 31GB）
- [x] 確認所需 Port 無衝突（5432 / 6333 / 6379 / 7474 / 7687 / 8000 / 9000）

**交付物**：Gate 0 報告（tools/versions logged）

---

### Phase 1 — 基礎設施（已完成 ✅）

**工作清單**
- [x] `docker-compose.yml` — 16 服務定義
- [x] `.env` / `.env.example` — 環境變數（含 Fernet + JWT 金鑰）
- [x] `scripts/init_db.sql` — PG 10 張資料表（含 saga_log / ontology_review_queue / ontology_blocklist）
- [x] `nginx/nginx.conf` — 反向代理 + 限流 + SSE buffering off
- [x] `monitoring/` — Prometheus / Loki / Promtail / Grafana config
- [x] `searxng/settings.yml`
- [x] `playwright-service/main.py` — HTTP 服務（/fetch / /screenshot）
- [x] 容器健康確認：postgres / neo4j / redis / qdrant / minio 全部 healthy
- [x] Ollama 模型已拉取：`qwen2.5:14b` + `bge-m3`

**交付物**：Gate 1 報告（5 個基礎容器 healthy）

---

### Phase 2 — RAG Chat MVP（已完成 ✅）

**工作清單**
- [x] `backend/Dockerfile` — Python 3.11-slim，`PYTHONPATH=/app`
- [x] `backend/config.py` — Pydantic Settings
- [x] `backend/main.py` — FastAPI lifespan（`init_saga_db` + `ensure_qdrant_collection` + `get_reranker`）
- [x] `backend/auth.py` — JWT（bcrypt 直接操作，不用 passlib）
- [x] `backend/database.py` — AsyncPG + Neo4j async + AsyncQdrantClient + `ensure_qdrant_collection()`
- [x] `backend/models.py` — SQLAlchemy ORM（User / Document / Chunk / Conversation / Message）
- [x] `backend/routers/auth.py` — `/login` + `/me`
- [x] `backend/routers/documents.py` — `/upload` + 狀態查詢
- [x] `backend/routers/chat.py` — SSE RAG 串流（embed→Qdrant top-20→BGE rerank top-5→Ollama stream→save）
- [x] `backend/tasks/__init__.py` — Celery app + `init_saga_db()` 啟動初始化
- [x] `backend/tasks/document_tasks.py` — 完整攝取 pipeline（PDF/DOCX/XLSX/HTML/TXT）
- [x] `backend/services/reranker.py` — BGE-reranker-large 單例
- [x] `backend/services/saga.py` — SQLite Saga 補償日誌
- [x] `backend/services/storage.py` — MinIO 上傳/下載/刪除
- [x] `backend/utils/crypto.py` — Fernet 加密
- [x] `docker-compose.yml` backend + celery-worker 加入 `PYTHONPATH=/app`
- [x] backend / celery-worker 容器 healthy

**Gate 2 驗收結果**
- [x] `POST /api/auth/login` → JWT token
- [x] `GET /api/auth/me` → user info
- [x] 上傳 .txt → Celery 攝取 → `status=indexed, chunk_count=2`
- [x] Qdrant `points_count=2`（bge-m3 1024d）
- [x] SSE chat「台灣的首都是哪裡？」→ 串流回答「台灣首都是台北市」+ sources

**已知坑（踩過的）**
- passlib 1.7.4 與 bcrypt 5.x 不兼容 → 直接 `import bcrypt`
- Celery worker 需顯式設 `PYTHONPATH=/app`（Docker WORKDIR 不自動加入 sys.path）
- `tasks/__init__.py` 需呼叫 `init_saga_db()` 否則 SQLite 表不存在
- Qdrant healthcheck 無 wget → 改用 `cat /proc/1/status`
- Ollama 在本機非容器 → URL 用 `http://host.docker.internal:11434`

**前端建置已知坑**
- Node 24 與 rollup 不相容，必須用 `node:20-alpine` 建置
- SheetJS npm import 在 Node 24 崩潰，改用靜態 `window.XLSX`
- Vite build 無需 TypeScript，專案全程純 JavaScript

---

### Phase 3a — Playwright 管線（未開始）

**工作清單**
- [ ] `playwright-service` 容器啟動確認（`/health` 回 200）
- [ ] `backend/routers/search.py` — `POST /api/search/crawl` 端點（呼叫 playwright-service /fetch）
- [ ] `backend/tasks/crawl_tasks.py` — 爬蟲 Celery 任務（fetch → chunk → embed → 三庫寫入 with Saga）
- [ ] HTML chunker（BeautifulSoup inner_text → SentenceWindowNodeParser）
- [ ] MinIO 儲存截圖（/screenshot 端點）

**Gate 3a 驗收**
- [ ] `POST /api/search/crawl` 送入 URL → Celery 處理 → PG `status=indexed`
- [ ] Qdrant 有向量、PG 有 chunks、Neo4j 有 entities
- [ ] `/screenshot` 回傳 minio_key，MinIO 可取回圖片

---

### Phase 3b — 插件系統（未開始）

**工作清單**
- [ ] PG `plugins` 資料表（id / name / endpoint_url / auth_header_encrypted / is_active / owner_id）
- [ ] `backend/routers/plugins.py` — CRUD（create / list / update / delete / toggle）
- [ ] `auth_header` Fernet 加密寫入、讀出時解密（`backend/utils/crypto.py` 已完成）
- [ ] `backend/tasks/webhook_tasks.py` — Celery Webhook 呼叫任務（帶 retry）
- [ ] 插件停用 → Agent 工具動態移除（不影響 `web_search` 核心工具）

**Gate 3b 驗收**
- [ ] `POST /api/plugins` → 建立插件，auth_header DB 中為密文
- [ ] `DELETE /api/plugins/{id}` → 軟刪除
- [ ] Webhook 呼叫成功（mock server 回 200）
- [ ] 停用插件後 Agent 工具清單不含該插件

---

### Phase 3c — Agent 整合（未開始）

**工作清單**
- [ ] `backend/tools/llama_retriever_tool.py` — `LlamaIndexRetrieverTool` 適配器（架構 §5.3）
- [ ] `backend/tools/code_executor.py` — RestrictedPython 沙盒（架構 §5.5）
- [ ] `backend/routers/agent.py` — `POST /api/agent/run`（LangChain ReAct Agent）
- [ ] Agent 工具集：`knowledge_base_search` + `web_search`（SearXNG）+ `code_executor`
- [ ] SearXNG 容器啟動確認（確保 `web_search` 工具可用）
- [ ] Agent SSE 串流（步驟事件 + 最終答案）

**Gate 3c 驗收**
- [ ] Agent 回答需要知識庫的問題 → 呼叫 `knowledge_base_search`
- [ ] Agent 回答時事問題 → 呼叫 `web_search`
- [ ] Agent 執行簡單 Python 計算 → `code_executor` 回傳結果
- [ ] 惡意 `import os` 被沙盒攔截

---

### Phase 4 — Ontology + Wiki + 完整 UI（部分完成 🟡）

**工作清單**
- [ ] `backend/routers/ontology.py` — Review Queue CRUD（approve / reject / list pending）
- [ ] 封鎖清單 `ontology_blocklist` CRUD
- [ ] `backend/routers/wiki.py` — 條目查詢 + 手動建立
- [x] Vue 3 前端建置（`frontend/` 目錄）— **已完成基礎框架**
  - [x] 對話頁 `ChatView.vue`（SSE 串流 + sources 卡片）
  - [x] 文件管理頁 `DocsView.vue`（上傳 / 狀態 / 刪除 / 試算表預覽）
  - [x] Ontology 頁 `OntologyView.vue`（Cytoscape.js 圖譜 + Review Queue）
  - [x] 插件管理頁 `PluginsView.vue`
  - [x] 設定頁 `SettingsView.vue`（模型選擇 / 比較）
  - [x] 登入頁 `LoginView.vue` + NavBar + TitleBar 元件
  - [x] Pinia auth store + Vue Router + API 層
- [x] `frontend` Docker image + nginx（multi-stage build：node:20-alpine → nginx:alpine）

**Gate 4 驗收**
- [ ] 圖譜可視化（有節點和關係）
- [ ] Review Queue 可 approve/reject
- [ ] 前端 SSE 對話含 sources 卡片
- [ ] 模型比較頁可並排對比兩個 LLM 回答

---

### Phase 5 — 監控 + 備份 + 生產就緒（未開始）

**工作清單**
- [ ] Grafana Dashboard 建立（API 延遲 / Celery 佇列長度 / Qdrant 查詢數）
- [ ] Prometheus alerts 規則（容器 down / 磁碟 > 80%）
- [ ] PG 備份腳本（`pg_dump` 排程 + MinIO 上傳）
- [ ] Qdrant snapshot 排程
- [ ] Neo4j backup 排程
- [ ] 重啟恢復測試（全容器 `docker compose down` → `up` → 功能驗證）
- [ ] `.env.example` 所有金鑰說明完整
- [ ] README.md 部署文件
- [ ] Nginx HTTPS 設定（自簽憑證或 Let's Encrypt）

**Gate 5 驗收**
- [ ] Grafana Dashboard 顯示即時 metrics
- [ ] 重啟後所有功能正常（無資料遺失）
- [ ] PG + Qdrant + Neo4j 備份均可恢復

---

## 七、Phase 完成報告規範

> **BLOCKING RULE**：每個 Phase 的全部 Gate 驗收項目通過後，**必須**產出報告檔並存至 `docs/gate-report-phase{N}.md`。報告未產出前，不得開始下一個 Phase。

### 7.1 報告必填結構

```markdown
# Gate Report — Phase {N}: {Phase 名稱}

**報告日期**：{YYYY-MM-DD}
**容器狀態快照**：`docker compose ps` 輸出

---

## 1. Gate 驗收結果

| 驗收項目 | 指令 / API | 實際回應 | 狀態 |
|---------|-------------|---------|------|
| (Gate 清單項依序填入) | | | ✅ / ❌ |

---

## 2. 實際完成的主要程式碼（引用真實程式碼）

**必須引用真實程式碼片段，不得僅述文字。**

### {檔案路徑}  （例：`backend/tasks/document_tasks.py` L48-L72）

```python
# 貼上實際完成的關鍵函數 / 類別，不得僅说「見所附檔案」
```

---

## 3. 踪踪的餕 — 除錯記錄

> 每個頕必須包含：錯誤現象描述、根本原因分析、修正後的實際程式碼。

### Pit #{N}：{簡這標題}

**現象**：
```
{error log 或報錯訊息，必須為真實輸出}
```

**根本原因**：

**修正**：
```diff
- {before}
+ {after}
```

---

## 4. 三庫一致性快照（每個涉及跌庫操作的 Phase 必填）

```
PostgreSQL：  SELECT id, status, chunk_count FROM documents WHERE id='{doc_id}';
              → {status=indexed, chunk_count=N}

Qdrant：      GET /collections/chunks
              → {points_count: N}

Neo4j：       MATCH (e:Entity)-[:MENTIONS]->(d:Document {id:'{doc_id}'}) RETURN count(e);
              → {count: N}
```

---

## 5. 容器健康快照

```
{docker compose ps 的實際輸出}
```

---

## 6. 下一個 Phase 備備事項

- (Phase N+1 開始前需要預備的事項)
```

### 7.2 報告資料來源規則

| 報告區塊 | 資料來源要求 |
|---------|-------------|
| Gate 驗收表格 | **必須報告實際驗收指令和回應**，不得僅勾選 |
| 主要程式碼 | **必須直接引用檔案路徑 + 行號 + 程式碼片段** |
| 除錯記錄 | **必須含真實 error log**，Pit 數量對應踪踪的餔 |
| 三庫快照 | **必須含 DB 查詢命令 + 真實輸出** |
| 容器快照 | **必須含 `docker compose ps` 真實輸出** |

### 7.3 報告存檔規則

```
docs/
  gate-report-phase0-1.md    ← Phase 0 + Phase 1 共用（已建立）
  gate-report-phase2.md      ← Phase 2（待補建）
  gate-report-phase3a.md
  gate-report-phase3b.md
  gate-report-phase3c.md
  gate-report-phase4.md
  gate-report-phase5.md
```

### 7.4 Phase 2 報告範例（已完成）

以下為 Gate 2 報告的將需庺入的程式碼引用范例：

**auth.py 修正（passlib 移除）**
```diff
# backend/auth.py
- from passlib.context import CryptContext
- pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
- def hash_password(p): return pwd_context.hash(p)
- def verify_password(p, h): return pwd_context.verify(p, h)
+ import bcrypt as _bcrypt
+ def hash_password(p): return _bcrypt.hashpw(p.encode(), _bcrypt.gensalt()).decode()
+ def verify_password(p, h): return _bcrypt.checkpw(p.encode(), h.encode())
```

**tasks/__init__.py 加入 init_saga_db**
```diff
# backend/tasks/__init__.py
+ from services.saga import init_saga_db
+ init_saga_db()   # 確保 saga_log 表存在
  celery_app = Celery(...)
```

**docker-compose.yml PYTHONPATH 修正**
```diff
  backend:
    env_file: .env
+   environment:
+     - PYTHONPATH=/app
  celery-worker:
    env_file: .env
+   environment:
+     - PYTHONPATH=/app
```

---

## 八、最低硬體規格

| 規格項目 | 最低（14b 4-bit）| 建議（72b 4-bit）|
|---------|----------------|----------------|
| RAM | 16 GB | 64 GB |
| GPU VRAM | 8 GB（RTX 3070）| 48 GB（A6000 / 雒14GB）|
| 磁碟空間 | 100 GB（SSD）| 500 GB（NVMe SSD）|
| CPU | 8 核 | 16 核 |

> CPU-only 模式：qwen2.5:7b 可在 16GB RAM 無 GPU 機器運行，速度約 2-5 tok/s。

---

## 九、資安邊界總結

| 風險點 | 對策 |
|--------|------|
| Plugin auth_header 洩漏 | Fernet 加密，金鑰僅存 .env |
| code_executor RCE | RestrictedPython + import 白名單 + 30s timeout |
| XSS token 竊取 | CSP header + DOMPurify sanitize（token 存 localStorage，透過 Pinia 統一管理）|
| CSRF | SameSite cookie 不適用（token 在 header），主要依賴 CORS 白名單 |
| 三庫資料不一致 | Saga 補償，任何跨 DB 操作必須登記 |
| LLM prompt injection | 使用者輸入先行 sanitize，禁止直接拼接至系統 prompt |
