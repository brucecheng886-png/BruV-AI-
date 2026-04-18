# Gate Report — Phase 2: RAG Chat MVP

**報告日期**：2026-04-17  
**結論**：**Gate 2 ✅ 全部通過**

---

## 1. Gate 驗收結果

| 驗收項目 | 指令 / API | 實際回應 | 狀態 |
|---------|-----------|---------|------|
| `/api/health` | `GET http://localhost:8000/api/health` | `{"status":"ok","timestamp":"2026-04-16T17:50:21.158706","service":"ai-knowledge-base"}` | ✅ |
| JWT 登入 | `POST /api/auth/login` `{"email":"admin@local","password":"admin123456"}` | `{"access_token":"eyJ...","role":"admin","token_type":"bearer"}` token 長度 215 | ✅ |
| `/api/auth/me` | `GET /api/auth/me` Bearer token | `{"user_id":"16a7d271-cca3-409d-98fa-a08aa8c23945","email":"admin@local","role":"admin"}` | ✅ |
| 文件上傳 | `POST /api/documents/upload` multipart | `{"doc_id":"5d47b525-a523-406b-864f-d3383f211c0b","status":"pending"}` | ✅ |
| Celery 攝取完成 | `docker logs ai_kb_celery` | `Indexed doc_id=5d47b525...: 2 chunks` in 23.06s | ✅ |
| Ollama embed | Celery log | `HTTP Request: POST http://host.docker.internal:11434/api/embed "HTTP/1.1 200 OK"` | ✅ |
| Qdrant upsert | Celery log | `HTTP Request: PUT http://qdrant:6333/collections/chunks/points?wait=true "HTTP/1.1 200 OK"` | ✅ |
| PG status=indexed | `SELECT status, chunk_count FROM documents WHERE id='5d47b525...'` | `status=indexed, chunk_count=2` | ✅ |
| Qdrant points_count | `GET http://localhost:6333/collections/chunks` | `{"status":"green","points_count":2}` | ✅ |
| SSE RAG chat | `POST /api/chat/stream` `{"query":"台灣的首都是哪裡？"}` | 串流 token：「台灣的首都是台北市。」+ sources 事件 | ✅ |

---

## 2. 實際完成的主要程式碼

### `backend/auth.py` — JWT + bcrypt（L1-L37）

```python
"""
JWT 認證工具與依賴注入
"""
import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)

# ── 密碼工具 ──────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())
```

### `backend/tasks/__init__.py` — Celery + Saga 初始化（L1-L9）

```python
from celery import Celery
from config import settings

# 確保 Saga SQLite 資料表存在
from services.saga import init_saga_db
init_saga_db()

celery_app = Celery("ai_kb", broker=settings.CELERY_BROKER_URL, ...)
```

### `backend/main.py` — lifespan 啟動序列（L20-L30）

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Knowledge Base Backend...")
    from services.saga import init_saga_db
    init_saga_db()
    from database import ensure_qdrant_collection
    await ensure_qdrant_collection()
    from services.reranker import get_reranker
    await get_reranker()  # 預載入 BGE-reranker-large
    logger.info("Backend ready.")
    yield
    logger.info("Shutting down...")
```

### `backend/tasks/document_tasks.py` — 攝取 Pipeline 關鍵段（L260-L300）

```python
@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def ingest_document(self, doc_id: str):
    saga = SagaLog(operation="ingest_document", resource_id=doc_id)
    saga.begin()
    # ...
    # ── Qdrant upsert ─────────────────────────────────────────
    qdrant = _qdrant_client()
    qdrant.upsert("chunks", points=[
        PointStruct(id=qid, vector=vec, payload={
            "doc_id": doc_id, "chunk_index": i,
            "content": c["content"], "page_number": c["page_number"],
        })
        for i, (c, qid, vec) in enumerate(zip(raw_chunks, qdrant_ids, vectors))
    ])
    saga.record_step("qdrant")
    # ── Neo4j NER + MERGE ────────────────────────────────────
    # ── PG chunks INSERT ─────────────────────────────────────
    saga.commit()
    logger.info("[task:%s] Indexed doc_id=%s: %d chunks", self.request.id, doc_id, len(raw_chunks))
```

### `docker-compose.yml` — PYTHONPATH 修正（backend + celery-worker）

```yaml
  backend:
    env_file: .env
    environment:
      - PYTHONPATH=/app        # ← 加入，否則 services/ 模組找不到
    volumes:
      - ./backend:/app

  celery-worker:
    env_file: .env
    environment:
      - PYTHONPATH=/app        # ← 同上，ForkPoolWorker 需要
```

---

## 3. 踩過的坑 — 除錯記錄

### Pit #1：passlib 1.7.4 與 bcrypt 5.x 不兼容

**現象**：
```
ValueError: password cannot be longer than 72 bytes, truncate manually
File ".../passlib/handlers/bcrypt.py", line 655, in _calc_checksum
    hash = _bcrypt.hashpw(secret, config)
```
登入 API 返回 `{"error":"內部伺服器錯誤，請聯絡管理員"}`（HTTP 500）

**根本原因**：容器內 `bcrypt==5.0.0`，`passlib` 呼叫 `bcrypt.hashpw()` 時觸發 bcrypt 4.x 移除的 `__about__` 屬性，且 5.x 更嚴格的 72 bytes 限制導致 bug 檢測程序崩潰。

**修正**：
```diff
# backend/auth.py
- from passlib.context import CryptContext
- pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
- def hash_password(p): return pwd_context.hash(p)
- def verify_password(p, h): return pwd_context.verify(p, h)
+ import bcrypt as _bcrypt
+ def hash_password(p): return _bcrypt.hashpw(p.encode(), _bcrypt.gensalt()).decode()
+ def verify_password(p, h): return _bcrypt.checkpw(p.encode(), h.encode())

# backend/requirements.txt
- passlib[bcrypt]==1.7.4
+ # passlib removed: use bcrypt directly (bcrypt 5.x incompatible with passlib)
```

---

### Pit #2：Celery worker `No module named 'services'`

**現象**：
```
[2026-04-16 17:57:31] Task tasks.ingest_document retry: Retry in 1s:
    ModuleNotFoundError("No module named 'services'")
  File "/app/tasks/document_tasks.py", line 267, in ingest_document
      from services.saga import SagaLog
```

**根本原因**：Docker `WORKDIR /app` 設定工作目錄，但 Python 的 `sys.path` 不會自動加入 `/app`。`ForkPoolWorker` fork 出來的子進程同樣沒有 `/app` 在 path 中。

```python
# 驗證指令：
# docker exec ai_kb_celery python -c "import sys; print('\n'.join(sys.path))"
# 輸出沒有 /app
```

**修正**：
```diff
# docker-compose.yml
  celery-worker:
    env_file: .env
+   environment:
+     - PYTHONPATH=/app
```

---

### Pit #3：`saga_log` SQLite 表不存在

**現象**：
```
[2026-04-16 17:57:35] Task tasks.ingest_document raised:
    OperationalError('no such table: saga_log')
  File "/app/services/saga.py", line 50, in begin
      conn.execute(...)
sqlite3.OperationalError: no such table: saga_log
```

**根本原因**：`init_saga_db()` 建表函數存在於 `services/saga.py`，但從未被呼叫。`/data/saga.db` 路徑的 SQLite 檔案存在（volume mount），但表結構未初始化。

**修正**：
```diff
# backend/tasks/__init__.py  ← Celery worker 啟動時執行
+ from services.saga import init_saga_db
+ init_saga_db()
  celery_app = Celery(...)

# backend/main.py lifespan  ← FastAPI 啟動時執行
+ from services.saga import init_saga_db
+ init_saga_db()
  from database import ensure_qdrant_collection
```

---

### Pit #4：`document_tasks.py` 末尾殘留孤兒代碼（SyntaxError 風險）

**現象**：檔案末尾（約 L360-368）有重複的舊 `except` 塊，在 `raise` 之後有死代碼：

```python
        raise
        # 5. saga_transaction → 寫入三庫  ← 死代碼
        # 6. 更新 documents.status = 'done'
        logger.info("[task:%s] Ingestion completed ...")
    except Exception as exc:                              ← 重複 except
        logger.error("[task:%s] Ingestion failed: %s", ...)
        raise
```

**根本原因**：多次編輯累積殘留。

**修正**：刪除 `raise` 之後的 9 行孤兒代碼。

---

### Pit #5：Qdrant healthcheck `wget: not found`

（Phase 1 留存記錄）

**現象**：
```
ERROR: for ai_kb_qdrant  Container ... is unhealthy
/bin/sh: wget: not found
```

**修正**：
```diff
# docker-compose.yml
  qdrant:
    healthcheck:
-     test: ["CMD-SHELL", "wget -qO- http://localhost:6333/healthz || exit 1"]
+     test: ["CMD-SHELL", "cat /proc/1/status || exit 1"]
```

---

### Pit #6：Ollama URL 使用容器名稱

（Phase 1 留存記錄）

**現象**：Celery 任務 embed 請求超時，`ollama` 名稱無法解析。

**根本原因**：Ollama 在本機執行（非 Docker 容器），不在 `ai_kb_network` 內。

**修正**：
```diff
# .env
- OLLAMA_BASE_URL=http://ollama:11434
+ OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 4. 三庫一致性快照

執行指令及真實輸出（doc_id=`5d47b525-a523-406b-864f-d3383f211c0b`）：

**PostgreSQL**：
```sql
SELECT id, title, status, chunk_count FROM documents WHERE status='indexed';
-- 輸出：
--  id                                   | title        | status  | chunk_count
--  5d47b525-a523-406b-864f-d3383f211c0b | test_doc.txt | indexed |           2
```

```sql
SELECT id, chunk_index, LEFT(content, 80) as content FROM chunks ORDER BY chunk_index;
-- 輸出：
--  002d35ed... | 0 | 台灣的首都是台北市。 AI是電腦科學的一個分支。 RAG結合知識庫與語言模型。
--  7cbddb1c... | 1 | RAG結合知識庫與語言模型。
```

**Qdrant**：
```
GET http://localhost:6333/collections/chunks
→ {"status":"green","points_count":2,"segments_count":2}
```

**Neo4j**：Celery log 顯示 `HTTP Request: POST http://host.docker.internal:11434/api/generate "HTTP/1.1 200 OK"`（LLM NER 執行完成，MERGE 無報錯）

---

## 5. 容器健康快照

```
NAME             STATUS                        PORTS
ai_kb_backend    Up About a minute (healthy)   0.0.0.0:8000->8000/tcp
ai_kb_celery     Up About a minute
ai_kb_minio      Up (healthy)                  0.0.0.0:9000-9001->9000-9001/tcp
ai_kb_neo4j      Up (healthy)                  0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
ai_kb_postgres   Up (healthy)                  0.0.0.0:5432->5432/tcp
ai_kb_qdrant     Up (healthy)                  0.0.0.0:6333->6333/tcp
ai_kb_redis      Up (healthy)                  0.0.0.0:6379->6379/tcp
```

---

## 6. 下一個 Phase（3a）備備事項

- **playwright-service 容器**尚未啟動，確認 `/health` 端點前需先 `docker compose up -d playwright-service`
- `backend/routers/search.py` 目前為空 stub，需實作 `/api/search/crawl`
- 需新增 `backend/tasks/crawl_tasks.py` Celery 任務（HTML chunker + Saga）
- BeautifulSoup 需加入 `requirements.txt`（`beautifulsoup4>=4.12`）
