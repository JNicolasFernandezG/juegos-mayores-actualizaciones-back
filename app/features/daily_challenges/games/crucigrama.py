"""Generación y persistencia de desafíos diarios de Crucigrama (fácil y difícil)."""

import asyncio
import calendar  # noqa: F401 - Conservado para monkeypatching en tests de integración.
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.database import get_database
from app.features.daily_challenges.crucigrama import generate_crucigrama_challenge_for_date
from app.features.daily_challenges.crucigrama.bans import get_global_banned_words
from app.features.daily_challenges.crucigrama.published_templates import (
    get_recurring_published_config,
    get_scheduled_published_config,
)
from app.features.daily_challenges.games.common import (
    CRUCIGRAMA_DIFFICULTIES,
    build_month_generation_result,
    is_month_complete,
    upsert_daily_challenge,
    validate_month_bounds,
)

logger = logging.getLogger(__name__)


async def _resolve_crucigrama_day_config(
    date_str: str,
    diff: str,
    global_bans: List[str],
) -> Dict[str, Any]:
    crucigrama_data = await get_scheduled_published_config(date_str, diff)
    if not crucigrama_data:
        crucigrama_data = await get_recurring_published_config(date_str, diff, global_bans)
    if crucigrama_data:
        crucigrama_data = dict(crucigrama_data)
        crucigrama_data["date"] = date_str
        return crucigrama_data

    return await asyncio.to_thread(
        generate_crucigrama_challenge_for_date,
        date_str,
        diff,
        banned_words=global_bans,
    )


async def generate_and_save_crucigrama_month(year: int, month: int, force: bool = False) -> dict:
    """
    Genera y guarda de forma atómica e idempotente los desafíos diarios de Crucigrama
    en sus dos dificultades (facil 7x7 y dificil 11x11) para el mes y año especificados.
    Si force=False, saltea instantáneamente en 0ms si el mes ya está completo para ambas.
    """
    start_date, end_date, days_in_month = validate_month_bounds(year, month)
    db = get_database()
    now_utc = datetime.now(timezone.utc)

    if not force and await is_month_complete(
        db, "crucigrama", start_date, end_date, days_in_month, difficulties=CRUCIGRAMA_DIFFICULTIES
    ):
        logger.info(f"[CRUCIGRAMA] Mes {year}-{month:02d} ya está completamente generado en {len(CRUCIGRAMA_DIFFICULTIES)} dificultades. Saltando en 0ms.")
        return build_month_generation_result(
            "crucigrama", year, month, days_in_month, 0, already_complete=True
        )

    generated_count = 0
    global_bans = await get_global_banned_words()

    for day in range(1, days_in_month + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"

        for diff in CRUCIGRAMA_DIFFICULTIES:
            if not force:
                existing = await db["daily_challenges"].find_one(
                    {"game_id": "crucigrama", "date": date_str, "difficulty": diff}
                )
                if existing and existing.get("config", {}).get("cells"):
                    continue

            crucigrama_data = await _resolve_crucigrama_day_config(date_str, diff, global_bans)
            await upsert_daily_challenge(
                db, game_id="crucigrama", date_str=date_str, difficulty=diff,
                title=f"Crucigrama ({diff.capitalize()}): {crucigrama_data['theme']} ({date_str})",
                config=crucigrama_data, now_utc=now_utc,
            )
            generated_count += 1

        await asyncio.sleep(0.1)

    logger.info(f"[CRUCIGRAMA] {generated_count} desafíos de Crucigrama generados para {year}-{month:02d}.")
    return build_month_generation_result("crucigrama", year, month, days_in_month, generated_count)
