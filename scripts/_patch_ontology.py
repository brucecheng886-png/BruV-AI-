"""
一次性補丁腳本：在 ontology.py 的 /blocklist endpoint 前插入 batch endpoints
"""
import pathlib

path = pathlib.Path(r'C:\Users\bruce\PycharmProjects\BruV AI新架構\backend\routers\ontology.py')
raw = path.read_bytes()

BATCH_CODE = b'''\n\n# -- Batch Operations ---------------------------------------------------------\n\nclass BatchBody(BaseModel):\n    ids: list[str] = []\n    all: bool = False\n\n\n@router.post("/review-queue/batch-approve", status_code=200)\nasync def batch_approve_review(\n    body: BatchBody,\n    db: AsyncSession = Depends(get_db),\n    neo4j_session=Depends(get_neo4j_session),\n    current_user: CurrentUser = None,\n):\n    """batch approve: body.all=True approves all pending, else approves body.ids"""\n    if body.all:\n        result = await db.execute(\n            select(OntologyReviewQueue).where(OntologyReviewQueue.status == "pending")\n        )\n        items = result.scalars().all()\n    elif body.ids:\n        result = await db.execute(\n            select(OntologyReviewQueue).where(\n                and_(OntologyReviewQueue.id.in_(body.ids),\n                     OntologyReviewQueue.status == "pending")\n            )\n        )\n        items = result.scalars().all()\n    else:\n        return {"approved": 0}\n\n    count = 0\n    for item in items:\n        data = item.proposed_data or {}\n        name = item.entity_name\n        etype = item.entity_type\n        desc = data.get("description", "")\n        props = data.get("properties", {})\n        if item.action in ("create", "update"):\n            await neo4j_session.run(\n                "MERGE (e:Entity {name: $name}) SET e.type = $etype, e.description = $desc",\n                name=name, etype=etype, desc=desc,\n            )\n            for k, v in props.items():\n                await neo4j_session.run(\n                    "MATCH (e:Entity {name: $name}) SET e[$key] = $val",\n                    name=name, key=k, val=str(v),\n                )\n        elif item.action == "delete":\n            await neo4j_session.run(\n                "MATCH (e:Entity {name: $name}) DETACH DELETE e", name=name\n            )\n        item.status = "approved"\n        item.reviewed_by = current_user.id if current_user else None\n        count += 1\n\n    await db.commit()\n    return {"approved": count}\n\n\n@router.post("/review-queue/batch-reject", status_code=200)\nasync def batch_reject_review(\n    body: BatchBody,\n    db: AsyncSession = Depends(get_db),\n    current_user: CurrentUser = None,\n):\n    """batch reject: body.all=True rejects all pending, else rejects body.ids"""\n    if body.all:\n        result = await db.execute(\n            select(OntologyReviewQueue).where(OntologyReviewQueue.status == "pending")\n        )\n        items = result.scalars().all()\n    elif body.ids:\n        result = await db.execute(\n            select(OntologyReviewQueue).where(\n                and_(OntologyReviewQueue.id.in_(body.ids),\n                     OntologyReviewQueue.status == "pending")\n            )\n        )\n        items = result.scalars().all()\n    else:\n        return {"rejected": 0}\n\n    count = 0\n    for item in items:\n        existing = await db.execute(\n            select(OntologyBlocklist).where(\n                and_(OntologyBlocklist.name == item.entity_name,\n                     OntologyBlocklist.entity_type == item.entity_type)\n            )\n        )\n        if not existing.scalar_one_or_none():\n            db.add(OntologyBlocklist(\n                name=item.entity_name,\n                entity_type=item.entity_type,\n                blocked_by=current_user.id if current_user else None,\n            ))\n        item.status = "rejected"\n        item.reviewed_by = current_user.id if current_user else None\n        count += 1\n\n    await db.commit()\n    return {"rejected": count}\n\n\n'''

MARKER = b'@router.get("/blocklist", response_model=list[BlocklistOut])'
idx = raw.find(MARKER)
if idx == -1:
    raise RuntimeError("MARKER NOT FOUND in ontology.py")

# Check not already patched
if b'batch_approve_review' in raw:
    print("Already patched, skipping.")
else:
    new_raw = raw[:idx] + BATCH_CODE + raw[idx:]
    path.write_bytes(new_raw)
    print(f"OK: inserted {len(BATCH_CODE)} bytes at offset {idx}")
