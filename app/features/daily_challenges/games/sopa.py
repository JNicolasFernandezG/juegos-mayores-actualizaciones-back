"""Generación y persistencia de desafíos diarios de Sopa de Letras."""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.database import get_database
from app.features.daily_challenges.games.common import (
    build_month_generation_result,
    count_month_challenges,
    upsert_daily_challenge,
    validate_month_bounds,
)
from app.features.daily_challenges.sopa_generator import generate_sopa_challenge_for_date

logger = logging.getLogger(__name__)


async def generate_and_save_sopa_month(year: int, month: int, force: bool = False) -> dict:
    """
    Genera y guarda de forma atómica e idempotente los desafíos diarios de Sopa de Letras
    para el mes y año especificados, enriqueciendo las pistas con definiciones de la RAE.
    Si force=False, saltea instantáneamente en 0ms si el mes ya está completo.
    """
    start_date, end_date, days_in_month = validate_month_bounds(year, month)
    db = get_database()
    now_utc = datetime.now(timezone.utc)

    if not force:
        existing_count = await count_month_challenges(db, "sopa_letras", start_date, end_date)
        if existing_count >= days_in_month:
            logger.info(f"[SOPA_LETRAS] Mes {year}-{month:02d} ya está completamente generado ({existing_count}/{days_in_month}). Saltando en 0ms.")
            return build_month_generation_result(
                "sopa_letras", year, month, days_in_month, 0, already_complete=True
            )

    generated_count = 0

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"

        if not force:
            existing = await db["daily_challenges"].find_one({
                "game_id": "sopa_letras",
                "date": date_str,
            })
            if existing and existing.get("config", {}).get("grid"):
                continue

        sopa_data = await asyncio.to_thread(generate_sopa_challenge_for_date, date_str)
        await upsert_daily_challenge(
            db,
            game_id="sopa_letras",
            date_str=date_str,
            title=f"Sopa de Letras: {sopa_data['theme']} ({date_str})",
            config=sopa_data,
            now_utc=now_utc,
        )
        generated_count += 1
        await asyncio.sleep(0.15)

    logger.info(f"[SOPA_LETRAS] {generated_count} desafíos de Sopa de Letras generados para {year}-{month:02d}.")
    return build_month_generation_result("sopa_letras", year, month, days_in_month, generated_count)
