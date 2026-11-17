"""Orquestación y casos de uso de intentos de partidas de usuarios."""

import calendar
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pymongo import ASCENDING

from app.core.database import get_database
from app.features.economy.streak_bonus import BonusRachaAplicado, SIN_BONUS, resolver_bonus_racha
from app.features.user_attempts.grading import _parse_errors, _tier_value, calculate_grade_and_score
from app.features.user_attempts.repository import (
    AttemptEvaluation,
    _as_utc, _attempt_snapshot, _attempt_started_at, _difficulty_is_completed,
    _doc_difficulty, _is_completed_attempt, _normalize_difficulty,
    _preserve_existing_difficulty, _serialize_attempt, _server_elapsed_seconds,
    _should_replace_top_level, build_attempt_doc, persist_user_attempt_doc,
)
from app.features.user_attempts.schemas import (
    UserAttemptCreateRequest,
    UserAttemptResponse,
    UserAttemptsListResponse,
)
from app.features.user_attempts.validation import Submission, is_enforcement_enabled, validate_submission
from app.shared.economy_points import DEFAULT_PUNTOS_POR_CALIFICACION
from app.shared.ledger import LedgerKey, get_points_ledger
from app.shared.streak import registrar_ingreso_y_racha

logger = logging.getLogger(__name__)


async def _register_replay_rejection(
    user_id: int, game_id: str, date: str, difficulty: str, status: str
) -> None:
    try:
        await get_points_ledger().record_event(
            user_id=user_id, motivo="replay_rejected", puntos=0,
            idempotency_key=f"replay:{user_id}:{game_id}:{date}:{difficulty}:{status}",
            metadata={"game_id": game_id, "date": date, "difficulty": difficulty, "status": status, "actor": "system"},
            status="rejected",
        )
    except Exception as e:
        logger.warning(f"No se pudo auditar el replay de {user_id}/{game_id}/{date}: {e}")


async def _reject_replay(
    ledger: Any, doc: dict, user_id: int, game_id: str, date: str, difficulty: str, status: str
) -> UserAttemptResponse:
    await _register_replay_rejection(user_id, game_id, date, difficulty, status)
    return _serialize_attempt(doc, puntos_ganados=0, puntos_totales_usuario=await ledger.saldo(user_id))


async def _load_economy_config(game_id: str) -> Tuple[Any, Dict[str, int], Optional[List[Any]]]:
    from app.features.economy.service import get_economy_config

    econ_config = None
    try:
        econ_config = await get_economy_config()
        puntos_config = econ_config.puntos_por_calificacion
    except Exception as e:
        logger.warning(f"No se pudo cargar la configuración de economía: {e}")
        puntos_config = dict(DEFAULT_PUNTOS_POR_CALIFICACION)

    escalas = (
        econ_config.escalas_tiempo_por_juego.get(game_id)
        if getattr(econ_config, "escalas_tiempo_por_juego", None)
        else None
    )
    return econ_config, puntos_config, escalas


def _extract_client_time(req: UserAttemptCreateRequest) -> Optional[int]:
    raw = req.time_taken_seconds
    if raw is None and req.game_data:
        raw = (
            req.game_data.get("timeTaken")
            or req.game_data.get("time_taken_seconds")
            or req.game_data.get("elapsedSeconds")
            or req.game_data.get("elapsed_seconds")
        )
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_status(raw_status: str) -> str:
    norm = raw_status.lower().strip()
    if norm in ("completed", "won"):
        return "completed"
    return "failed" if norm in ("failed", "lost") else "in_progress"


async def _evaluate_attempt(
    req: UserAttemptCreateRequest, user_id: int, game_id: str, date: str, difficulty: str,
    final_status: str, time_taken: Optional[int], server_elapsed: Optional[int],
    time_suspect: bool, puntos_config: Dict[str, int], escalas_juego: Optional[List[Any]],
) -> AttemptEvaluation:
    validation_status: Optional[str] = None
    validation_reason: Optional[str] = None
    attempts_val = req.attempts
    effective_time = time_taken
    effective_game_data = req.game_data
    provided_grade, provided_score, provided_stars = req.grade, req.score, req.stars

    if final_status == "completed" and is_enforcement_enabled(game_id):
        errors = _parse_errors(req.game_data)
        submission = Submission(
            word=req.word, guesses=req.guesses or [], attempts=req.attempts,
            errors=errors, game_data=req.game_data or {},
        )
        validation = await validate_submission(game_id, date, difficulty, submission)
        if not validation.valid:
            logger.info(f"[VALIDACION] Intento rechazado {user_id}/{game_id}/{date}/{difficulty}: {validation.reason}")
            return AttemptEvaluation(
                final_status=final_status, attempts_value=attempts_val, grade="F", score=0, stars=0,
                validation_status="rejected", validation_reason=validation.reason,
                server_elapsed=server_elapsed, time_suspect=time_suspect,
            )
        validation_status = "validated"
        attempts_val = validation.attempts if validation.attempts is not None else req.attempts
        effective_errors = validation.errors if validation.errors is not None else errors
        effective_game_data = {**(req.game_data or {}), "errors": effective_errors}
        if (time_suspect or effective_time is None) and server_elapsed is not None:
            effective_time = server_elapsed
        provided_grade = provided_score = provided_stars = None

    grade, score, stars = calculate_grade_and_score(
        game_id=game_id, status=req.status, attempts=attempts_val,
        remaining_attempts=req.remaining_attempts or 0, provided_grade=provided_grade,
        provided_score=provided_score, provided_stars=provided_stars,
        puntos_por_calificacion=puntos_config, game_data=effective_game_data,
        time_taken_seconds=effective_time, escalas_tiempo=escalas_juego,
    )
    if game_id == "wordle" and (attempts_val > 6 or (req.guesses and len(req.guesses) > 6)):
        final_status, grade, score, stars = "failed", "F", 0, 0

    return AttemptEvaluation(
        final_status=final_status, attempts_value=attempts_val, grade=grade, score=score,
        stars=stars, validation_status=validation_status, validation_reason=validation_reason,
        server_elapsed=server_elapsed, time_suspect=time_suspect,
    )


async def _resolve_streak_bonus(
    econ_config: Any, user_id: int, game_id: str, evaluated: AttemptEvaluation
) -> BonusRachaAplicado:
    if (
        econ_config is None or game_id == "narrativo" or evaluated.final_status != "completed"
        or evaluated.validation_status == "rejected" or evaluated.score <= 0
    ):
        return SIN_BONUS
    try:
        racha = await registrar_ingreso_y_racha(user_id)
        return resolver_bonus_racha(econ_config.bonus_racha, racha.actual, int(evaluated.score))
    except Exception as e:
        logger.warning(f"No se pudo calcular el bonus por racha de {user_id}: {e}")
        return SIN_BONUS


async def _credit_attempt_points(
    ledger: Any, user_id: int, game_id: str, date: str, difficulty: str,
    evaluated: AttemptEvaluation, bonus_racha: BonusRachaAplicado,
) -> Tuple[int, Optional[int]]:
    if evaluated.final_status != "completed" or evaluated.validation_status == "rejected":
        return 0, None
    puntos = int(evaluated.score) + bonus_racha.puntos
    res = await ledger.credit(
        LedgerKey(user_id=user_id, motivo="attempt", game_id=game_id, date=date, difficulty=difficulty),
        puntos,
        metadata={
            "grade": evaluated.grade, "difficulty": difficulty, "score_base": int(evaluated.score),
            "bonus_racha": bonus_racha.puntos, "racha_dias": bonus_racha.dias_tramo,
        },
    )
    if res.applied:
        logger.info(
            f"[PUNTOS] Usuario {user_id} ganó {puntos} pts (calificación {evaluated.grade}, "
            f"dificultad {difficulty}, bonus racha {bonus_racha.puntos}) en {game_id}. Saldo: {res.saldo}"
        )
        return puntos, res.saldo
    logger.info(
        f"[PUNTOS] Acreditación ya aplicada para {user_id}/{game_id}/{date}/{difficulty}; no se suman puntos."
    )
    return 0, res.saldo


async def save_user_attempt(
    req: UserAttemptCreateRequest, authenticated_user_id: Optional[int] = None
) -> UserAttemptResponse:
    """Guarda o actualiza un intento de partida de forma atómica e idempotente."""
    if authenticated_user_id is None:
        raise HTTPException(status_code=401, detail="Se requiere iniciar sesión para guardar progreso en la nube.")

    db, ledger = get_database(), get_points_ledger()
    user_id, game_id, date = int(authenticated_user_id), req.game_id.lower().strip(), req.date.strip()
    difficulty, now = _normalize_difficulty(req), datetime.now(timezone.utc)
    filter_query = {"user_id": user_id, "game_id": game_id, "date": date}

    econ_config, puntos_config, escalas_juego = await _load_economy_config(game_id)
    time_taken, final_status = _extract_client_time(req), _normalize_status(req.status)
    existing = await db["user_attempts"].find_one(filter_query)
    if _difficulty_is_completed(existing, difficulty):
        return await _reject_replay(ledger, existing, user_id, game_id, date, difficulty, final_status)

    started_at = _attempt_started_at(existing, difficulty)
    if final_status == "in_progress" and started_at is None:
        started_at = now
    server_elapsed, time_suspect = _server_elapsed_seconds(started_at, now, time_taken)

    evaluated = await _evaluate_attempt(
        req, user_id, game_id, date, difficulty, final_status,
        time_taken, server_elapsed, time_suspect, puntos_config, escalas_juego,
    )
    bonus = await _resolve_streak_bonus(econ_config, user_id, game_id, evaluated)
    doc = build_attempt_doc(
        req, user_id, game_id, date, difficulty, time_taken, started_at, now,
        evaluated, bonus.puntos, bonus.dias_tramo,
    )
    result, is_replay = await persist_user_attempt_doc(
        db, filter_query, doc, difficulty, evaluated.final_status, now, existing=existing
    )
    if is_replay:
        return await _reject_replay(ledger, result, user_id, game_id, date, difficulty, evaluated.final_status)

    puntos_ganados, puntos_totales = await _credit_attempt_points(
        ledger, user_id, game_id, date, difficulty, evaluated, bonus
    )
    if puntos_totales is None:
        puntos_totales = await ledger.saldo(user_id)
    return _serialize_attempt(result, puntos_ganados=puntos_ganados, puntos_totales_usuario=puntos_totales)


async def get_user_attempt_by_date(
    user_id: int, game_id: str, date: Optional[str] = None, date_str: Optional[str] = None
) -> Optional[UserAttemptResponse]:
    """Obtiene el intento de un usuario para un juego y fecha específicos."""
    target_date = (date or date_str or "").strip()
    doc = await get_database()["user_attempts"].find_one(
        {"user_id": user_id, "game_id": game_id.lower().strip(), "date": target_date}
    )
    return _serialize_attempt(doc) if doc else None


async def get_user_attempts_by_month(
    user_id: int, game_id: str, year: int, month: int
) -> UserAttemptsListResponse:
    """Obtiene todos los intentos de un usuario para un mes calendario."""
    days_in_month = calendar.monthrange(year, month)[1]
    start_date, end_date = f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{days_in_month:02d}"
    cursor = get_database()["user_attempts"].find({
        "user_id": user_id, "game_id": game_id.lower().strip(), "date": {"$gte": start_date, "$lte": end_date},
    }).sort("date", ASCENDING)
    items = [_serialize_attempt(d) for d in await cursor.to_list(length=31)]
    return UserAttemptsListResponse(
        user_id=user_id, game_id=game_id, year=year, month=month, total=len(items), attempts=items
    )
