"""
Ontology Router ??Review Queue 撖拇 + Blocklist + ???亥岷
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser
from database import get_db, get_neo4j_session
from models import OntologyReviewQueue, OntologyBlocklist

logger = logging.getLogger(__name__)
router = APIRouter()


# ?? Pydantic Schemas ?????????????????????????????????????????????????????????

class ReviewQueueOut(BaseModel):
    id: str
    entity_name: str
    entity_type: str
    action: str
    proposed_data: dict
    source_doc_id: Optional[str]
    status: str
    reviewed_by: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class BlocklistOut(BaseModel):
    id: str
    name: str
    entity_type: str
    blocked_by: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class RejectBody(BaseModel):
    reason: Optional[str] = None


# ?? Review Queue ?????????????????????????????????????????????????????????????

@router.get("/review-queue", response_model=list[ReviewQueueOut])
async def list_review_queue(
    status_filter: str = Query("pending", alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(OntologyReviewQueue)
        .where(OntologyReviewQueue.status == status_filter)
        .order_by(OntologyReviewQueue.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        ReviewQueueOut(
            id=r.id,
            entity_name=r.entity_name,
            entity_type=r.entity_type,
            action=r.action,
            proposed_data=r.proposed_data or {},
            source_doc_id=r.source_doc_id,
            status=r.status,
            reviewed_by=r.reviewed_by,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("/review-queue/{item_id}/approve", status_code=200)
async def approve_review_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    neo4j_session=Depends(get_neo4j_session),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(OntologyReviewQueue).where(
            and_(OntologyReviewQueue.id == item_id,
                 OntologyReviewQueue.status == "pending")
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found or already processed")

    data = item.proposed_data or {}
    name = item.entity_name
    etype = item.entity_type
    desc = data.get("description", "")
    props = data.get("properties", {})

    if item.action in ("create", "update"):
        await neo4j_session.run(
            """
            MERGE (e:Entity {name: $name})
            SET e.type = $etype, e.description = $desc
            """,
            name=name, etype=etype, desc=desc,
        )
        for k, v in props.items():
            await neo4j_session.run(
                "MATCH (e:Entity {name: $name}) SET e[$key] = $val",
                name=name, key=k, val=str(v),
            )
    elif item.action == "delete":
        await neo4j_session.run(
            "MATCH (e:Entity {name: $name}) DETACH DELETE e",
            name=name,
        )

    item.status = "approved"
    item.reviewed_by = current_user.id
    await db.commit()
    return {"status": "approved", "id": item_id}


@router.post("/review-queue/{item_id}/reject", status_code=200)
async def reject_review_item(
    item_id: str,
    body: RejectBody = RejectBody(),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(OntologyReviewQueue).where(
            and_(OntologyReviewQueue.id == item_id,
                 OntologyReviewQueue.status == "pending")
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found or already processed")

    # ?撠?皜
    existing = await db.execute(
        select(OntologyBlocklist).where(
            and_(OntologyBlocklist.name == item.entity_name,
                 OntologyBlocklist.entity_type == item.entity_type)
        )
    )
    if not existing.scalar_one_or_none():
        db.add(OntologyBlocklist(
            name=item.entity_name,
            entity_type=item.entity_type,
            blocked_by=current_user.id,
        ))

    item.status = "rejected"
    item.reviewed_by = current_user.id
    await db.commit()
    return {"status": "rejected", "id": item_id}


# ?? Blocklist ?????????????????????????????????????????????????????????????????



# -- Batch Operations ---------------------------------------------------------

class BatchBody(BaseModel):
    ids: list[str] = []
    all: bool = False


@router.post("/review-queue/batch-approve", status_code=200)
async def batch_approve_review(
    body: BatchBody,
    db: AsyncSession = Depends(get_db),
    neo4j_session=Depends(get_neo4j_session),
    current_user: CurrentUser = None,
):
    if body.all:
        result = await db.execute(
            select(OntologyReviewQueue).where(OntologyReviewQueue.status == "pending")
        )
        items = result.scalars().all()
    elif body.ids:
        result = await db.execute(
            select(OntologyReviewQueue).where(
                and_(OntologyReviewQueue.id.in_(body.ids),
                     OntologyReviewQueue.status == "pending")
            )
        )
        items = result.scalars().all()
    else:
        return {"approved": 0}
    count = 0
    for item in items:
        data = item.proposed_data or {}
        name = item.entity_name
        etype = item.entity_type
        desc = data.get("description", "")
        props = data.get("properties", {})
        if item.action in ("create", "update"):
            await neo4j_session.run(
                "MERGE (e:Entity {name: $name}) SET e.type = $etype, e.description = $desc",
                name=name, etype=etype, desc=desc,
            )
            for k, v in props.items():
                await neo4j_session.run(
                    "MATCH (e:Entity {name: $name}) SET e[$key] = $val",
                    name=name, key=k, val=str(v),
                )
        elif item.action == "delete":
            await neo4j_session.run(
                "MATCH (e:Entity {name: $name}) DETACH DELETE e", name=name
            )
        item.status = "approved"
        item.reviewed_by = current_user.id if current_user else None
        count += 1
    await db.commit()
    return {"approved": count}


@router.post("/review-queue/batch-reject", status_code=200)
async def batch_reject_review(
    body: BatchBody,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    if body.all:
        result = await db.execute(
            select(OntologyReviewQueue).where(OntologyReviewQueue.status == "pending")
        )
        items = result.scalars().all()
    elif body.ids:
        result = await db.execute(
            select(OntologyReviewQueue).where(
                and_(OntologyReviewQueue.id.in_(body.ids),
                     OntologyReviewQueue.status == "pending")
            )
        )
        items = result.scalars().all()
    else:
        return {"rejected": 0}
    count = 0
    for item in items:
        existing = await db.execute(
            select(OntologyBlocklist).where(
                and_(OntologyBlocklist.name == item.entity_name,
                     OntologyBlocklist.entity_type == item.entity_type)
            )
        )
        if not existing.scalar_one_or_none():
            db.add(OntologyBlocklist(
                name=item.entity_name,
                entity_type=item.entity_type,
                blocked_by=current_user.id if current_user else None,
            ))
        item.status = "rejected"
        item.reviewed_by = current_user.id if current_user else None
        count += 1
    await db.commit()
    return {"rejected": count}

@router.get("/blocklist", response_model=list[BlocklistOut])
async def list_blocklist(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(OntologyBlocklist)
        .order_by(OntologyBlocklist.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        BlocklistOut(
            id=r.id,
            name=r.name,
            entity_type=r.entity_type,
            blocked_by=r.blocked_by,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.delete("/blocklist/{item_id}", status_code=200)
async def delete_blocklist_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    result = await db.execute(
        select(OntologyBlocklist).where(OntologyBlocklist.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Blocklist item not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": item_id}


# ?? Graph ?????????????????????????????????????????????????????????????????????

@router.get("/graph")
async def get_graph(
    limit: int = Query(200, ge=1, le=1000),
    neo4j_session=Depends(get_neo4j_session),
    current_user: CurrentUser = None,
):
    """回傳 {nodes, edges}，節點含 degree weight，邊含聚合 weight"""
    nodes_result = await neo4j_session.run(
        """
        MATCH (e:Entity)
        OPTIONAL MATCH (e)-[r]-()
        RETURN e.name AS name, e.type AS type, e.description AS description,
               count(r) AS degree
        LIMIT $limit
        """,
        limit=limit,
    )
    nodes_data = await nodes_result.data()

    edges_result = await neo4j_session.run(
        """
        MATCH (a:Entity)-[r]->(b:Entity)
        WITH a.name AS source, b.name AS target, type(r) AS rel_type, count(*) AS weight
        RETURN source, target, rel_type, weight
        LIMIT $limit
        """,
        limit=limit,
    )
    edges_data = await edges_result.data()

    doc_edges_result = await neo4j_session.run(
        """
        MATCH (d:Document)-[:MENTIONS]->(e:Entity)
        WITH d, e, count(*) AS weight
        RETURN d.id AS doc_id, d.title AS doc_title, e.name AS entity_name, weight
        LIMIT $limit
        """,
        limit=limit,
    )
    doc_edges_data = await doc_edges_result.data()

    nodes = [
        {"data": {"id": n["name"], "label": n["name"], "type": n.get("type", "Entity"),
                  "description": n.get("description", ""), "weight": n.get("degree", 1) or 1}}
        for n in nodes_data
    ]
    seen_docs: set[str] = set()
    for de in doc_edges_data:
        if de["doc_id"] not in seen_docs:
            nodes.append({"data": {"id": de["doc_id"], "label": de.get("doc_title", de["doc_id"]),
                                   "type": "Document", "weight": 1}})
            seen_docs.add(de["doc_id"])

    edges = [
        {"data": {"id": f"{e['source']}->{e['target']}", "source": e["source"],
                  "target": e["target"], "label": e.get("rel_type", "RELATED"),
                  "weight": e.get("weight", 1)}}
        for e in edges_data
    ]
    for de in doc_edges_data:
        edges.append({"data": {"id": f"{de['doc_id']}->#{de['entity_name']}",
                                "source": de["doc_id"], "target": de["entity_name"],
                                "label": "MENTIONS", "weight": de.get("weight", 1)}})

    return {"nodes": nodes, "edges": edges}



