import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import entitlements
from app.core.database import get_db
from app.core.security import get_current_admin_user, require_admin_role
from app.models.knowledge import KnowledgeDoc
from app.models.user import AdminUser
from app.core.access import parse_tags_json, parse_ids_json

router = APIRouter(prefix="/admin/knowledge", tags=["Admin Knowledge Base Management"])


def _access_json_from(group_ids: Optional[List[int]], access_tags: Optional[List[str]]) -> tuple[str, str]:
    """Returns (access_group_ids_json, access_tags_json). Mirrors the catalog:
    group IDs are stored as their own list AND copied into the tags list (as
    strings) so the tag-based access filter and RAG retrieval match them
    without a join. Non-numeric free tags are kept alongside."""
    gids = [int(g) for g in (group_ids or []) if g]
    free_tags = [t.strip().lower() for t in (access_tags or []) if t.strip() and not t.strip().isdigit()]
    combined = sorted(set(free_tags + [str(g) for g in gids]))
    return json.dumps(gids), json.dumps(combined)


class KnowledgeDocCreateRequest(BaseModel):
    title: str
    category: Optional[str] = None
    content: str
    tags: Optional[str] = None
    access_group_ids: Optional[List[int]] = []
    access_tags: Optional[List[str]] = []


class KnowledgeDocUpdateRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    access_group_ids: Optional[List[int]] = None
    access_tags: Optional[List[str]] = None


@router.get("")
async def list_admin_knowledge(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Lists knowledge base documents with access tags and categories."""
    stmt = select(KnowledgeDoc)
    conditions = []

    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(KnowledgeDoc.title.ilike(term), KnowledgeDoc.content.ilike(term)))
    if category:
        conditions.append(KnowledgeDoc.category.ilike(f"%{category.strip()}%"))

    if conditions:
        stmt = stmt.where(*conditions)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    offset = (page - 1) * limit
    stmt = stmt.order_by(desc(KnowledgeDoc.created_at)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    docs = res.scalars().all()

    return {
        "items": [
            {
                "id": doc.id,
                "title": doc.title,
                "category": doc.category or "General",
                "content": doc.content,
                "tags": doc.tags,
                "access_group_ids": parse_ids_json(getattr(doc, "access_group_ids_json", "[]")),
                "access_tags": [t for t in parse_tags_json(doc.access_tags_json) if not t.isdigit()],
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge_doc(
    req: KnowledgeDocCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    """Creates a new knowledge document scoped to access groups (and/or tags)."""
    # No-op unless CommB Cloud provisioned this instance on a plan; a
    # self-hosted install has no document limit. See app/core/entitlements.py.
    existing = (await db.execute(select(func.count(KnowledgeDoc.id)))).scalar() or 0
    entitlements.require_knowledge_capacity(existing)

    group_ids_json, tags_json = _access_json_from(req.access_group_ids, req.access_tags)

    doc = KnowledgeDoc(
        title=req.title,
        category=req.category,
        content=req.content,
        tags=req.tags,
        access_group_ids_json=group_ids_json,
        access_tags_json=tags_json,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "access_group_ids": parse_ids_json(doc.access_group_ids_json),
        "access_tags": [t for t in parse_tags_json(doc.access_tags_json) if not t.isdigit()],
    }


@router.get("/{doc_id}")
async def get_knowledge_doc(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")

    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category or "General",
        "content": doc.content,
        "tags": doc.tags,
        "access_group_ids": parse_ids_json(getattr(doc, "access_group_ids_json", "[]")),
        "access_tags": [t for t in parse_tags_json(doc.access_tags_json) if not t.isdigit()],
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.put("/{doc_id}")
async def update_knowledge_doc(
    doc_id: int,
    req: KnowledgeDocUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_admin_role),
):
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")

    if req.title is not None:
        doc.title = req.title
    if req.category is not None:
        doc.category = req.category
    if req.content is not None:
        doc.content = req.content
    if req.tags is not None:
        doc.tags = req.tags
    if req.access_group_ids is not None or req.access_tags is not None:
        # Preserve whichever side wasn't sent in this request.
        gids = req.access_group_ids if req.access_group_ids is not None else parse_ids_json(getattr(doc, "access_group_ids_json", "[]"))
        free = req.access_tags if req.access_tags is not None else [t for t in parse_tags_json(doc.access_tags_json) if not t.isdigit()]
        doc.access_group_ids_json, doc.access_tags_json = _access_json_from(gids, free)

    await db.commit()
    await db.refresh(doc)

    return {"status": "ok", "message": "Knowledge document updated successfully"}


@router.delete("/{doc_id}")
async def delete_knowledge_doc(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_admin_role),
):
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")

    await db.delete(doc)
    await db.commit()

    return {"status": "ok", "message": "Knowledge document deleted"}
