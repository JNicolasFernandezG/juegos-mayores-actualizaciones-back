"""Desbloqueo de días históricos con puntos o suscripción Premium."""

import logging
from typing import Any

from fastapi import HTTPException, status

from app.core.database import get_database
from app.features.economy.config import get_economy_config
from app.features.economy.points import debit_user_points

logger = logging.getLogger("EconomyService")


async def unlock_historical_day(
    user_id: int,
    game_id: str,
    date_str: str,
) -> Any:
    """
    Desbloquea un desafío de un día anterior gastando puntos para usuarios Básicos,
    o de forma automática e ilimitada para usuarios Premium.
    """
    db = get_database()
    config = await get_economy_config()
    clean_game = game_id.lower().strip()
    clean_date = date_str.strip()
    unlock_key = f"{clean_game}:{clean_date}"

    user = await db["usuarios"].find_one({"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario {user_id} no encontrado.",
        )

    suscripcion = str(user.get("suscripcion", "basica")).lower()
    puntos_actuales = int(user.get("puntos", 0))
    dias_desbloqueados = user.get("dias_desbloqueados", [])

    if suscripcion == "premium":
        return {
            "success": True,
            "unlocked": True,
            "puntos": puntos_actuales,
            "costo": 0,
            "date": clean_date,
            "game_id": clean_game,
            "message": "Acceso concedido por suscripción Premium.",
        }

    if unlock_key in dias_desbloqueados:
        return {
            "success": True,
            "unlocked": True,
            "puntos": puntos_actuales,
            "costo": 0,
            "date": clean_date,
            "game_id": clean_game,
            "message": "Este desafío ya fue desbloqueado previamente.",
        }

    costo = config.costo_desbloqueo_dia_puntos
    result = await debit_user_points(
        db,
        user_id,
        costo,
        extra_update={"$addToSet": {"dias_desbloqueados": unlock_key}},
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Puntos insuficientes. Necesitás {costo} pts para desbloquear este día y tenés {puntos_actuales} pts.",
        )

    nuevos_puntos = int(result.get("puntos", 0))
    logger.info(
        f"[DESBLOQUEO DIA] Usuario {user_id} desbloqueó '{unlock_key}' por {costo} pts. "
        f"Saldo restante: {nuevos_puntos} pts."
    )

    return {
        "success": True,
        "unlocked": True,
        "puntos": nuevos_puntos,
        "costo": costo,
        "date": clean_date,
        "game_id": clean_game,
        "message": f"¡Desafío desbloqueado exitosamente por {costo} puntos!",
    }
