"""Pistas: resolución idempotente y cobro posterior a la entrega."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.features.economy.config import get_economy_config
from app.features.economy.points import debit_user_points
from app.features.economy.schemas import UseHintResponse
from app.shared.clock import today_str

logger = logging.getLogger("EconomyService")

COLL_HINTS = "user_hints"


async def _find_hint_challenge(db: Any, game_id: str, target_date: str, difficulty: str) -> Optional[dict]:
    challenge = await db["daily_challenges"].find_one(
        {"game_id": game_id, "date": target_date, "difficulty": difficulty}
    )
    if challenge:
        return challenge
    candidates = await db["daily_challenges"].find(
        {"game_id": game_id, "date": target_date}
    ).limit(2).to_list(length=2)
    return candidates[0] if len(candidates) == 1 else None


def _resolve_crucigrama_hint(config: dict, req: Any, idx: int) -> Tuple[Optional[str], Any, str]:
    words = config.get("words") or []
    if req.row is not None and req.col is not None:
        hint_key = f"cell:{req.row}:{req.col}"
        for w in words:
            word_str = w.get("word", "")
            for i, coord in enumerate(w.get("coords") or []):
                if len(coord) >= 2 and coord[0] == req.row and coord[1] == req.col and i < len(word_str):
                    val = word_str[i]
                    return (f"La letra en ({req.row + 1}, {req.col + 1}) es '{val}'", val, hint_key)
        return (None, None, hint_key)
    if words and 0 <= idx < len(words):
        texto = f"{words[idx].get('direction', 'Horiz.')} {words[idx].get('number', '')}: {words[idx].get('clue', '')}"
        return (texto, None, f"word:{idx}")
    return (None, None, f"hint:{idx}")


def _resolve_hint(config: dict, game: str, req: Any) -> Tuple[Optional[str], Any, str]:
    """Devuelve (texto, valor_revelado, hint_key) sin cobrar nada."""
    idx = req.hint_index or 0
    if game == "wordle":
        hints = config.get("hints") or []
        if hints:
            idx = idx if 0 <= idx < len(hints) else 0
            return (hints[idx], None, f"hint:{idx}")
        if config.get("solution"):
            return (f"Empieza con la letra '{config['solution'][0]}'", None, "letter:first")
    elif game == "sudoku":
        sol = config.get("solution")
        if sol and req.row is not None and req.col is not None and 0 <= req.row < 9 and 0 <= req.col < 9:
            val = sol[req.row][req.col]
            return (f"El número en la fila {req.row + 1}, columna {req.col + 1} es {val}", val, f"cell:{req.row}:{req.col}")
    elif game == "sopa_letras":
        hints, words = config.get("hints") or [], config.get("words") or []
        if hints and 0 <= idx < len(hints):
            return (hints[idx], None, f"hint:{idx}")
        if words and 0 <= idx < len(words):
            return (f"Palabra a buscar: {words[idx]}", None, f"word:{idx}")
    elif game == "crucigrama":
        return _resolve_crucigrama_hint(config, req, idx)
    return (None, None, f"hint:{idx}")


def _build_hint_response(
    user: dict,
    *,
    puntos_descontados: int,
    pista: Optional[str],
    valor_revelado: Any,
    message: str,
) -> UseHintResponse:
    return UseHintResponse(
        success=True,
        puntos_restantes=int(user.get("puntos", 0)),
        puntos_descontados=puntos_descontados,
        vidas_restantes=int(user.get("vidas") or 5),
        vidas_descontadas=0,
        pista=pista,
        valor_revelado=valor_revelado,
        message=message,
    )


async def _hint_response_from_record(record: dict, user: dict, costo: int, replayed: bool) -> UseHintResponse:
    msg = (
        "Esta pista ya fue desbloqueada; no se descontaron puntos."
        if replayed
        else f"Pista desbloqueada exitosamente (-{costo} puntos)."
    )
    return _build_hint_response(
        user,
        puntos_descontados=0,
        pista=record.get("pista"),
        valor_revelado=record.get("valor_revelado"),
        message=msg,
    )


async def _resolve_difficulty(db: Any, user_id: int, game: str, target_date: str, raw_diff: Optional[str]) -> str:
    difficulty = (raw_diff or "").strip().lower()
    if difficulty:
        return difficulty
    attempt = await db["user_attempts"].find_one(
        {"user_id": user_id, "game_id": game, "date": target_date}
    )
    return str((attempt or {}).get("difficulty") or "standard").lower() or "standard"


async def use_hint(user_id: int, req: Any) -> UseHintResponse:
    """Entrega una pista y descuenta puntos solo si hay contenido y no se entregó antes."""
    db = get_database()
    config = await get_economy_config()
    costo = int(config.costo_pista_puntos or 20)

    game = req.game_id.lower().strip()
    target_date = req.date or today_str()
    difficulty = await _resolve_difficulty(db, user_id, game, target_date, req.difficulty)

    user = await db["usuarios"].find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Usuario {user_id} no encontrado.")

    challenge = await _find_hint_challenge(db, game, target_date, difficulty)
    pista_texto, valor_revelado, hint_key = None, None, f"hint:{req.hint_index or 0}"
    if challenge and "config" in challenge:
        try:
            pista_texto, valor_revelado, hint_key = _resolve_hint(challenge["config"] or {}, game, req)
        except Exception as e:
            logger.warning(f"[ECONOMIA] No se pudo resolver la pista de {game}: {e}")

    if pista_texto is None and valor_revelado is None:
        return _build_hint_response(
            user,
            puntos_descontados=0,
            pista=None,
            valor_revelado=None,
            message="No hay pista disponible para este desafío; no se descontaron puntos.",
        )

    hint_filter = {
        "user_id": user_id, "game_id": game, "date": target_date,
        "difficulty": difficulty, "hint_key": hint_key,
    }
    existing = await db[COLL_HINTS].find_one(hint_filter)
    if existing:
        return await _hint_response_from_record(existing, user, costo, replayed=True)

    now = datetime.now(timezone.utc)
    record = {
        **hint_filter, "pista": pista_texto, "valor_revelado": valor_revelado,
        "status": "pending", "created_at": now, "updated_at": now,
    }
    try:
        await db[COLL_HINTS].insert_one(record)
    except DuplicateKeyError:
        existing = await db[COLL_HINTS].find_one(hint_filter)
        if existing:
            return await _hint_response_from_record(existing, user, costo, replayed=True)
        raise

    result = await debit_user_points(db, user_id, costo, now=now)
    if not result:
        await db[COLL_HINTS].delete_one({"_id": record["_id"]})
        user_actual = await db["usuarios"].find_one({"id": user_id})
        puntos_actuales = int(user_actual.get("puntos", 0)) if user_actual else 0
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Puntos insuficientes para pedir una pista. Cuesta {costo} pts y tenés {puntos_actuales} pts.",
        )

    nuevos_puntos = int(result.get("puntos", 0))
    await db[COLL_HINTS].update_one(
        {"_id": record["_id"]},
        {"$set": {"status": "applied", "puntos_descontados": costo, "saldo_despues": nuevos_puntos, "updated_at": now}},
    )
    logger.info(
        f"[ECONOMIA] Usuario {user_id} consumió {costo} pts por pista en "
        f"{game}/{difficulty}/{target_date}. Restan: {nuevos_puntos} pts"
    )
    return _build_hint_response(
        result,
        puntos_descontados=costo,
        pista=pista_texto,
        valor_revelado=valor_revelado,
        message=f"Pista desbloqueada exitosamente (-{costo} puntos).",
    )
