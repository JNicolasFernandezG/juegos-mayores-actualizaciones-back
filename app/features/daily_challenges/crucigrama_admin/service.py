"""Persistencia y ciclo de vida de las máscaras de crucigrama del panel admin."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo import DESCENDING

from app.core.database import get_database
from app.core.rae_client import get_masked_definition
from app.features.daily_challenges.crucigrama.bans import (
    get_global_banned_words, get_global_bans_doc, set_global_banned_words,
)
from app.features.daily_challenges.crucigrama.published_templates import (  # noqa: F401
    get_recurring_published_config, get_scheduled_published_config, prefer_curated as _prefer_curated,
)
from app.features.daily_challenges.crucigrama.validator import validate_pattern, validate_structure
from app.features.daily_challenges.crucigrama_admin.publish_service import (  # noqa: F401
    COLLECTION, GAME_ID, STATUS_PUBLISHED,
    _apply_config_to_date, _assert_free_monthly_day, _assert_free_published_slot,
    _assert_free_schedule, _user_label, apply_template, publish_template,
)
from app.features.daily_challenges.crucigrama_admin.schemas import (
    CrucigramaTemplateCreate, CrucigramaTemplateUpdate,
)
from app.features.daily_challenges.crucigrama_admin.validation_service import (  # noqa: F401
    _assert_future_date, _assert_structure as _val_assert_structure,
    lookup_definition as _val_lookup_definition, lookup_definitions as _val_lookup_definitions,
    resolve_publish_solution, validate_mask as _val_validate_mask,
)

logger = logging.getLogger(__name__)
STATUS_DRAFT = "draft"
STATUS_ARCHIVED = "archived"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def _to_summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("id"), "name": doc.get("name"),
        "theme": doc.get("theme") or "Palabras Cruzadas", "difficulty": doc.get("difficulty"),
        "size": doc.get("size") or len(doc.get("pattern") or []), "status": doc.get("status"),
        "scheduled_date": doc.get("scheduled_date"), "monthly_day": doc.get("monthly_day"),
        "total_words": doc.get("total_words") or 0, "anchors": doc.get("anchors") or {},
        "created_by": doc.get("created_by"), "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")), "published_at": _iso(doc.get("published_at")),
        "archived_at": _iso(doc.get("archived_at")),
    }


def _to_detail(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_to_summary(doc),
        "pattern": doc.get("pattern") or [], "banned_words": doc.get("banned_words") or [],
        "clue_overrides": doc.get("clue_overrides") or {},
        "solution_grid": doc.get("solution_grid"), "clues": doc.get("clues") or {},
        "published_config": doc.get("published_config"), "last_seed": doc.get("last_seed"),
        "notes": doc.get("notes"), "published_by": doc.get("published_by"),
        "archived_by": doc.get("archived_by"),
    }


async def _get_doc(template_id: str) -> Dict[str, Any]:
    doc = await get_database()[COLLECTION].find_one({"id": template_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"No existe la plantilla '{template_id}'.")
    return doc


def _assert_structure(pattern: List[str], anchors: Dict[str, str]) -> Dict[str, Any]:
    return _val_assert_structure(pattern, anchors, validate_structure_fn=validate_structure)


def validate_mask(payload: Any, global_banned_words: Optional[List[str]] = None) -> Dict[str, Any]:
    """Valida estructura + solubilidad sin persistir nada."""
    return _val_validate_mask(
        payload, global_banned_words=global_banned_words,
        validate_pattern_fn=validate_pattern, prefer_curated_fn=_prefer_curated,
    )


def lookup_definition(word: str) -> Dict[str, Any]:
    """Definición RAE (con la palabra tapada) para una palabra del diseñador."""
    return _val_lookup_definition(word, get_masked_definition_fn=get_masked_definition)


def lookup_definitions(words: List[str]) -> Dict[str, Any]:
    """Definiciones RAE en lote para autocompletar pistas."""
    return _val_lookup_definitions(words, get_masked_definition_fn=get_masked_definition)


async def get_global_bans() -> Dict[str, Any]:
    return await get_global_bans_doc()


async def update_global_bans(payload: Any, user: Dict[str, Any]) -> Dict[str, Any]:
    words = await set_global_banned_words(payload.banned_words, updated_by=_user_label(user))
    logger.info(f"[CRUCIGRAMA] Vetos globales actualizados ({len(words)}) por {_user_label(user)}.")
    return await get_global_bans_doc()


async def list_templates(
    status: Optional[str] = None, difficulty: Optional[str] = None,
    size: Optional[int] = None, limit: int = 50, skip: int = 0,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if difficulty:
        query["difficulty"] = difficulty
    if size:
        query["size"] = size
    collection = get_database()[COLLECTION]
    total = await collection.count_documents(query)
    cursor = collection.find(query).sort("updated_at", DESCENDING).skip(skip).limit(limit)
    return {"total": total, "limit": limit, "skip": skip, "items": [_to_summary(doc) async for doc in cursor]}


async def get_template(template_id: str) -> Dict[str, Any]:
    return _to_detail(await _get_doc(template_id))


async def create_template(payload: CrucigramaTemplateCreate, user: Dict[str, Any]) -> Dict[str, Any]:
    report = _assert_structure(payload.pattern, payload.anchors)
    if payload.scheduled_date:
        _assert_future_date(payload.scheduled_date)
    now = _now()
    doc: Dict[str, Any] = {
        "id": uuid.uuid4().hex[:16], "name": payload.name.strip(),
        "theme": payload.theme.strip() or "Palabras Cruzadas", "pattern": payload.pattern,
        "size": len(payload.pattern), "difficulty": payload.difficulty,
        "anchors": report["anchors"], "banned_words": payload.banned_words,
        "clue_overrides": payload.clue_overrides, "status": STATUS_DRAFT,
        "scheduled_date": payload.scheduled_date, "monthly_day": payload.monthly_day,
        "total_words": report["words"], "solution_grid": None, "clues": {},
        "published_config": None, "last_seed": None, "notes": payload.notes,
        "created_by": _user_label(user), "created_at": now, "updated_at": now,
        "published_at": None, "published_by": None, "archived_at": None, "archived_by": None,
    }
    await get_database()[COLLECTION].insert_one(doc)
    return _to_detail(doc)


async def update_template(
    template_id: str, payload: CrucigramaTemplateUpdate, user: Dict[str, Any]
) -> Dict[str, Any]:
    doc = await _get_doc(template_id)
    if doc.get("status") == STATUS_PUBLISHED:
        raise HTTPException(status_code=409, detail="La plantilla está publicada. Archivala antes de editarla.")
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return _to_detail(doc)
    if data.get("banned_words") is None:
        data.pop("banned_words", None)
    if data.get("scheduled_date"):
        _assert_future_date(data["scheduled_date"])
    pattern, anchors = data.get("pattern", doc.get("pattern") or []), data.get("anchors", doc.get("anchors") or {})
    if "pattern" in data or "anchors" in data or "banned_words" in data:
        report = _assert_structure(pattern, anchors)
        data.update({
            "anchors": report["anchors"], "size": len(pattern), "total_words": report["words"],
            "solution_grid": None, "clues": {}, "published_config": None,
            "last_seed": None, "published_at": None, "published_by": None,
        })
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
    if data.get("theme") is not None:
        data["theme"] = data["theme"].strip() or "Palabras Cruzadas"
    data["updated_at"] = _now()
    await get_database()[COLLECTION].update_one({"id": template_id}, {"$set": data})
    doc.update(data)
    return _to_detail(doc)


async def archive_template(template_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    doc = await _get_doc(template_id)
    if doc.get("status") == STATUS_ARCHIVED:
        return _to_detail(doc)
    now = _now()
    changes = {"status": STATUS_ARCHIVED, "archived_at": now, "archived_by": _user_label(user), "updated_at": now}
    await get_database()[COLLECTION].update_one({"id": template_id}, {"$set": changes})
    doc.update(changes)
    return _to_detail(doc)


async def delete_template(template_id: str) -> Dict[str, Any]:
    doc = await _get_doc(template_id)
    if doc.get("status") == STATUS_PUBLISHED:
        raise HTTPException(status_code=409, detail="No se puede eliminar una plantilla publicada. Archivala primero.")
    await get_database()[COLLECTION].delete_one({"id": template_id})
    return {"success": True, "deleted_id": template_id}
