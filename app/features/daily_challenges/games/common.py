"""Constantes, guardas y utilidades compartidas por la generación diaria."""

import calendar
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from fastapi import HTTPException

from app.core.database import get_database

MONTH_NAMES_ES = [
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

CRUCIGRAMA_DIFFICULTIES = ["facil", "dificil"]


def validate_month_bounds(year: int, month: int) -> Tuple[str, str, int]:
    """Valida el mes (1..12) y devuelve (start_date, end_date, days_in_month)."""
    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=400, detail="El mes debe estar comprendido entre 1 y 12."
        )
    _, days_in_month = calendar.monthrange(year, month)
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{days_in_month:02d}"
    return start_date, end_date, days_in_month


async def count_month_challenges(
    db: Any,
    game_id: str,
    start_date: str,
    end_date: str,
    difficulty: Optional[str] = None,
) -> int:
    """Cuenta los desafíos generados de un juego en el rango mensual."""
    query: Dict[str, Any] = {
        "game_id": game_id,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if difficulty is not None:
        query["difficulty"] = difficulty
    return await db["daily_challenges"].count_documents(query)


async def is_month_complete(
    db: Any,
    game_id: str,
    start_date: str,
    end_date: str,
    days_in_month: int,
    difficulties: Optional[Sequence[str]] = None,
) -> bool:
    """Indica si el mes está completo para todas las dificultades aplicables."""
    if difficulties:
        for diff in difficulties:
            count = await count_month_challenges(
                db, game_id, start_date, end_date, difficulty=diff
            )
            if count < days_in_month:
                return False
        return True
    return await count_month_challenges(db, game_id, start_date, end_date) >= days_in_month


def build_month_generation_result(
    game_id: str,
    year: int,
    month: int,
    days_in_month: int,
    generated_count: int,
    already_complete: bool = False,
) -> Dict[str, Any]:
    """Construye la respuesta estándar de generación mensual de desafíos."""
    result: Dict[str, Any] = {
        "success": True,
        "game_id": game_id,
        "year": year,
        "month": month,
        "month_name": MONTH_NAMES_ES[month - 1],
        "days_in_month": days_in_month,
        "generated_count": 0 if already_complete else generated_count,
    }
    if already_complete:
        result["already_complete"] = True
    return result


async def upsert_daily_challenge(
    db: Any,
    game_id: str,
    date_str: str,
    title: str,
    config: Dict[str, Any],
    difficulty: str = "standard",
    now_utc: Optional[datetime] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Crea o actualiza un desafío diario de forma idempotente."""
    timestamp = now_utc or datetime.now(timezone.utc)
    doc = {
        "game_id": game_id,
        "date": date_str,
        "difficulty": difficulty,
        "title": title,
        "config": config,
        "updated_at": timestamp,
        **(extra_fields or {}),
    }
    await db["daily_challenges"].update_one(
        {"game_id": game_id, "date": date_str, "difficulty": difficulty},
        {"$set": doc, "$setOnInsert": {"created_at": timestamp}},
        upsert=True,
    )


async def assert_month_regenerable(game_id: str, year: int, month: int) -> None:
    """
    Bloquea la regeneración forzada de un mes que ya tiene intentos registrados:
    cambiar las soluciones invalidaría las partidas jugadas.
    """
    start_date, end_date, _ = validate_month_bounds(year, month)
    db = get_database()
    intento = await db["user_attempts"].find_one(
        {"game_id": game_id, "date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 1},
    )
    if intento:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede regenerar {game_id} para {year}-{month:02d}: "
                "ya existen intentos de jugadores. Usá un mes futuro."
            ),
        )
