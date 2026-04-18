---
name: 執行準則
description: "地端 AI 知識庫的嚴謹執行準則。包含階段性驗收閘門、代碼自檢清單、錯誤處理標準、回滾程序。使用時機：開始寫任何模組代碼前、提交代碼前自檢、Phase 驗收前、遇到 bug 除錯時。"
argument-hint: "指定階段或模組，例如：Phase 1、代碼自檢、回滾程序"
---

# 地端 AI 知識庫 — 執行準則 v1.0

> 本準則定義：何時可以繼續、何時必須停下、寫完後必須檢查什麼。

---

## 一、基本原則（每次執行必讀）

1. **閘門優先**：每個 Phase 必須通過驗收閘門才能進入下一個
2. **先跑再寫**：新增任何代碼前，先確認依賴服務已啟動且健康
3. **最小可驗證單元**：每次只實作一個功能，立即測試，通過後再繼續
4. **錯誤必須顯性**：所有異常必須 log，不得靜默吞掉
5. **Saga 先行**：任何跨資料庫操作，必須先確認 Saga 日誌已初始化才執行

---

## 二、階段性驗收閘門

### Gate 0 — 環境驗證（Phase 0 結束前必須全部通過）

```bash
# 版本驗證（全部需符合）
docker --version          # >= 24.0
docker compose version    # >= 2.20
python --version          # >= 3.11
node --version            # >= 20.0
ollama --version          # >= 0.3

# Port 衝突掃描（以下 Port 必須全部空閒）
netstat -an | findstr "80 443 3000 3001 3002 3100 5432 6333 6379 7474 7687 8000 8080 9000 9001 9090 11434"

# 硬體驗證
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_properties(0).total_memory // 1024**3, 'GB')"
```

**閘門條件**：全部指令無錯誤，GPU VRAM >= 8GB（或確認使用 CPU-only 7b 模式）

---

### Gate 1 — 基礎設施（Phase 1 結束前）

```bash
# 所有容器必須 healthy
docker compose ps --format "table {{.Name}}\t{{.Status}}" | grep -v healthy

# 各服務健康檢查
curl -s http://localhost:11434/api/tags | python -m json.tool  # Ollama 有模型
curl -s http://localhost:6333/health                            # Qdrant ok
curl -s http://localhost:7474 -o /dev/null -w "%{http_code}"   # Neo4j 200
psql -U postgres -c "SELECT version();" 2>&1                   # PG 連線
redis-cli ping                                                  # PONG
curl -s http://localhost:9000/minio/health/live                 # MinIO ok
```

**閘門條件**：所有 curl 無錯誤，`docker compose ps` 無 unhealthy 容器

---

### Gate 2 — RAG MVP（Phase 2 結束前）

驗收腳本（依序執行，每步驟必須無錯誤）：
```bash
# 1. 上傳測試文件
curl -s -X POST http://localhost:8000/api/documents/upload \
  -F "file=@test.pdf" -H "Authorization: Bearer $TOKEN"
# → 回傳 { "doc_id": "xxx", "status": "pending" }

# 2. 輪詢處理狀態（最多等 120 秒）
for i in {1..24}; do
  STATUS=$(curl -s http://localhost:8000/api/documents/$DOC_ID/status | python -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  [ "$STATUS" = "done" ] && break
  sleep 5
done
[ "$STATUS" != "done" ] && echo "FAIL: Document processing timeout" && exit 1

# 3. 驗證三庫均有寫入
curl -s "http://localhost:6333/collections/chunks/points/count"   # Qdrant > 0
psql -U postgres -c "SELECT COUNT(*) FROM chunks WHERE doc_id='$DOC_ID';"  # PG > 0
cypher-shell -u neo4j "MATCH (d:Document {id:'$DOC_ID'}) RETURN d;"  # Neo4j 存在

# 4. RAG 對話測試（SSE）
curl -s -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "這份文件的主題是什麼？"}' \
  | head -20
# → 必須含 sources 欄位
```

**閘門條件**：三庫均有資料，SSE 回答含 `sources` 欄位

---

### Gate 3a — Playwright（Phase 3a 結束前）

```bash
# Playwright 服務健康
curl -s http://localhost:3002/health  # { "status": "ok" }

# 爬蟲功能測試
curl -s -X POST http://localhost:3002/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' | python -c "import sys,json; d=json.load(sys.stdin); assert 'text' in d and len(d['text']) > 50"

# 網頁攝取管線測試（透過 API）
curl -s -X POST http://localhost:8000/api/documents/upload \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' \
  -H "Authorization: Bearer $TOKEN"
```

**閘門條件**：爬蟲服務回應，網頁可透過 URL 上傳至知識庫

---

### Gate 3b — 插件（Phase 3b 結束前）

```bash
# 新增插件（含加密 auth_header）
curl -s -X POST http://localhost:8000/api/plugins \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"test","endpoint":"http://httpbin.org/post","auth_header":"Bearer test123","input_schema":{"type":"object"}}'

# 驗證 DB 中 auth_header 非明文
psql -U postgres -c "SELECT auth_header FROM plugins WHERE name='test';"
# → 必須是加密字串（gAAAAAB... 格式），不得是 "Bearer test123"

# 插件觸發測試
PLUGIN_ID=$(curl -s http://localhost:8000/api/plugins | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST http://localhost:8000/api/plugins/$PLUGIN_ID/test
```

**閘門條件**：DB 中 auth_header 為加密格式，插件測試回應成功

---

### Gate 3c — Agent（Phase 3c 結束前）

```bash
# Agent 任務執行測試
TASK_ID=$(curl -s -X POST http://localhost:8000/api/agent/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"instruction": "搜尋知識庫中關於機器學習的內容，並列出三個重點"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

# 輪詢任務狀態
sleep 30
curl -s http://localhost:8000/api/agent/tasks/$TASK_ID \
  | python -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='completed', f'Status: {d[\"status\"]}'"
```

**閘門條件**：Agent 任務完成，steps 日誌中包含 `knowledge_base_search` 的呼叫記錄

---

## 三、代碼自檢清單

> 每次寫完一個函式或模組後，逐項確認。不確定的項目必須測試後才能勾選。

### 3.1 安全性自檢

- [ ] **SQL Injection**：所有 DB 查詢使用參數化（`?` / `$1` 佔位），無字串拼接
- [ ] **Path Traversal**：檔案路徑操作使用 `pathlib.Path` + `resolve()`，驗證在允許目錄內
- [ ] **Secret 外洩**：沒有任何 key/token/password 硬編碼在程式碼中，全從 `os.environ` 讀取
- [ ] **輸入驗證**：所有 API endpoint 使用 Pydantic 模型，長度和格式有限制
- [ ] **Prompt Injection**：使用者輸入在送入 LLM 前已 sanitize（去除特殊控制序列）

### 3.2 一致性自檢

- [ ] **跨 DB 操作必有 Saga**：任何同時寫入 2+ 個資料庫的函式，必須有對應的補償函式
- [ ] **刪除有 cascade 邏輯**：刪除文件時確認 chunks、vectors、relations 都有對應清除
- [ ] **Qdrant payload 與 PG 同步**：修改 custom_fields 時確認走 `set_payload`，不走 re-embedding

### 3.3 API 設計自檢

- [ ] **HTTP 狀態碼正確**：
  - 200 OK（成功讀取）
  - 201 Created（成功建立）
  - 202 Accepted（非同步任務已接受）
  - 400 Bad Request（輸入格式錯誤）
  - 401 Unauthorized（未認證）
  - 403 Forbidden（無權限）
  - 404 Not Found（資源不存在）
  - 409 Conflict（資源已存在）
  - 422 Unprocessable Entity（Pydantic 驗證失敗，FastAPI 自動）
  - 500 Internal Server Error（系統錯誤）
- [ ] **非同步任務回傳 202 + task_id**，不得讓客戶端等待超過 5 秒
- [ ] **分頁參數**：列表 API 必須有 `limit`（預設 20，上限 100）和 `offset`

### 3.4 錯誤處理自檢

- [ ] **所有 except 必須 log**：`logger.error(...)` 含 exception info（`exc_info=True`）
- [ ] **外部服務呼叫必須 timeout**：Ollama / Qdrant / Neo4j / Playwright 呼叫都有 timeout 設定
- [ ] **Retry 有上限**：重試邏輯最多 3 次，exponential backoff，不得無限重試
- [ ] **Celery 任務有 max_retries**：`autoretry_for=(Exception,), max_retries=3, countdown=5`

### 3.5 效能自檢

- [ ] **N+1 查詢檢查**：列表 API 不得在迴圈中發出多次 DB 查詢，使用 JOIN 或批量查詢
- [ ] **向量查詢有 limit**：Qdrant search 有 `limit` 參數，不得取出全部向量
- [ ] **LLM 呼叫有快取**：相同問題在 TTL 內直接回傳 Redis 快取，不重複推理

---

## 四、標準錯誤處理模板

### 4.1 FastAPI Exception Handler
```python
# backend/main.py
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc) if app.debug else "請聯絡管理員"}
    )
```

### 4.2 Celery 任務標準模板
```python
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), max_retries=3,
             retry_backoff=True, retry_backoff_max=60)
def process_document(self, doc_id: str):
    logger.info(f"[task:{self.request.id}] Processing document {doc_id}")
    try:
        # ... 業務邏輯 ...
        pass
    except Exception as exc:
        logger.error(f"[task:{self.request.id}] Failed: {exc}", exc_info=True)
        raise  # 讓 Celery 的 autoretry 接管
```

### 4.3 Saga 操作標準模板
```python
from contextlib import contextmanager
from services.saga import SagaLog

@contextmanager
def saga_transaction(operation: str, doc_id: str):
    saga = SagaLog(operation=operation, doc_id=doc_id)
    saga.begin()
    completed_steps = []
    try:
        yield completed_steps
        saga.commit()
    except Exception as exc:
        logger.error(f"Saga failed at step {len(completed_steps)}: {exc}", exc_info=True)
        saga.compensate(completed_steps)
        saga.mark_compensated()
        raise RuntimeError(f"Transaction rolled back: {exc}") from exc
```

---

## 五、除錯程序（遇到問題時依序執行）

```
Step 1 — 確認錯誤層級
  容器本身掛掉？   → docker compose logs <service> --tail=50
  API 回傳錯誤？   → 看 backend logs + HTTP status code
  資料不一致？     → 查 saga_log 表 status='COMPENSATED' 記錄
  效能問題？       → Grafana Dashboard → 找瓶頸服務

Step 2 — 隔離問題範圍
  單一服務測試：直接呼叫該服務的原始 API（不透過 backend）
  例：Qdrant 問題 → curl http://localhost:6333/...
      Neo4j 問題  → 直接開 http://localhost:7474 執行 Cypher
      LLM 問題    → curl http://localhost:11434/api/generate

Step 3 — 復原順序
  先停止問題服務：docker compose stop <service>
  清除損壞狀態：  docker compose rm -f <service>
  重啟並驗證：    docker compose up -d <service> && docker compose ps
  驗收閘門重跑：  執行對應 Gate 的驗證腳本
```

---

## 六、禁止清單（永不做以下事情）

| 禁止行為 | 原因 |
|---------|------|
| 直接在程式碼中硬編碼 API Key / 密碼 | 洩漏風險，git commit 後無法撤回 |
| 跨 DB 操作不走 Saga | 會產生永久的資料不一致 |
| `except: pass` 靜默吞掉異常 | 讓 bug 沉默，難以排查 |
| 在 LLM prompt 中直接拼接使用者輸入 | Prompt injection 攻擊面 |
| 未通過當前 Phase Gate 就進入下一個 Phase | 後面的 Phase 依賴前面的基礎 |
| 刪除資料不確認依賴關係 | 孤兒節點和向量洩漏 |
| 列表 API 不加 limit | 可能回傳整個資料庫內容 |
| 外部服務呼叫不設 timeout | 一個服務卡住導致整個請求鏈堵死 |

---

## 七、Phase 進度追蹤格式

每次繼續實作前，先在對話開頭聲明當前狀態：

```
當前 Phase：[Phase X]
已通過閘門：[Gate 0, Gate 1, ...]
當前實作：[模組名稱 / 函式名稱]
未解問題：[列出已知但尚未解決的問題]
```
