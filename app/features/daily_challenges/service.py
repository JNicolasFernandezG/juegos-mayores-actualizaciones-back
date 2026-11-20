"""Fachada de desafíos diarios: lectura, upsert y orquestación de generación.

La generación por juego vive en ``app.features.daily_challenges.games``.
Se reexportan los generadores para conservar los imports existentes (router,
``main`` y seeds).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo import ASCENDING

from app.core.database import get_database
from app.features.daily_challenges.games.common import (  # noqa: F401
    CRUCIGRAMA_DIFFICULTIES,
    MONTH_NAMES_ES,
    assert_month_regenerable,
    is_month_complete,
    validate_month_bounds,
)
from app.features.daily_challenges.games.coverage import get_challenges_monthly_status  # noqa: F401
from app.features.daily_challenges.games.crucigrama import generate_and_save_crucigrama_month  # noqa: F401
from app.features.daily_challenges.games.sopa import generate_and_save_sopa_month  # noqa: F401
from app.features.daily_challenges.games.sudoku import generate_and_save_sudoku_month  # noqa: F401
from app.features.daily_challenges.games.wordle import generate_and_save_wordle_month  # noqa: F401
from app.features.daily_challenges.schemas import (
    ChallengeRangeResponse,
    DailyChallengeCreateRequest,
    DailyChallengeResponse,
    MonthChallengesResponse,
)

logger = logging.getLogger(__name__)


def _serialize_challenge(doc: dict, today_str: Optional[str] = None) -> DailyChallengeResponse:
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")
    doc_date = doc.get("date", "")
    created_at = doc.get("created_at")
    created_at_str = (
        created_at.isoformat() if isinstance(created_at, datetime)
        else (str(created_at) if created_at else None)
    )
    return DailyChallengeResponse(
        id=str(doc.get("_id", "")),
        game_id=doc.get("game_id", ""),
        date=doc_date,
        difficulty=doc.get("difficulty", "standard"),
        title=doc.get("title"),
        config=doc.get("config", {}),
        is_today=(doc_date == today_str),
        is_past=(doc_date < today_str),
        is_future=(doc_date > today_str),
        created_at=created_at_str,
    )


async def get_challenge_by_date(
    game_id: str = "wordle", target_date: Optional[str] = None, difficulty: str = "standard"
) -> DailyChallengeResponse:
    """Busca el desafío de una fecha específica para un juego determinado."""
    db = get_database()
    today_str = datetime.now().strftime("%Y-%m-%d")
    date_to_query = target_date or today_str
    challenge = await db["daily_challenges"].find_one({
        "game_id": game_id, "date": date_to_query, "difficulty": difficulty,
    })
    if not challenge:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró desafío para el juego '{game_id}' en la fecha {date_to_query}",
        )
    return _serialize_challenge(challenge, today_str)


async def get_today_challenge(
    game_id: str = "wordle", difficulty: str = "standard"
) -> DailyChallengeResponse:
    """Obtiene el desafío de hoy para el juego especificado."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    return await get_challenge_by_date(game_id=game_id, target_date=today_str, difficulty=difficulty)


async def get_month_challenges(
    year: int, month: int, game_id: str = "wordle",
    difficulty: str = "standard", until_today: bool = False,
) -> MonthChallengesResponse:
    """Obtiene los desafíos de un mes específico respetando el tope real de días."""
    start_date, end_date, days_in_month = validate_month_bounds(year, month)
    if not (2020 <= year <= 2050):
        raise HTTPException(status_code=400, detail="Año fuera del rango admitido (2020-2050).")

    today_str = datetime.now().strftime("%Y-%m-%d")
    effective_end_date = today_str if (until_today and today_str < end_date) else end_date

    db = get_database()
    query = {
        "game_id": game_id,
        "difficulty": difficulty,
        "date": {"$gte": start_date, "$lte": effective_end_date},
    }
    results = await db["daily_challenges"].find(query).sort("date", ASCENDING).limit(days_in_month).to_list(length=days_in_month)
    challenges = [_serialize_challenge(doc, today_str) for doc in results]

    return MonthChallengesResponse(
        year=year, month=month, days_in_month=days_in_month,
        total_challenges=len(challenges), challenges=challenges,
    )


async def upsert_challenge(req: DailyChallengeCreateRequest) -> DailyChallengeResponse:
    """Crea o actualiza un desafío diario de forma idempotente."""
    db = get_database()
    now_utc = datetime.now(timezone.utc)
    today_str = datetime.now().strftime("%Y-%m-%d")
    doc = {
        "game_id": req.game_id.lower().strip(),
        "date": req.date.strip(),
        "difficulty": req.difficulty.lower().strip(),
        "title": req.title,
        "config": req.config,
        "updated_at": now_utc,
    }
    result = await db["daily_challenges"].find_one_and_update(
        {"game_id": doc["game_id"], "date": doc["date"], "difficulty": doc["difficulty"]},
        {"$set": doc, "$setOnInsert": {"created_at": now_utc}},
        upsert=True,
        return_document=True,
    )
    return _serialize_challenge(result, today_str)


async def get_challenge_date_range(game_id: str = "wordle") -> ChallengeRangeResponse:
    """Busca la fecha mínima y máxima con desafíos disponibles para un juego."""
    db = get_database()
    first_doc = await db["daily_challenges"].find_one({"game_id": game_id}, sort=[("date", ASCENDING)])
    last_doc = await db["daily_challenges"].find_one({"game_id": game_id}, sort=[("date", -1)])
    return ChallengeRangeResponse(
        game_id=game_id,
        min_date=first_doc.get("date") if first_doc else None,
        max_date=last_doc.get("date") if last_doc else None,
    )


async def _generate_game_month(game: str, year: int, month: int) -> None:
    if game == "sudoku":
        await generate_and_save_sudoku_month(year, month)
    elif game == "wordle":
        await generate_and_save_wordle_month(year, month)
    elif game == "sopa_letras":
        await generate_and_save_sopa_month(year, month)
    elif game == "crucigrama":
        await generate_and_save_crucigrama_month(year, month)
    elif game == "narrativo":
        try:
            from app.features.narrative.admin.challenge_service import generar_mes_narrativo
            await generar_mes_narrativo(year=year, month=month, universo_id="corte_medieval")
        except Exception as e_narr:
            logger.warning(f"Error autogenerando mes narrativo {year}-{month:02d}: {e_narr}")


async def ensure_current_and_next_month_generated(game_id: Optional[str] = None):
    """Genera el mes actual y el siguiente si falta algún día para los juegos registrados."""
    games = [game_id] if game_id else ["sudoku", "wordle", "sopa_letras", "crucigrama", "narrativo"]
    now = datetime.now()
    cur_year, cur_month = now.year, now.month
    next_year, next_month = (cur_year + 1, 1) if cur_month == 12 else (cur_year, cur_month + 1)

    targets = [(cur_year, cur_month), (next_year, next_month)]
    db = get_database()

    for g in games:
        for y, m in targets:
            start_date, end_date, days_in_month = validate_month_bounds(y, m)
            difficulties = CRUCIGRAMA_DIFFICULTIES if g == "crucigrama" else None
            if not await is_month_complete(
                db, g, start_date, end_date, days_in_month, difficulties=difficulties
            ):
                logger.info(f"[AUTOGENERACIÓN] Juego '{g}' mes {y}-{m:02d} incompleto. Generando...")
                await _generate_game_month(g, y, m)
