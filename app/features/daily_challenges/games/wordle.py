"""Generación y persistencia de desafíos diarios de Wordle."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from app.core.database import get_database
from app.features.daily_challenges.games.common import (
    build_month_generation_result,
    count_month_challenges,
    upsert_daily_challenge,
    validate_month_bounds,
)
from app.features.daily_challenges.wordle_generator import (
    generate_wordle_challenge,
    generate_wordle_hints,
)

logger = logging.getLogger(__name__)


async def _load_used_wordle_words(db: Any) -> Set[str]:
    cursor = db["daily_challenges"].find({"game_id": "wordle"}, {"config.solution": 1})
    used_words: Set[str] = set()
    async for doc in cursor:
        sol = doc.get("config", {}).get("solution")
        if sol:
            used_words.add(sol.upper().strip())
    return used_words


async def _build_wordle_day_config(
    date_str: str,
    day: int,
    existing: Optional[Dict[str, Any]],
    used_words: Set[str],
) -> Dict[str, Any]:
    existing_solution = existing.get("config", {}).get("solution") if existing else None
    if existing_solution:
        sol = existing_solution.upper().strip()
        hints = await asyncio.to_thread(generate_wordle_hints, sol)
        return {
            "solution": sol,
            "word_length": 5,
            "max_attempts": 6,
            "hints": hints,
        }

    challenge_config = await asyncio.to_thread(
        generate_wordle_challenge, date_str, used_words, index=day
    )
    used_words.add(challenge_config["solution"])
    return challenge_config


async def generate_and_save_wordle_month(year: int, month: int, force: bool = False) -> dict:
    """
    Genera y guarda de forma atómica e idempotente los desafíos diarios de Wordle
    para el mes y año especificados, extrayendo palabras del pool de 4.933 palabras frecuentes.
    Si force=False, saltea instantáneamente en 0ms si el mes ya está completo.
    Si force=True, refresca las pistas y definiciones de la RAE respetando las soluciones existentes.
    """
    start_date, end_date, days_in_month = validate_month_bounds(year, month)
    db = get_database()
    now_utc = datetime.now(timezone.utc)

    if not force:
        existing_count = await count_month_challenges(db, "wordle", start_date, end_date)
        if existing_count >= days_in_month:
            logger.info(f"[WORDLE] Mes {year}-{month:02d} ya está completamente generado ({existing_count}/{days_in_month}). Saltando en 0ms.")
            return build_month_generation_result(
                "wordle", year, month, days_in_month, 0, already_complete=True
            )

    used_words = await _load_used_wordle_words(db)
    generated_count = 0

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        existing = await db["daily_challenges"].find_one({"game_id": "wordle", "date": date_str})

        if not force and existing and existing.get("config", {}).get("solution"):
            used_words.add(existing["config"]["solution"].upper().strip())
            continue

        challenge_config = await _build_wordle_day_config(date_str, day, existing, used_words)
        await upsert_daily_challenge(
            db,
            game_id="wordle",
            date_str=date_str,
            title=f"Palabra del Día ({date_str})",
            config=challenge_config,
            now_utc=now_utc,
        )
        generated_count += 1
        await asyncio.sleep(0.2)

    logger.info(f"[WORDLE] {generated_count} desafíos de Wordle actualizados/generados para {year}-{month:02d}.")
    return build_month_generation_result("wordle", year, month, days_in_month, generated_count)
