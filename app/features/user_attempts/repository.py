"""Persistencia, serialización y helpers de dificultad para user_attempts."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.features.user_attempts.schemas import (
    UserAttemptCreateRequest,
    UserAttemptResponse,
)

_DIFFICULTY_PATTERN = re.compile(r"^[a-z0-9_-]{1,32}$")
_COMPLETED_STATUSES = ("completed", "won")
_TIME_SUSPECT_MIN_SERVER_SECONDS = 30
_TIME_SUSPECT_MIN_DIFF_SECONDS = 10


@dataclass(frozen=True)
class AttemptEvaluation:
    """Resultado de validar y calificar un intento antes de persistirlo."""

    final_status: str
    attempts_value: int
    grade: str
    score: int
    stars: int
    validation_status: Optional[str]
    validation_reason: Optional[str]
    server_elapsed: Optional[int]
    time_suspect: bool


def _normalize_difficulty(req: UserAttemptCreateRequest) -> str:
    raw = req.difficulty or (req.game_data or {}).get("difficulty") or "standard"
    difficulty = str(raw).strip().lower()
    if not _DIFFICULTY_PATTERN.match(difficulty):
        raise HTTPException(status_code=400, detail="La dificultad informada no es válida.")
    return difficulty


def _doc_difficulty(doc: dict) -> str:
    return str(doc.get("difficulty") or "standard").strip().lower()


def _is_completed_attempt(doc: Optional[dict]) -> bool:
    if not doc:
        return False
    return doc.get("status") in _COMPLETED_STATUSES and doc.get("validation_status") != "rejected"


def _difficulty_is_completed(doc: Optional[dict], difficulty: str) -> bool:
    if not doc:
        return False
    sub = (doc.get("by_difficulty") or {}).get(difficulty)
    if sub:
        return _is_completed_attempt(sub)
    # Documentos históricos sin by_difficulty: se interpretan como su dificultad declarada.
    if _doc_difficulty(doc) == difficulty:
        return _is_completed_attempt(doc)
    return False


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _attempt_started_at(doc: Optional[dict], difficulty: str) -> Optional[datetime]:
    if not doc:
        return None
    sub = (doc.get("by_difficulty") or {}).get(difficulty)
    if sub and isinstance(sub.get("started_at"), datetime):
        return _as_utc(sub["started_at"])
    if _doc_difficulty(doc) == difficulty and isinstance(doc.get("started_at"), datetime):
        return _as_utc(doc["started_at"])
    return None


def _server_elapsed_seconds(
    started_at: Optional[datetime], now: datetime, client_seconds: Optional[int]
) -> Tuple[Optional[int], bool]:
    """Tiempo medido por el servidor y sospecha de tiempo cliente subdeclarado."""
    if started_at is None:
        return None, False
    elapsed = int((now - started_at).total_seconds())
    if elapsed < 0:
        return None, False
    suspect = (
        client_seconds is not None
        and elapsed >= _TIME_SUSPECT_MIN_SERVER_SECONDS
        and elapsed - client_seconds >= _TIME_SUSPECT_MIN_DIFF_SECONDS
        and client_seconds < elapsed * 0.5
    )
    return elapsed, suspect


def _should_replace_top_level(existing: dict, final_status: str) -> bool:
    """El nivel superior refleja la última partida, salvo que ya esté completada."""
    if existing.get("validation_status") == "rejected":
        return True
    if existing.get("status") in _COMPLETED_STATUSES:
        return final_status == "completed"
    return True


def _attempt_snapshot(doc: dict) -> dict:
    """Copia un intento para guardarlo dentro de by_difficulty (sin _id ni anidamientos)."""
    return {k: v for k, v in doc.items() if k not in ("_id", "created_at", "by_difficulty")}


def _preserve_existing_difficulty(existing: dict, difficulty: str, update_fields: dict) -> None:
    """Materializa by_difficulty si el documento histórico no lo tenía."""
    existing_difficulty = _doc_difficulty(existing)
    if existing_difficulty == difficulty:
        return
    if existing_difficulty not in (existing.get("by_difficulty") or {}):
        update_fields[f"by_difficulty.{existing_difficulty}"] = _attempt_snapshot(existing)


def _serialize_attempt(
    doc: dict,
    puntos_ganados: int = 0,
    puntos_totales_usuario: Optional[int] = None,
) -> UserAttemptResponse:
    updated_at = doc.get("updated_at")
    updated_at_str = (
        updated_at.isoformat() if isinstance(updated_at, datetime) else (str(updated_at) if updated_at else None)
    )
    return UserAttemptResponse(
        id=str(doc.get("_id", "")),
        user_id=doc.get("user_id"),
        game_id=doc.get("game_id", "wordle"),
        date=doc.get("date", ""),
        mode=doc.get("mode", "daily"),
        status=doc.get("status", "completed"),
        word=doc.get("word"),
        attempts=int(doc.get("attempts", 1)),
        stars=int(doc.get("stars", 1)),
        score=int(doc.get("score", 100)),
        grade=doc.get("grade"),
        remaining_attempts=int(doc.get("remaining_attempts", 0)),
        time_taken_seconds=doc.get("time_taken_seconds"),
        puntos_ganados=puntos_ganados,
        bonus_racha_puntos=int(doc.get("bonus_racha_puntos", 0)),
        bonus_racha_dias=int(doc.get("bonus_racha_dias", 0)),
        puntos_totales_usuario=puntos_totales_usuario,
        guesses=doc.get("guesses", []),
        game_data=doc.get("game_data"),
        updated_at=updated_at_str,
    )


def build_attempt_doc(
    req: UserAttemptCreateRequest,
    user_id: int,
    game_id: str,
    date: str,
    difficulty: str,
    time_taken: Optional[int],
    started_at: Optional[datetime],
    now: datetime,
    evaluated: AttemptEvaluation,
    bonus_puntos: int,
    bonus_dias: int,
) -> Dict[str, Any]:
    """Construye el documento de intento a persistir en MongoDB."""
    doc: Dict[str, Any] = {
        "user_id": user_id,
        "game_id": game_id,
        "date": date,
        "difficulty": difficulty,
        "mode": req.mode.lower().strip(),
        "status": evaluated.final_status,
        "word": req.word.strip() if req.word else None,
        "attempts": evaluated.attempts_value,
        "stars": evaluated.stars,
        "score": evaluated.score,
        "grade": evaluated.grade,
        "guesses": req.guesses or [],
        "game_data": req.game_data,
        "remaining_attempts": req.remaining_attempts or 0,
        "time_taken_seconds": time_taken,
        "updated_at": now,
    }
    if bonus_puntos > 0:
        doc["bonus_racha_puntos"] = bonus_puntos
        doc["bonus_racha_dias"] = bonus_dias
    # Momento real de cierre: las medallas se contabilizan por cuándo se jugó.
    if evaluated.final_status == "completed" and evaluated.validation_status != "rejected":
        doc["completed_at"] = now
    if started_at is not None:
        doc["started_at"] = started_at
    if evaluated.server_elapsed is not None:
        doc["server_elapsed_seconds"] = evaluated.server_elapsed
    if evaluated.time_suspect:
        doc["time_suspect"] = True
    if evaluated.validation_status:
        doc["validation_status"] = evaluated.validation_status
        if evaluated.validation_reason:
            doc["validation_reason"] = evaluated.validation_reason
    return doc


async def _apply_attempt_update(
    db: Any,
    filter_query: Dict[str, Any],
    existing: Optional[dict],
    doc: Dict[str, Any],
    difficulty: str,
    final_status: str,
    now: datetime,
    conflict_detail: str,
) -> dict:
    update_fields: Dict[str, Any] = {f"by_difficulty.{difficulty}": doc, "updated_at": now}
    if existing:
        _preserve_existing_difficulty(existing, difficulty, update_fields)
        if _should_replace_top_level(existing, final_status):
            update_fields.update(doc)
    result = await db["user_attempts"].find_one_and_update(
        filter_query, {"$set": update_fields}, return_document=True
    )
    if result is None:
        raise HTTPException(status_code=409, detail=conflict_detail)
    return result


async def persist_user_attempt_doc(
    db: Any,
    filter_query: Dict[str, Any],
    doc: Dict[str, Any],
    difficulty: str,
    final_status: str,
    now: datetime,
    existing: Optional[dict] = None,
) -> Tuple[dict, bool]:
    """Persiste un intento de forma atómica; devuelve (documento, es_replay)."""
    if existing:
        result = await _apply_attempt_update(
            db, filter_query, existing, doc, difficulty, final_status, now,
            "No se pudo actualizar la partida por un conflicto concurrente.",
        )
        return result, False

    initial = {**doc, "by_difficulty": {difficulty: dict(doc)}}
    try:
        result = await db["user_attempts"].find_one_and_update(
            filter_query,
            {"$set": initial, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=True,
        )
        return result, False
    except DuplicateKeyError:
        # Otra request insertó el mismo slot: se resuelve como replay o actualización.
        current = await db["user_attempts"].find_one(filter_query)
        if _difficulty_is_completed(current, difficulty):
            return current, True
        result = await _apply_attempt_update(
            db, filter_query, current, doc, difficulty, final_status, now,
            "No se pudo guardar la partida por un conflicto concurrente.",
        )
        return result, False
