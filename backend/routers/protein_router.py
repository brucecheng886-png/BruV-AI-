"""
Protein Graph Router
POST /api/protein/import   — 上傳兩個 xlsx，自動辨識 genes / scores
GET  /api/protein/networks — 列出已匯入的 network 清單
GET  /api/protein/graph    — 取得 3D 圖所需 nodes + links
GET  /api/protein/top      — 取前 N 高分邊
"""
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from plugins.protein_graph_handler import (
    _parse_genes_xlsx,
    _parse_scores_xlsx,
    _db_upsert_proteins,
    _db_upsert_interactions,
    _get_networks,
    _get_graph_data,
    _get_top_interactions,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _is_genes_file(data: bytes, filename: str) -> bool:
    """簡單啟發式：genes list 遠小於 scores；或從檔名判斷"""
    name_lower = filename.lower()
    if "gene" in name_lower or "list" in name_lower:
        return True
    if "score" in name_lower or "connection" in name_lower:
        return False
    # 以檔案大小判斷（genes list 通常較小）
    return len(data) < 16_000


@router.post("/import")
async def import_xlsx(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """
    接受 1~2 個 xlsx：
    - genes list → 寫入 proteins 表
    - scores xlsx  → 寫入 protein_interactions 表
    """
    if not files:
        raise HTTPException(status_code=400, detail="至少上傳一個 xlsx 檔案")
    if len(files) > 2:
        raise HTTPException(status_code=400, detail="最多上傳兩個 xlsx 檔案")

    genes_count = 0
    interactions_count = 0
    networks_imported = []

    for upload in files:
        data = await upload.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"{upload.filename} 超過 20MB 限制")

        if _is_genes_file(data, upload.filename or ""):
            # 解析 genes list
            try:
                proteins = _parse_genes_xlsx(data)
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"genes xlsx 解析錯誤: {e}")
            if not proteins:
                raise HTTPException(status_code=422, detail="genes xlsx 未找到有效的 GeneCards URL")
            genes_count = await _db_upsert_proteins(proteins, db)
        else:
            # 解析 scores xlsx
            try:
                interactions = _parse_scores_xlsx(data)
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"scores xlsx 解析錯誤: {e}")
            if not interactions:
                raise HTTPException(status_code=422, detail="scores xlsx 未找到有效的連結評分")
            interactions_count = await _db_upsert_interactions(interactions, db)
            networks_imported = list({i["network"] for i in interactions})

    return {
        "success": True,
        "genes_imported": genes_count,
        "interactions_imported": interactions_count,
        "networks": sorted(networks_imported),
    }


@router.get("/networks")
async def list_networks(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    networks = await _get_networks(db)
    return {"networks": networks}


@router.get("/graph")
async def get_graph(
    network: str = Query("USP7", description="Network 名稱，如 USP7 / SOD1 / MDM2 / HSPA4"),
    min_score: float = Query(0.5, ge=0.0, le=1.0, description="最低連結評分閾值"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    data = await _get_graph_data(network, min_score, db)
    if not data["nodes"]:
        raise HTTPException(status_code=404, detail=f"Network '{network}' 無資料，請先匯入")
    return data


@router.get("/top")
async def get_top(
    network: str = Query("USP7"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    rows = await _get_top_interactions(network, limit, db)
    return {"interactions": rows, "network": network}
