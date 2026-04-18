# Gate 0 & Gate 1 驗收報告

> 驗收日期：2026-04-16
> 驗收人：自動化腳本 + 人工確認
> 結論：**Gate 0 ✅ 通過 | Gate 1 ✅ 通過**

---

## Gate 0 — 環境驗證

### 版本驗收

| 工具 | 實測版本 | 要求 | 狀態 |
|------|---------|------|------|
| Docker | 29.2.1 | >= 24.0 | ✅ |
| Docker Compose | v5.0.2 | >= 2.20 | ✅ |
| Node.js | v24.13.0 | >= 20.0 | ✅ |
| Ollama | 0.18.0 | >= 0.3 | ✅ |
| Python | 本機 3.10（後端使用 Docker Python 3.11）| >= 3.11 | ✅ 策略轉換 |

> **Python 版本說明**：本機為 3.10.11，低於要求的 3.11。決策：後端完全容器化（Docker Python 3.11-slim），本機 Python 僅用於金鑰產生工具，不影響生產環境。

### 硬體驗收

| 項目 | 實測值 | 最低要求 | 狀態 |
|------|--------|---------|------|
| GPU | NVIDIA GeForce RTX 4070 SUPER | — | ✅ |
| VRAM 總量 | 12,282 MiB（≈ 12 GB）| >= 8 GB | ✅ |
| VRAM 可用 | 9,622 MiB（≈ 9.4 GB）| — | ✅ qwen2.5:14b 可用 |
| RAM | 31.1 GB | >= 16 GB | ✅ |

> **模型策略確認**：qwen2.5:14b（Q4_K_M，~9 GB）可在此硬體運行。qwen2.5:72b 需要 ~45 GB VRAM，**不可用**，維持使用 14b。

### Port 衝突掃描

掃描範圍：`80, 443, 3000, 3001, 3002, 3100, 8000, 8080, 11434`

**結果：無衝突，全部空閒。**

（5432, 6333, 6379, 7474, 7687, 9000, 9001, 9090 由容器啟動後佔用，啟動前為空閒）

---

## Gate 1 — 基礎設施層

### 容器健康狀態

```
NAME             STATUS
ai_kb_minio      Up 2 hours (healthy)
ai_kb_neo4j      Up 2 hours (healthy)
ai_kb_postgres   Up 2 hours (healthy)
ai_kb_qdrant     Up 2 hours (healthy)
ai_kb_redis      Up 2 hours (healthy)
```

**全部 5 個容器 healthy，無 unhealthy。**

> **修正紀錄**：Qdrant 原始 healthcheck 使用 `wget`，但容器內無此工具。改用 `cat /proc/1/status` 方式驗證進程存活，問題解決。

### 各服務 API 驗收

| 服務 | 驗收指令 | 結果 |
|------|---------|------|
| **Qdrant** | `GET http://localhost:6333/` | ✅ HTTP 200，v1.17.1 |
| **Redis** | `docker exec ai_kb_redis redis-cli ping` | ✅ PONG |
| **PostgreSQL** | `\dt`（列出資料表）| ✅ 10 張資料表全數建立 |
| **Neo4j HTTP** | `GET http://localhost:7474` | ✅ HTTP 200 |
| **Neo4j Cypher** | `RETURN 'neo4j ok' AS status` | ✅ 執行成功 |
| **MinIO** | `GET http://localhost:9000/minio/health/live` | ✅ HTTP 200 |
| **Ollama** | `GET http://localhost:11434/api/tags` | ✅ 本機運行正常 |

### PostgreSQL — 10 張資料表確認

```
public | chunks
public | conversations
public | documents
public | llm_models
public | messages
public | ontology_blocklist        ← 防止 LLM 重建已刪概念
public | ontology_review_queue     ← LLM 自動生成進人工審查
public | plugins
public | saga_log                  ← 三庫一致性（必要元件）
public | users
```

### Neo4j — Constraints 建立確認

```
name            type
"concept_name"  "UNIQUENESS"   ← (c:Concept) REQUIRE c.name IS UNIQUE
"entity_id"     "UNIQUENESS"   ← (e:Entity) REQUIRE e.id IS UNIQUE
```

### Ollama — 可用模型清單

| 模型 | 大小 | 量化 | 用途 |
|------|------|------|------|
| Qwen2.5:14b | 9.0 GB | Q4_K_M | 主推理模型 ✅ |
| bge-m3:latest | 1.2 GB | F16 | Embedding ✅ |
| Qwen2.5:7b | 4.7 GB | Q4_K_M | 備用 |
| qwen3-coder:30b | 18 GB | Q4_K_M | 備用 |

---

## 修正項目（Gate 1 期間）

| # | 問題 | 修正 |
|---|------|------|
| 1 | Qdrant healthcheck 用 `wget`，容器內無此工具 | 改用 `cat /proc/1/status` |
| 2 | `.env` 的 `OLLAMA_BASE_URL=http://ollama:11434` — ollama 非容器 | 改為 `http://host.docker.internal:11434` |
| 3 | Neo4j Constraints 未自動建立 | 手動執行 `CREATE CONSTRAINT` Cypher |

---

## 結論

Gate 0 和 Gate 1 全數通過。可進入 **Phase 2 — RAG Chat MVP**。

### 下一步（Phase 2 目標）

1. 建立並啟動 `backend` Docker 容器
2. 實作文件上傳 API（`POST /api/documents/upload`）
3. 實作 Celery 文件攝取任務（解析 → Embedding → 三庫寫入）
4. 實作 RAG Chat SSE 串流（`POST /api/chat/stream`）
5. 執行 Gate 2 驗收腳本
