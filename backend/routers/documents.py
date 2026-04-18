"""
文件 Router — 上傳、狀態查詢、列表、刪除
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db
from models import Document
from services.storage import upload_file
from tasks.document_tasks import ingest_document

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/html": "html",
    "text/csv": "csv",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class DocumentOut(BaseModel):
    doc_id: str
    title: str
    status: str
    file_type: str | None
    chunk_count: int
    knowledge_base_id: str | None = None
    knowledge_base_name: str | None = None
    created_at: str

    class Config:
        from_attributes = True


class DocumentStatusOut(BaseModel):
    doc_id: str
    status: str
    chunk_count: int
    error_message: str | None


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """上傳文件並觸發非同步攝取任務"""
    # 1. 驗證 content type
    content_type = file.content_type or ""
    file_type = ALLOWED_TYPES.get(content_type)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的檔案類型：{content_type}。支援：{list(ALLOWED_TYPES.keys())}",
        )

    # 2. 讀取並驗證大小
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"檔案過大（{len(data) // 1024 // 1024} MB），上限 50 MB",
        )

    # 3. 建立 Document 記錄
    doc_id = str(uuid.uuid4())
    title = file.filename or doc_id
    object_name = f"documents/{doc_id}/{file.filename}"

    # 4. 上傳至 MinIO
    upload_file(object_name, data, content_type)

    # 5. 寫入 PG
    doc = Document(
        id=doc_id,
        title=title,
        source=file.filename,
        file_path=object_name,
        file_type=file_type,
        status="pending",
        created_by=current_user.id if current_user else None,
    )
    db.add(doc)
    await db.commit()

    # 6. 觸發 Celery 攝取任務
    ingest_document.delay(doc_id)

    logger.info("Document uploaded: %s (%s)", doc_id, file.filename)
    return {"doc_id": doc_id, "title": title, "status": "pending"}


@router.get("/{doc_id}/status", response_model=DocumentStatusOut)
async def get_document_status(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return DocumentStatusOut(
        doc_id=doc.id,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
    )


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    kb_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        q = q.where(Document.status == status_filter)
    if kb_id == "__none__":
        q = q.where(Document.knowledge_base_id.is_(None))
    elif kb_id:
        q = q.where(Document.knowledge_base_id == kb_id)
    result = await db.execute(q)
    docs = result.scalars().all()

    # load KB names
    from models import KnowledgeBase
    kb_ids = {d.knowledge_base_id for d in docs if d.knowledge_base_id}
    kb_map: dict[str, str] = {}
    if kb_ids:
        kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
        kb_map = {kb.id: kb.name for kb in kb_result.scalars().all()}

    return [
        DocumentOut(
            doc_id=d.id,
            title=d.title,
            status=d.status,
            file_type=d.file_type,
            chunk_count=d.chunk_count,
            knowledge_base_id=d.knowledge_base_id,
            knowledge_base_name=kb_map.get(d.knowledge_base_id) if d.knowledge_base_id else None,
            created_at=d.created_at.isoformat(),
        )
        for d in docs
    ]


@router.patch("/{doc_id}/fields")
async def update_custom_fields(
    doc_id: str,
    fields: dict,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """更新 custom_fields — 不觸發 re-embedding（只更新 Qdrant payload）"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    updated = {**(doc.custom_fields or {}), **fields}
    doc.custom_fields = updated

    # 同步更新 Qdrant payload（不重新 embed）
    from database import get_qdrant_client
    from sqlalchemy import text

    qdrant = get_qdrant_client()
    chunk_result = await db.execute(
        text("SELECT vector_id FROM chunks WHERE doc_id = :doc_id AND vector_id IS NOT NULL"),
        {"doc_id": doc_id},
    )
    vector_ids = [row[0] for row in chunk_result.fetchall()]
    if vector_ids:
        await qdrant.set_payload(
            collection_name="chunks",
            payload={"custom_fields": updated},
            points=vector_ids,
        )

    await db.commit()
    return {"doc_id": doc_id, "custom_fields": updated}


@router.get("/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """取得文件的 chunks 列表（含文字內容）"""
    from models import Chunk

    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    q = (
        select(Chunk)
        .where(Chunk.doc_id == doc_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
        .offset(offset)
    )
    chunk_result = await db.execute(q)
    chunks = chunk_result.scalars().all()

    return {
        "doc_id": doc_id,
        "title": doc.title,
        "total": doc.chunk_count,
        "chunks": [
            {
                "id": c.id,
                "index": c.chunk_index,
                "content": c.content,
                "page_number": c.page_number,
            }
            for c in chunks
        ],
    }


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """刪除文件（含 Qdrant 向量、MinIO 原檔、Neo4j 關係）— Saga 保護"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    from services.saga import saga_transaction
    from database import get_qdrant_client, get_neo4j_driver
    from services.storage import delete_file as minio_delete
    from sqlalchemy import text

    chunk_result = await db.execute(
        text("SELECT vector_id FROM chunks WHERE doc_id = :doc_id AND vector_id IS NOT NULL"),
        {"doc_id": doc_id},
    )
    vector_ids = [row[0] for row in chunk_result.fetchall()]

    with saga_transaction("delete_document", doc_id) as saga:
        if vector_ids:
            qdrant = get_qdrant_client()
            await qdrant.delete(collection_name="chunks", points_selector=vector_ids)
        saga.record_step("qdrant")

        driver = get_neo4j_driver()
        async with driver.session(database="neo4j") as neo_session:
            await neo_session.run(
                """
                MATCH (d:Document {id: $doc_id})-[r:MENTIONS]->(e:Entity)
                DELETE r
                WITH e
                WHERE NOT (e)<-[:MENTIONS]-() AND NOT (e)-[:INSTANCE_OF]->()
                DETACH DELETE e
                """,
                doc_id=doc_id,
            )
            await neo_session.run(
                "MATCH (d:Document {id: $doc_id}) DETACH DELETE d", doc_id=doc_id
            )
        saga.record_step("neo4j")

        await db.delete(doc)
        await db.commit()
        saga.record_step("postgres")

        if doc.file_path:
            minio_delete(doc.file_path)
        saga.record_step("minio")


# ── 移動文件至知識庫 ──────────────────────────────────────────

class MoveDocIn(BaseModel):
    knowledge_base_id: str | None  # None = 移出知識庫


# ── 編輯文件中繼資料（標題／描述／註記／圖示）──────────────────

class DocMetaIn(BaseModel):
    title: str | None = None
    description: str | None = None
    notes: str | None = None
    icon: str | None = None


@router.patch("/{doc_id}/meta")
async def update_document_meta(
    doc_id: str,
    body: DocMetaIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """更新文件標題、描述、註記、圖示（不重新分析）"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    if body.title is not None:
        doc.title = body.title.strip() or doc.title

    # 描述、註記、圖示存入 custom_fields
    cf = dict(doc.custom_fields or {})
    if body.description is not None:
        cf["description"] = body.description
    if body.notes is not None:
        cf["notes"] = body.notes
    if body.icon is not None:
        cf["icon"] = body.icon
    doc.custom_fields = cf

    await db.commit()
    return {
        "doc_id": doc_id,
        "title": doc.title,
        "custom_fields": doc.custom_fields,
    }


# ── 重新觸發 AI 分析 ──────────────────────────────────────────

@router.post("/{doc_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED)
async def reanalyze_document(
    doc_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """重置文件狀態並重新觸發 Celery 攝取任務"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not doc.file_path:
        raise HTTPException(status_code=400, detail="此文件無原始檔案，無法重新分析")

    doc.status = "pending"
    doc.error_message = None
    doc.chunk_count = 0
    await db.commit()

    ingest_document.delay(doc_id)
    logger.info("Reanalyze triggered: %s", doc_id)
    return {"doc_id": doc_id, "status": "pending"}


# ── 下載原始檔案 ──────────────────────────────────────────────

@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """從 MinIO 取得原始檔案內容（前端用於 SheetJS 渲染）"""
    from fastapi.responses import Response
    from services.storage import download_file as minio_download

    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not doc.file_path:
        raise HTTPException(status_code=400, detail="此文件無原始檔案")

    try:
        data = minio_download(doc.file_path)
    except Exception as e:
        logger.error("MinIO download failed %s: %s", doc.file_path, e)
        raise HTTPException(status_code=500, detail="檔案下載失敗")

    content_type_map = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
        "html": "text/html",
        "csv": "text/csv",
    }
    ct = content_type_map.get(doc.file_type or "", "application/octet-stream")
    return Response(
        content=data,
        media_type=ct,
        headers={"Content-Disposition": f'inline; filename="{doc.title}"'},
    )


@router.patch("/{doc_id}/kb")
async def move_document_to_kb(
    doc_id: str,
    body: MoveDocIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    if body.knowledge_base_id:
        from models import KnowledgeBase
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == body.knowledge_base_id)
        )
        if kb_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="知識庫不存在")

    doc.knowledge_base_id = body.knowledge_base_id
    await db.commit()
    return {"doc_id": doc_id, "knowledge_base_id": body.knowledge_base_id}


# ── AI 語意搜尋 ──────────────────────────────────────────────

class DocSearchIn(BaseModel):
    query: str
    kb_id: str | None = None
    top_k: int = 10


class DocSearchResult(BaseModel):
    doc_id: str
    title: str
    file_type: str | None
    status: str
    score: float
    snippet: str
    knowledge_base_id: str | None = None
    knowledge_base_name: str | None = None
    created_at: str


@router.post("/search", response_model=list[DocSearchResult])
async def search_documents_ai(
    body: DocSearchIn,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """AI 語意搜尋：嵌入查詢 → Qdrant → 聚合返回最相關文件"""
    import httpx
    from database import get_qdrant_client
    from config import settings

    if not body.query.strip():
        return []

    # 1. 嵌入查詢
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embed",
                json={"model": settings.OLLAMA_EMBED_MODEL, "input": [body.query]},
            )
            resp.raise_for_status()
            query_vec = resp.json().get("embeddings", [[]])[0]
    except Exception as e:
        logger.error("embedding failed: %s", e)
        raise HTTPException(status_code=503, detail="嵌入服務暫時無法使用")

    # 2. 如果指定 KB，先取該 KB 的 doc_id 列表
    search_filter = None
    if body.kb_id:
        kb_docs_result = await db.execute(
            select(Document.id).where(Document.knowledge_base_id == body.kb_id)
        )
        kb_doc_ids = [r[0] for r in kb_docs_result.all()]
        if not kb_doc_ids:
            return []
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        search_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=kb_doc_ids))]
        )

    # 3. Qdrant 向量搜尋
    qdrant = get_qdrant_client()
    hits = await qdrant.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vec,
        limit=body.top_k * 5,
        query_filter=search_filter,
        with_payload=True,
    )

    # 4. 聚合：每個 doc_id 保留最高分
    seen: dict[str, dict] = {}
    for hit in hits:
        doc_id = hit.payload.get("doc_id")
        if doc_id and (doc_id not in seen or hit.score > seen[doc_id]["score"]):
            seen[doc_id] = {
                "score": hit.score,
                "snippet": (hit.payload.get("content") or "")[:200],
            }

    if not seen:
        return []

    # 5. 取 Document 資訊
    docs_result = await db.execute(
        select(Document).where(Document.id.in_(list(seen.keys())))
    )
    docs_map = {d.id: d for d in docs_result.scalars().all()}

    # load KB names
    from models import KnowledgeBase
    kb_ids = {d.knowledge_base_id for d in docs_map.values() if d.knowledge_base_id}
    kb_name_map: dict[str, str] = {}
    if kb_ids:
        kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
        kb_name_map = {kb.id: kb.name for kb in kb_result.scalars().all()}

    # 6. 排序並返回
    results = []
    for doc_id, info in sorted(seen.items(), key=lambda x: -x[1]["score"]):
        if doc_id not in docs_map:
            continue
        d = docs_map[doc_id]
        results.append(DocSearchResult(
            doc_id=doc_id,
            title=d.title,
            file_type=d.file_type,
            status=d.status,
            score=round(info["score"], 4),
            snippet=info["snippet"],
            knowledge_base_id=d.knowledge_base_id,
            knowledge_base_name=kb_name_map.get(d.knowledge_base_id) if d.knowledge_base_id else None,
            created_at=d.created_at.isoformat(),
        ))

    return results[: body.top_k]

