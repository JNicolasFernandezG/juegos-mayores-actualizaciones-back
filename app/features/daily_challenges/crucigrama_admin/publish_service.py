"""Publicación, verificación de agenda y aplicación al calendario de crucigrama."""

import importlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.features.daily_challenges.crucigrama.bans import get_global_banned_words
from app.features.daily_challenges.crucigrama.published_templates import prefer_curated as _prefer_curated
from app.features.daily_challenges.crucigrama.validator import validate_pattern, validate_structure
from app.features.daily_challenges.crucigrama_admin.validation_service import (
    _assert_future_date, resolve_publish_solution,
)
from app.features.daily_challenges.games.common import upsert_daily_challenge

COLLECTION = "crucigrama_templates"
GAME_ID = "crucigrama"
STATUS_PUBLISHED = "published"

_ORIG_GET_DB = get_database
_ORIG_GLOBAL_BANS = get_global_banned_words
_ORIG_RESOLVE_SOLUTION = resolve_publish_solution
_ORIG_VALIDATE_STRUCTURE = validate_structure
_ORIG_VALIDATE_PATTERN = validate_pattern
_ORIG_PREFER_CURATED = _prefer_curated


def _service_mod() -> Any:
    name = f"{__package__}.service"
    return sys.modules.get(name) or importlib.import_module(name)


def _svc(name: str, local_val: Any, orig_val: Any) -> Any:
    if local_val is not orig_val:
        return local_val
    return getattr(_service_mod(), name, local_val)


def _user_label(user: Optional[Dict[str, Any]]) -> str:
    user = user or {}
    return str(user.get("email") or user.get("name") or user.get("id") or "sistema")


async def _assert_free_published_slot(
    field: str, value: Any, difficulty: str, slot_label: str, exclude_id: Optional[str] = None
) -> None:
    db_fn = _svc("get_database", get_database, _ORIG_GET_DB)
    query: Dict[str, Any] = {"status": STATUS_PUBLISHED, field: value, "difficulty": difficulty}
    if exclude_id:
        query["id"] = {"$ne": exclude_id}
    existing = await db_fn()[COLLECTION].find_one(query)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe la plantilla publicada '{existing.get('name')}' ({existing.get('id')}) "
                f"para {slot_label} en dificultad {difficulty}. Archivá esa plantilla primero."
            ),
        )


async def _assert_free_schedule(
    scheduled_date: str, difficulty: str, exclude_id: Optional[str] = None
) -> None:
    await _assert_free_published_slot("scheduled_date", scheduled_date, difficulty, scheduled_date, exclude_id)


async def _assert_free_monthly_day(
    monthly_day: int, difficulty: str, exclude_id: Optional[str] = None
) -> None:
    await _assert_free_published_slot(
        "monthly_day", monthly_day, difficulty, f"el día {monthly_day} de cada mes", exclude_id
    )


async def _apply_config_to_date(
    date_str: str, difficulty: str, config: Dict[str, Any], force: bool, user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    db = _svc("get_database", get_database, _ORIG_GET_DB)()
    existing = await db["daily_challenges"].find_one(
        {"game_id": GAME_ID, "date": date_str, "difficulty": difficulty}
    )
    if existing and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un desafío de crucigrama para {date_str} ({difficulty}). Usá force=true para sobrescribirlo.",
        )

    stored = {k: v for k, v in config.items() if k != "date"}
    stored["date"] = date_str
    title = f"Crucigrama ({difficulty.capitalize()}): {stored.get('theme', 'Palabras Cruzadas')} ({date_str})"
    await upsert_daily_challenge(
        db, game_id=GAME_ID, date_str=date_str, title=title, config=stored,
        difficulty=difficulty, now_utc=datetime.now(timezone.utc),
        extra_fields={"source": "admin_template", "updated_by": _user_label(user)},
    )
    return {
        "game_id": GAME_ID, "date": date_str, "difficulty": difficulty,
        "overwritten": bool(existing), "total_words": stored.get("total_words", 0),
    }


_ORIG_APPLY_CONFIG = _apply_config_to_date


async def publish_template(template_id: str, payload: Any, user: Dict[str, Any]) -> Dict[str, Any]:
    """Resuelve/valida la grilla, publica la plantilla y la aplica si tiene fecha fija."""
    svc = _service_mod()
    doc = await svc._get_doc(template_id)
    difficulty = doc.get("difficulty") or "facil"
    bans_fn = _svc("get_global_banned_words", get_global_banned_words, _ORIG_GLOBAL_BANS)
    resolve_fn = _svc("resolve_publish_solution", resolve_publish_solution, _ORIG_RESOLVE_SOLUTION)
    report, banned_words, solution_grid, config = resolve_fn(
        doc, payload, await bans_fn(),
        validate_structure_fn=_svc("validate_structure", validate_structure, _ORIG_VALIDATE_STRUCTURE),
        validate_pattern_fn=_svc("validate_pattern", validate_pattern, _ORIG_VALIDATE_PATTERN),
        prefer_curated_fn=_svc("_prefer_curated", _prefer_curated, _ORIG_PREFER_CURATED),
    )

    scheduled_date = payload.scheduled_date or doc.get("scheduled_date")
    if scheduled_date:
        _assert_future_date(scheduled_date)
        await _assert_free_schedule(scheduled_date, difficulty, template_id)

    monthly_day = payload.monthly_day or doc.get("monthly_day")
    if monthly_day:
        await _assert_free_monthly_day(monthly_day, difficulty, template_id)

    now = datetime.now(timezone.utc)
    changes = {
        "status": STATUS_PUBLISHED, "anchors": report["anchors"], "banned_words": banned_words,
        "last_seed": payload.seed, "solution_grid": solution_grid,
        "clues": {word["word"]: word["clue"] for word in config["words"]},
        "published_config": config, "total_words": config["total_words"],
        "scheduled_date": scheduled_date, "monthly_day": monthly_day,
        "published_at": now, "published_by": _user_label(user),
        "archived_at": None, "archived_by": None, "updated_at": now,
    }
    db_fn = _svc("get_database", get_database, _ORIG_GET_DB)
    try:
        await db_fn()[COLLECTION].update_one({"id": template_id}, {"$set": changes})
    except DuplicateKeyError:
        msg = f"Ya hay una plantilla publicada para esa fecha o ese día del mes en dificultad {difficulty}."
        raise HTTPException(status_code=409, detail=msg)
    doc.update(changes)
    apply_fn = _svc("_apply_config_to_date", _apply_config_to_date, _ORIG_APPLY_CONFIG)
    applied_to = await apply_fn(scheduled_date, difficulty, config, force=True, user=user) if scheduled_date else None
    return {"template": svc._to_detail(doc), "applied_to": applied_to}


async def apply_template(template_id: str, date_str: str, force: bool, user: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica una plantilla ya publicada a una fecha futura concreta."""
    doc = await _service_mod()._get_doc(template_id)
    if doc.get("status") != STATUS_PUBLISHED:
        raise HTTPException(status_code=409, detail="Solo se pueden aplicar plantillas publicadas.")
    config = doc.get("published_config")
    if not config:
        raise HTTPException(status_code=409, detail="La plantilla no tiene una configuración publicada.")
    _assert_future_date(date_str)
    apply_fn = _svc("_apply_config_to_date", _apply_config_to_date, _ORIG_APPLY_CONFIG)
    applied = await apply_fn(date_str, doc.get("difficulty") or "facil", config, force=force, user=user)
    return {"success": True, "template_id": template_id, **applied}
