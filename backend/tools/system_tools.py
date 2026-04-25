"""
System Tools — Agent 可呼叫的系統管理工具

工具清單：
  # 文件查詢
  search_documents            — 搜尋文件列表（依標題 / KB 名稱 / 狀態）
  get_document_stats          — 統計各狀態文件數量
  diagnose_stuck_documents    — 找出卡住 > N 分鐘的文件
  semantic_search_documents   — AI 語意搜尋相關文件
  list_trash_documents        — 列出垃圾桶文件

  # 文件操作
  reprocess_document          — 重新處理失敗/卡住的文件
  batch_reprocess_failed      — 批次重處理所有 failed 文件
  rename_document             — 修改文件標題
  soft_delete_document        — 將文件移入垃圾桶
  restore_document            — 從垃圾桶還原文件
  move_document_to_kb         — 將文件移動到指定知識庫
  crawl_url                   — 爬取指定 URL 並建立文件

  # 永久刪除（原有）
  delete_document             — 永久刪除文件（PG + Qdrant + MinIO）

  # 知識庫管理
  create_knowledge_base       — 建立新知識庫
  update_knowledge_base       — 更新知識庫名稱/描述
  delete_knowledge_base       — 刪除知識庫（文件保留）
  list_knowledge_bases        — 列出所有知識庫及文件數量
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

import psycopg2
import psycopg2.extras
from langchain.tools import Tool

from config import settings

logger = logging.getLogger(__name__)


def _get_pg_conn():
    """取得同步 psycopg2 連線"""
    return psycopg2.connect(settings.DATABASE_URL.replace("+asyncpg", ""))


# ────────────────────────────────────────────────────────────────
# 工具 1：search_documents
# ────────────────────────────────────────────────────────────────
def search_documents(query: str = "") -> str:
    """
    搜尋知識庫中的文件列表。
    輸入格式：「關鍵字」或「kb:知識庫名稱」或「status:failed」或空字串（列出所有）
    """
    try:
        kb_filter = None
        title_filter = None
        status_filter = None

        # 解析輸入
        q = query.strip()
        if q.lower().startswith("kb:"):
            kb_filter = q[3:].strip()
        elif q.lower().startswith("status:"):
            status_filter = q[7:].strip()
        elif q:
            title_filter = q

        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT d.id, d.title, d.status, d.chunk_count,
                           kb.name AS kb_name, d.created_at, d.error_message
                    FROM documents d
                    LEFT JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                    WHERE d.deleted_at IS NULL
                """
                params = []
                if title_filter:
                    sql += " AND d.title ILIKE %s"
                    params.append(f"%{title_filter}%")
                if kb_filter:
                    sql += " AND kb.name ILIKE %s"
                    params.append(f"%{kb_filter}%")
                if status_filter:
                    sql += " AND d.status = %s"
                    params.append(status_filter)
                sql += " ORDER BY d.created_at DESC LIMIT 20"

                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return "找不到符合條件的文件。"

        lines = [f"找到 {len(rows)} 篇文件：\n"]
        for r in rows:
            kb = r["kb_name"] or "未分類"
            status = r["status"] or "unknown"
            chunks = r["chunk_count"] or 0
            date = str(r["created_at"])[:10] if r["created_at"] else "?"
            err = f" | ❌ {r['error_message'][:60]}" if r.get("error_message") else ""
            lines.append(f"• [{r['id']}] {r['title']}")
            lines.append(f"  知識庫：{kb} | 狀態：{status} | {chunks} chunks | {date}{err}")
        return "\n".join(lines)

    except Exception as e:
        logger.error("search_documents 失敗: %s", e, exc_info=True)
        return f"搜尋文件失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 2：delete_document
# ────────────────────────────────────────────────────────────────
def delete_document(doc_id: str) -> str:
    """
    刪除指定文件（含 Qdrant 向量、MinIO 原檔）。
    輸入：文件 ID（完整 UUID）
    """
    doc_id = doc_id.strip()
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 確認文件存在
                cur.execute("SELECT id, title, file_path FROM documents WHERE id = %s", (doc_id,))
                doc = cur.fetchone()
                if not doc:
                    return f"找不到 ID 為「{doc_id}」的文件，請確認 ID 是否正確。"

                title = doc["title"]
                file_path = doc["file_path"]

                # 取得 Qdrant vector_ids
                cur.execute(
                    "SELECT vector_id FROM chunks WHERE doc_id = %s AND vector_id IS NOT NULL",
                    (doc_id,),
                )
                vector_ids = [row["vector_id"] for row in cur.fetchall()]

                # 刪除 Qdrant
                if vector_ids:
                    try:
                        from qdrant_client import QdrantClient
                        qdrant = QdrantClient(
                            host=settings.QDRANT_HOST,
                            port=settings.QDRANT_PORT,
                        )
                        qdrant.delete(
                            collection_name=settings.QDRANT_COLLECTION,
                            points_selector=vector_ids,
                        )
                    except Exception as qe:
                        logger.warning("Qdrant 刪除失敗（繼續）: %s", qe)

                # 刪除 MinIO
                if file_path:
                    try:
                        from services.storage import delete_file as minio_delete
                        minio_delete(file_path)
                    except Exception as me:
                        logger.warning("MinIO 刪除失敗（繼續）: %s", me)

                # 刪除 PG（CASCADE 會刪 chunks / tags 關聯）
                cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                conn.commit()
        finally:
            conn.close()

        return f"文件「{title}」（{doc_id}）已成功刪除。"

    except Exception as e:
        logger.error("delete_document 失敗: %s", e, exc_info=True)
        return f"刪除文件失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 3：create_knowledge_base
# ────────────────────────────────────────────────────────────────
def create_knowledge_base(name_and_desc: str) -> str:
    """
    建立新的知識庫。
    輸入格式：「名稱」或「名稱|描述」
    """
    parts = name_and_desc.split("|", 1)
    name = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else None

    if not name:
        return "請提供知識庫名稱。"

    try:
        kb_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                # 檢查名稱是否重複
                cur.execute("SELECT id FROM knowledge_bases WHERE name = %s", (name,))
                if cur.fetchone():
                    return f"知識庫「{name}」已存在，請使用其他名稱。"

                cur.execute(
                    """
                    INSERT INTO knowledge_bases (id, name, description, icon, color, created_at)
                    VALUES (%s, %s, %s, '📚', '#409eff', %s)
                    """,
                    (kb_id, name, description, now),
                )
                conn.commit()
        finally:
            conn.close()

        desc_info = f"，描述：{description}" if description else ""
        return f"知識庫「{name}」已建立（ID：{kb_id[:8]}...{desc_info}）。"

    except Exception as e:
        logger.error("create_knowledge_base 失敗: %s", e, exc_info=True)
        return f"建立知識庫失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 4：list_knowledge_bases
# ────────────────────────────────────────────────────────────────
def list_knowledge_bases(_input: str = "") -> str:
    """列出所有知識庫及其文件數量。輸入：忽略"""
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT kb.id, kb.name, kb.description,
                           COUNT(d.id) AS doc_count
                    FROM knowledge_bases kb
                    LEFT JOIN documents d ON d.knowledge_base_id = kb.id
                    GROUP BY kb.id, kb.name, kb.description
                    ORDER BY doc_count DESC, kb.name
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return "目前沒有任何知識庫。"

        lines = [f"共 {len(rows)} 個知識庫：\n"]
        for r in rows:
            desc = f"（{r['description']}）" if r["description"] else ""
            lines.append(f"• {r['name']}{desc} — {r['doc_count']} 篇文件 [ID: {str(r['id'])[:8]}...]")
        return "\n".join(lines)

    except Exception as e:
        logger.error("list_knowledge_bases 失敗: %s", e, exc_info=True)
        return f"列出知識庫失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 5：get_document_stats
# ────────────────────────────────────────────────────────────────
def get_document_stats(_input: str = "") -> str:
    """
    統計系統內各狀態的文件數量，快速掌握整體健康狀況。
    輸入：忽略（可傳空字串）
    """
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE deleted_at IS NULL) AS total,
                        COUNT(*) FILTER (WHERE status = 'done' AND deleted_at IS NULL) AS done,
                        COUNT(*) FILTER (WHERE status = 'pending' AND deleted_at IS NULL) AS pending,
                        COUNT(*) FILTER (WHERE status = 'processing' AND deleted_at IS NULL) AS processing,
                        COUNT(*) FILTER (WHERE status = 'failed' AND deleted_at IS NULL) AS failed,
                        COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS in_trash
                    FROM documents
                """)
                row = cur.fetchone()
                cur.execute("""
                    SELECT COUNT(*) AS kb_count FROM knowledge_bases
                """)
                kb_row = cur.fetchone()
        finally:
            conn.close()

        return (
            f"📊 文件庫狀態總覽：\n"
            f"• 總文件數：{row['total']} 篇\n"
            f"• ✅ 已完成（done）：{row['done']} 篇\n"
            f"• ⏳ 等待處理（pending）：{row['pending']} 篇\n"
            f"• 🔄 處理中（processing）：{row['processing']} 篇\n"
            f"• ❌ 失敗（failed）：{row['failed']} 篇\n"
            f"• 🗑️ 垃圾桶：{row['in_trash']} 篇\n"
            f"• 📚 知識庫數量：{kb_row['kb_count']} 個"
        )
    except Exception as e:
        logger.error("get_document_stats 失敗: %s", e, exc_info=True)
        return f"取得統計資料失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 6：diagnose_stuck_documents
# ────────────────────────────────────────────────────────────────
def diagnose_stuck_documents(minutes_str: str = "30") -> str:
    """
    找出卡住超過指定分鐘數的文件（狀態為 pending 或 processing）。
    輸入：等待分鐘數（預設 30），例如 "30" 或 "60"
    """
    try:
        minutes = int(minutes_str.strip()) if minutes_str.strip().isdigit() else 30
    except Exception:
        minutes = 30

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT d.id, d.title, d.status, d.chunk_count,
                           d.error_message, d.created_at,
                           kb.name AS kb_name
                    FROM documents d
                    LEFT JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                    WHERE d.status IN ('pending', 'processing')
                      AND d.created_at < %s
                      AND d.deleted_at IS NULL
                    ORDER BY d.created_at ASC
                    LIMIT 20
                """, (cutoff,))
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return f"✅ 沒有卡住超過 {minutes} 分鐘的文件，系統處理正常。"

        lines = [f"⚠️ 發現 {len(rows)} 篇文件卡住超過 {minutes} 分鐘：\n"]
        for r in rows:
            elapsed = datetime.now(timezone.utc) - r["created_at"].replace(tzinfo=timezone.utc)
            hours = int(elapsed.total_seconds() // 3600)
            mins = int((elapsed.total_seconds() % 3600) // 60)
            kb = r["kb_name"] or "未分類"
            err = f" | 錯誤：{r['error_message'][:80]}" if r["error_message"] else ""
            lines.append(
                f"• [{r['id'][:8]}...] {r['title']}\n"
                f"  狀態：{r['status']} | 卡住：{hours}h{mins}m | KB：{kb}{err}"
            )
        lines.append(f"\n💡 建議：使用 reprocess_document 傳入文件 ID 重新處理，或使用 batch_reprocess_failed 批次處理。")
        return "\n".join(lines)

    except Exception as e:
        logger.error("diagnose_stuck_documents 失敗: %s", e, exc_info=True)
        return f"診斷失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 7：reprocess_document
# ────────────────────────────────────────────────────────────────
def reprocess_document(doc_id: str) -> str:
    """
    重新處理指定文件（重設狀態為 pending 並重新觸發 Celery 攝取任務）。
    適用於：status = failed、processing 卡住、done 但 chunk_count = 0 的文件。
    輸入：文件的完整 UUID
    """
    doc_id = doc_id.strip()
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, title, status, file_path FROM documents WHERE id = %s",
                    (doc_id,)
                )
                doc = cur.fetchone()
                if not doc:
                    return f"找不到 ID 為「{doc_id}」的文件。"
                if not doc["file_path"]:
                    return f"文件「{doc['title']}」無原始檔案（來源為網頁爬取），無法重新分析。"

                cur.execute("""
                    UPDATE documents
                    SET status = 'pending', error_message = NULL, chunk_count = 0
                    WHERE id = %s
                """, (doc_id,))
                conn.commit()
        finally:
            conn.close()

        from tasks.document_tasks import ingest_document
        ingest_document.delay(doc_id)
        return f"✅ 文件「{doc['title']}」已重設為 pending，Celery 任務已觸發。"

    except Exception as e:
        logger.error("reprocess_document 失敗: %s", e, exc_info=True)
        return f"重新處理失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 8：batch_reprocess_failed
# ────────────────────────────────────────────────────────────────
def batch_reprocess_failed(_input: str = "") -> str:
    """
    批次重新處理所有狀態為 failed 且有原始檔案的文件。
    輸入：忽略（可傳空字串）
    """
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, title FROM documents
                    WHERE status = 'failed'
                      AND file_path IS NOT NULL
                      AND deleted_at IS NULL
                    LIMIT 50
                """)
                rows = cur.fetchall()

                if not rows:
                    return "✅ 目前沒有狀態為 failed 的文件需要重新處理。"

                ids = [r["id"] for r in rows]
                cur.execute("""
                    UPDATE documents
                    SET status = 'pending', error_message = NULL, chunk_count = 0
                    WHERE id = ANY(%s)
                """, (ids,))
                conn.commit()
        finally:
            conn.close()

        from tasks.document_tasks import ingest_document
        for doc_id in ids:
            ingest_document.delay(doc_id)

        names = "、".join(r["title"][:20] for r in rows[:5])
        suffix = f" 等 {len(rows)} 篇" if len(rows) > 5 else ""
        return f"✅ 已觸發重新處理：{names}{suffix}。所有文件狀態已重設為 pending。"

    except Exception as e:
        logger.error("batch_reprocess_failed 失敗: %s", e, exc_info=True)
        return f"批次重新處理失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 9：rename_document
# ────────────────────────────────────────────────────────────────
def rename_document(input_str: str) -> str:
    """
    修改文件標題。
    輸入格式：「文件ID|新標題」（以 | 分隔）
    例如：「550e8400-...|新的文件名稱」
    """
    parts = input_str.split("|", 1)
    if len(parts) != 2:
        return "輸入格式錯誤，請使用「文件ID|新標題」格式。"

    doc_id = parts[0].strip()
    new_title = parts[1].strip()
    if not new_title:
        return "新標題不能為空。"

    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT title FROM documents WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                if not row:
                    return f"找不到 ID 為「{doc_id}」的文件。"
                old_title = row[0]
                cur.execute(
                    "UPDATE documents SET title = %s WHERE id = %s",
                    (new_title, doc_id)
                )
                conn.commit()
        finally:
            conn.close()

        return f"✅ 文件標題已從「{old_title}」改為「{new_title}」。"

    except Exception as e:
        logger.error("rename_document 失敗: %s", e, exc_info=True)
        return f"修改標題失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 10：soft_delete_document
# ────────────────────────────────────────────────────────────────
def soft_delete_document(doc_id: str) -> str:
    """
    將文件移入垃圾桶（軟刪除，保留向量與原始檔案，可還原）。
    輸入：文件的完整 UUID
    """
    doc_id = doc_id.strip()
    try:
        now = datetime.now(timezone.utc)
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT title, deleted_at FROM documents WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                if not row:
                    return f"找不到 ID 為「{doc_id}」的文件。"
                if row[1] is not None:
                    return f"文件「{row[0]}」已在垃圾桶中。"
                cur.execute(
                    "UPDATE documents SET deleted_at = %s WHERE id = %s",
                    (now, doc_id)
                )
                conn.commit()
                title = row[0]
        finally:
            conn.close()

        return f"🗑️ 文件「{title}」已移入垃圾桶，可使用 restore_document 還原。"

    except Exception as e:
        logger.error("soft_delete_document 失敗: %s", e, exc_info=True)
        return f"移入垃圾桶失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 11：restore_document
# ────────────────────────────────────────────────────────────────
def restore_document(doc_id: str) -> str:
    """
    從垃圾桶還原文件。
    輸入：文件的完整 UUID
    """
    doc_id = doc_id.strip()
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT title, deleted_at FROM documents WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                if not row:
                    return f"找不到 ID 為「{doc_id}」的文件。"
                if row[1] is None:
                    return f"文件「{row[0]}」不在垃圾桶中，無需還原。"
                cur.execute(
                    "UPDATE documents SET deleted_at = NULL WHERE id = %s",
                    (doc_id,)
                )
                conn.commit()
                title = row[0]
        finally:
            conn.close()

        return f"✅ 文件「{title}」已從垃圾桶還原。"

    except Exception as e:
        logger.error("restore_document 失敗: %s", e, exc_info=True)
        return f"還原文件失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 12：move_document_to_kb
# ────────────────────────────────────────────────────────────────
def move_document_to_kb(input_str: str) -> str:
    """
    將文件移動到指定知識庫（或從知識庫移出）。
    輸入格式：「文件ID|知識庫ID」，若要移出知識庫則傳「文件ID|none」
    例如：「550e8400-...|kb-uuid-...」
    """
    parts = input_str.split("|", 1)
    if len(parts) != 2:
        return "輸入格式錯誤，請使用「文件ID|知識庫ID」格式，移出知識庫請傳「文件ID|none」。"

    doc_id = parts[0].strip()
    kb_id = parts[1].strip()
    kb_id_val = None if kb_id.lower() == "none" else kb_id

    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT title FROM documents WHERE id = %s", (doc_id,))
                doc_row = cur.fetchone()
                if not doc_row:
                    return f"找不到 ID 為「{doc_id}」的文件。"

                kb_name = "（無）"
                if kb_id_val:
                    cur.execute("SELECT name FROM knowledge_bases WHERE id = %s", (kb_id_val,))
                    kb_row = cur.fetchone()
                    if not kb_row:
                        return f"找不到 ID 為「{kb_id_val}」的知識庫，請先確認知識庫 ID。"
                    kb_name = kb_row["name"]

                # 更新 documents FK
                cur.execute(
                    "UPDATE documents SET knowledge_base_id = %s WHERE id = %s",
                    (kb_id_val, doc_id)
                )
                # 同步 M2M 表
                cur.execute(
                    "DELETE FROM document_knowledge_bases WHERE doc_id = %s",
                    (doc_id,)
                )
                if kb_id_val:
                    cur.execute(
                        """
                        INSERT INTO document_knowledge_bases (doc_id, kb_id, source)
                        VALUES (%s, %s, 'manual')
                        ON CONFLICT DO NOTHING
                        """,
                        (doc_id, kb_id_val)
                    )
                conn.commit()
        finally:
            conn.close()

        action = f"移動到知識庫「{kb_name}」" if kb_id_val else "從知識庫移出"
        return f"✅ 文件「{doc_row['title']}」已{action}。"

    except Exception as e:
        logger.error("move_document_to_kb 失敗: %s", e, exc_info=True)
        return f"移動文件失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 13：list_trash_documents
# ────────────────────────────────────────────────────────────────
def list_trash_documents(_input: str = "") -> str:
    """
    列出垃圾桶中的文件。
    輸入：忽略（可傳空字串）
    """
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT d.id, d.title, d.status, d.chunk_count,
                           d.deleted_at, kb.name AS kb_name
                    FROM documents d
                    LEFT JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                    WHERE d.deleted_at IS NOT NULL
                    ORDER BY d.deleted_at DESC
                    LIMIT 30
                """)
                rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return "🗑️ 垃圾桶是空的。"

        lines = [f"🗑️ 垃圾桶共 {len(rows)} 篇文件：\n"]
        for r in rows:
            kb = r["kb_name"] or "未分類"
            date = str(r["deleted_at"])[:10]
            lines.append(f"• [{r['id'][:8]}...] {r['title']}")
            lines.append(f"  知識庫：{kb} | 刪除日期：{date}")
        return "\n".join(lines)

    except Exception as e:
        logger.error("list_trash_documents 失敗: %s", e, exc_info=True)
        return f"列出垃圾桶失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 14：crawl_url
# ────────────────────────────────────────────────────────────────
def crawl_url(input_str: str) -> str:
    """
    爬取指定 URL 並建立文件（加入知識庫可選）。
    輸入格式：「URL」或「URL|知識庫ID」或「URL|知識庫ID|標題」
    例如：「https://example.com/article」
          「https://example.com/article|kb-uuid-...|文章標題」
    """
    parts = input_str.split("|")
    url = parts[0].strip()
    kb_id = parts[1].strip() if len(parts) > 1 else None
    title = parts[2].strip() if len(parts) > 2 else url[:100]

    if not url.startswith(("http://", "https://")):
        return "URL 格式錯誤，必須以 http:// 或 https:// 開頭。"

    blocked = ["facebook.com", "youtube.com", "youtu.be", "google.com/drive", "drive.google.com"]
    for b in blocked:
        if b in url.lower():
            return f"URL 包含不支援的網域（{b}），請使用其他來源。"

    try:
        doc_id = str(uuid.uuid4())
        kb_id_val = kb_id if kb_id and kb_id.lower() != "none" else None

        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                if kb_id_val:
                    cur.execute("SELECT id FROM knowledge_bases WHERE id = %s", (kb_id_val,))
                    if not cur.fetchone():
                        return f"找不到知識庫 ID「{kb_id_val}」。"

                cur.execute("""
                    INSERT INTO documents (id, title, source, file_type, status, knowledge_base_id)
                    VALUES (%s, %s, %s, 'html', 'pending', %s)
                """, (doc_id, title, url, kb_id_val))

                if kb_id_val:
                    cur.execute("""
                        INSERT INTO document_knowledge_bases (doc_id, kb_id, source)
                        VALUES (%s, %s, 'manual')
                        ON CONFLICT DO NOTHING
                    """, (doc_id, kb_id_val))
                conn.commit()
        finally:
            conn.close()

        from tasks.crawl_tasks import crawl_document
        crawl_document.delay(doc_id, url)

        return (
            f"✅ 已建立爬取任務：\n"
            f"• 標題：{title}\n"
            f"• URL：{url}\n"
            f"• 文件 ID：{doc_id}\n"
            f"• 知識庫：{kb_id_val or '未分類'}\n"
            f"系統正在後台爬取，稍後可用 search_documents 查詢結果。"
        )

    except Exception as e:
        logger.error("crawl_url 失敗: %s", e, exc_info=True)
        return f"建立爬取任務失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 15：update_knowledge_base
# ────────────────────────────────────────────────────────────────
def update_knowledge_base(input_str: str) -> str:
    """
    更新知識庫的名稱和描述。
    輸入格式：「知識庫ID|新名稱」或「知識庫ID|新名稱|新描述」
    例如：「kb-uuid-...|風能研究|風力發電相關文獻」
    """
    parts = input_str.split("|")
    if len(parts) < 2:
        return "輸入格式錯誤，請使用「知識庫ID|新名稱」或「知識庫ID|新名稱|新描述」格式。"

    kb_id = parts[0].strip()
    new_name = parts[1].strip()
    new_desc = parts[2].strip() if len(parts) > 2 else None

    if not new_name:
        return "新名稱不能為空。"

    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM knowledge_bases WHERE id = %s", (kb_id,))
                row = cur.fetchone()
                if not row:
                    return f"找不到 ID 為「{kb_id}」的知識庫。"
                old_name = row[0]

                if new_desc is not None:
                    cur.execute(
                        "UPDATE knowledge_bases SET name = %s, description = %s WHERE id = %s",
                        (new_name, new_desc, kb_id)
                    )
                else:
                    cur.execute(
                        "UPDATE knowledge_bases SET name = %s WHERE id = %s",
                        (new_name, kb_id)
                    )
                conn.commit()
        finally:
            conn.close()

        desc_info = f"，描述：{new_desc}" if new_desc else ""
        return f"✅ 知識庫名稱已從「{old_name}」改為「{new_name}」{desc_info}。"

    except Exception as e:
        logger.error("update_knowledge_base 失敗: %s", e, exc_info=True)
        return f"更新知識庫失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具 16：delete_knowledge_base
# ────────────────────────────────────────────────────────────────
def delete_knowledge_base(kb_id: str) -> str:
    """
    刪除知識庫（文件不會被刪除，僅解除關聯）。
    輸入：知識庫的完整 UUID
    ⚠️ 此操作不可復原。
    """
    kb_id = kb_id.strip()
    try:
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM knowledge_bases WHERE id = %s", (kb_id,))
                row = cur.fetchone()
                if not row:
                    return f"找不到 ID 為「{kb_id}」的知識庫。"
                name = row[0]

                cur.execute(
                    "UPDATE documents SET knowledge_base_id = NULL WHERE knowledge_base_id = %s",
                    (kb_id,)
                )
                cur.execute("DELETE FROM knowledge_bases WHERE id = %s", (kb_id,))
                conn.commit()
        finally:
            conn.close()

        return f"✅ 知識庫「{name}」已刪除，其文件已保留但移出知識庫。"

    except Exception as e:
        logger.error("delete_knowledge_base 失敗: %s", e, exc_info=True)
        return f"刪除知識庫失敗：{e}"


# ────────────────────────────────────────────────────────────────
# 工具建構函式
# ────────────────────────────────────────────────────────────────
def build_system_tools() -> list[Tool]:
    return [
        # ── 查詢類 ──────────────────────────────────────────
        Tool(
            name="search_documents",
            func=search_documents,
            description=(
                "搜尋知識庫中的文件列表，可依標題或知識庫名稱過濾。"
                "輸入：搜尋關鍵字，或「kb:知識庫名稱」以篩選特定知識庫，"
                "或「status:failed」以篩選特定狀態，"
                "或空字串以列出最近 20 篇文件。"
                "輸出：文件 ID、標題、知識庫、狀態、chunk 數、日期。"
            ),
        ),
        Tool(
            name="get_document_stats",
            func=get_document_stats,
            description=(
                "取得系統文件庫的整體統計數據：各狀態數量（done/pending/processing/failed）、"
                "垃圾桶數量、知識庫數量。輸入：不需要任何輸入。"
                "建議在開始分析問題前先呼叫此工具。"
            ),
        ),
        Tool(
            name="diagnose_stuck_documents",
            func=diagnose_stuck_documents,
            description=(
                "找出卡在 pending 或 processing 狀態超過指定分鐘數的文件。"
                "輸入：等待分鐘數（預設 30），例如傳入「30」或「60」。"
                "輸出：卡住文件清單及建議操作。"
            ),
        ),
        Tool(
            name="list_trash_documents",
            func=list_trash_documents,
            description=(
                "列出垃圾桶中已軟刪除的文件。"
                "輸入：不需要任何輸入。"
                "輸出：垃圾桶文件清單（最多 30 篇）。"
            ),
        ),
        Tool(
            name="list_knowledge_bases",
            func=list_knowledge_bases,
            description=(
                "列出系統中所有知識庫及其文件數量。"
                "輸入：不需要任何輸入（可傳空字串）。"
                "輸出：知識庫名稱、描述、文件數量。"
            ),
        ),

        # ── 文件操作類 ───────────────────────────────────────
        Tool(
            name="reprocess_document",
            func=reprocess_document,
            description=(
                "重新處理指定文件（重設為 pending 並重觸 Celery 任務）。"
                "適用於 status=failed、processing 卡住、chunk_count=0 的文件。"
                "輸入：文件的完整 UUID（可從 search_documents 或 diagnose_stuck_documents 取得）。"
            ),
        ),
        Tool(
            name="batch_reprocess_failed",
            func=batch_reprocess_failed,
            description=(
                "批次重新處理所有 status=failed 且有原始檔案的文件（最多 50 篇）。"
                "輸入：不需要任何輸入。"
            ),
        ),
        Tool(
            name="rename_document",
            func=rename_document,
            description=(
                "修改文件的顯示標題。"
                "輸入格式：「文件ID|新標題」（以 | 分隔），"
                "例如：「550e8400-...|2026 年能源報告」。"
            ),
        ),
        Tool(
            name="soft_delete_document",
            func=soft_delete_document,
            description=(
                "將文件移入垃圾桶（軟刪除，保留原始資料，可用 restore_document 還原）。"
                "輸入：文件的完整 UUID。"
            ),
        ),
        Tool(
            name="restore_document",
            func=restore_document,
            description=(
                "從垃圾桶還原文件（清除 deleted_at 使文件重新顯示）。"
                "輸入：文件的完整 UUID（可從 list_trash_documents 取得）。"
            ),
        ),
        Tool(
            name="move_document_to_kb",
            func=move_document_to_kb,
            description=(
                "將文件移動到指定知識庫（同步更新多對多關聯表）。"
                "輸入格式：「文件ID|知識庫ID」，移出知識庫請傳「文件ID|none」。"
                "知識庫 ID 可從 list_knowledge_bases 取得。"
            ),
        ),
        Tool(
            name="crawl_url",
            func=crawl_url,
            description=(
                "爬取指定 URL 並建立文件，可選擇性指定知識庫和標題。"
                "輸入格式：「URL」或「URL|知識庫ID」或「URL|知識庫ID|標題」。"
                "例如：「https://example.com/article|kb-uuid-...|文章標題」。"
                "不支援：facebook.com、youtube.com、Google Drive。"
            ),
        ),
        Tool(
            name="delete_document",
            func=delete_document,
            description=(
                "永久刪除文件（含向量索引與原始檔案，不可復原）。"
                "建議先用 soft_delete_document，確認無誤再永久刪除。"
                "輸入：文件的完整 UUID。"
            ),
        ),

        # ── 知識庫管理類 ─────────────────────────────────────
        Tool(
            name="create_knowledge_base",
            func=create_knowledge_base,
            description=(
                "建立新的知識庫。"
                "輸入格式：「名稱」或「名稱|描述」（以 | 分隔名稱和描述）。"
                "輸出：建立結果與新知識庫 ID。"
            ),
        ),
        Tool(
            name="update_knowledge_base",
            func=update_knowledge_base,
            description=(
                "更新知識庫的名稱和描述。"
                "輸入格式：「知識庫ID|新名稱」或「知識庫ID|新名稱|新描述」。"
                "知識庫 ID 可從 list_knowledge_bases 取得。"
            ),
        ),
        Tool(
            name="delete_knowledge_base",
            func=delete_knowledge_base,
            description=(
                "刪除知識庫（文件不會被刪除，只解除關聯）。"
                "輸入：知識庫的完整 UUID。⚠️ 此操作不可復原。"
            ),
        ),
    ]
