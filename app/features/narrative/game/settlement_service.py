"""
settlement_service.py
Calificación de intentos narrativos, persistencia en `user_attempts` y acreditación
idempotente de puntos en el ledger económico (para cuentas e invitados).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.features.narrative.constants import COLL_USER_ATTEMPTS
from app.shared.economy_points import (
    DEFAULT_PUNTOS_POR_CALIFICACION,
    obtener_puntos_por_calificacion,
)
from app.shared.ledger import LedgerKey, get_points_ledger

logger = logging.getLogger(__name__)

# Estrellas por rango: mismo criterio que muestra el panel de administración.
ESTRELLAS_POR_RANGO = {"S": 3, "A": 3, "B": 2, "C": 1, "F": 0}


def estrellas_por_rango(rango: str) -> int:
    return ESTRELLAS_POR_RANGO.get(rango, 0)


def calificar_intento(
    rango: str,
    puntos_por_calificacion: Dict[str, int],
    *,
    completado: bool,
) -> tuple[int, int]:
    """Puntaje y estrellas del intento según el catálogo editable del panel."""
    if not completado:
        return 0, 0
    return int(puntos_por_calificacion.get(rango, 0)), estrellas_por_rango(rango)


async def registrar_intento_narrativo(
    user_id: int,
    date_str: str,
    *,
    status_str: str,
    attempts: int,
    stars: int,
    score: int,
    grade: str,
    game_data: Dict[str, Any],
) -> None:
    """Upsert del intento diario; el primer intento completado no se degrada."""
    try:
        ahora = datetime.now(timezone.utc)
        campos: Dict[str, Any] = {
            "user_id": user_id,
            "game_id": "narrativo",
            "date": date_str,
            "difficulty": "normal",
            "mode": "daily",
            "status": status_str,
            "attempts": attempts,
            "stars": stars,
            "score": score,
            "grade": grade,
            "game_data": game_data,
            "updated_at": ahora,
        }
        if status_str == "completed":
            campos["completed_at"] = ahora
        await get_database()[COLL_USER_ATTEMPTS].update_one(
            {
                "user_id": user_id,
                "game_id": "narrativo",
                "date": date_str,
                "status": {"$ne": "completed"},
            },
            {"$set": campos},
            upsert=True,
        )
    except DuplicateKeyError:
        pass


async def _liquidar_invitado(
    db: Any,
    guest_id: str,
    date_str: str,
    grade: str,
    rango: str,
    mes_final: int,
    is_completed: bool,
) -> int:
    if not is_completed:
        return 0
    puntos_config = await obtener_puntos_por_calificacion()
    puntos = int(puntos_config.get(grade, 0))
    idempotency_key = f"guest_narrative:{guest_id}:narrativo:{date_str}"
    if await db["economy_ledger"].find_one({"_id": idempotency_key}):
        return 0
    await get_points_ledger().record_event(
        user_id=0,
        motivo="guest_narrative",
        puntos=puntos,
        idempotency_key=idempotency_key,
        metadata={
            "guest_id": guest_id,
            "game_id": "narrativo",
            "date": date_str,
            "difficulty": "normal",
            "grade": grade,
            "rango": rango,
            "mes_final": mes_final,
        },
        status="recorded",
    )
    return puntos


async def _liquidar_cuenta(
    run_doc: Dict[str, Any], user_id: int, date_str: str, grade: str, rango: str, mes_final: int, is_completed: bool
) -> int:
    status_str = "completed" if is_completed else "failed"
    puntos_config = await obtener_puntos_por_calificacion()
    score, stars = calificar_intento(grade, puntos_config, completado=is_completed)
    await registrar_intento_narrativo(
        user_id, date_str, status_str=status_str, attempts=mes_final, stars=stars, score=score, grade=grade,
        game_data={
            "rango": rango, "mes_final": mes_final,
            "recursos_finales": run_doc.get("recursos", {}), "finalizacion": run_doc.get("finalizacion"),
        },
    )
    if not is_completed or score <= 0:
        return 0
    resultado = await get_points_ledger().credit(
        LedgerKey(user_id=user_id, motivo="attempt", game_id="narrativo", date=date_str, difficulty="normal"),
        score, metadata={"grade": grade, "rango": rango, "source": "narrativo"},
    )
    return score if resultado.applied else 0


async def sincronizar_intento_usuario(run_doc: Dict[str, Any]) -> int:
    """
    Registra el intento narrativo y acredita puntos al cerrar la partida.
    Devuelve los puntos ganados en esta llamada (0 si es replay, derrota o invitado repetido).
    """
    try:
        db = get_database()
        user_id = int(run_doc.get("user_id") or 0)
        guest_id = run_doc.get("guest_id")
        date_str = run_doc.get("date")
        if not date_str or (user_id <= 0 and not guest_id):
            return 0

        is_completed = run_doc.get("status") == "completed"
        rango = run_doc.get("finalizacion", {}).get("rango", "F")
        grade = rango if rango in DEFAULT_PUNTOS_POR_CALIFICACION else "F"
        mes_final = run_doc.get("mes_actual", 1)

        if guest_id:
            return await _liquidar_invitado(db, guest_id, date_str, grade, rango, mes_final, is_completed)
        return await _liquidar_cuenta(run_doc, user_id, date_str, grade, rango, mes_final, is_completed)
    except Exception as e:
        logger.warning(f"Aviso al sincronizar partida narrativa con user_attempts: {e}")
        return 0
