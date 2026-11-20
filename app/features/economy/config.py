"""Configuración global de economía (lectura, actualización y defaults)."""

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import ValidationError

from app.core.database import get_database
from app.features.economy.defaults import (
    DEFAULT_BONUS_RACHA,
    DEFAULT_ESCALAS_TIEMPO,
    DEFAULT_PUNTOS_POR_CALIFICACION,
    DEFAULT_PUNTOS_POR_JUEGO,
)
from app.features.economy.schemas import (
    BonusRachaConfig,
    EconomyConfigResponse,
    EconomyConfigUpdateRequest,
    EscalaCalificacionTiempo,
)

logger = logging.getLogger("EconomyService")

COLL_CONFIG = "configuracion_economia"

DEFAULT_ECONOMY_CONFIG: Dict[str, Any] = {
    "_id": "global_economy",
    "vidas_iniciales": 5,
    "costo_desbloqueo_dia_puntos": 100,
    "costo_pista_puntos": 20,
    "puntos_por_calificacion": dict(DEFAULT_PUNTOS_POR_CALIFICACION),
    "guest_migration_max_points": 1000,
    "bonus_racha": deepcopy(DEFAULT_BONUS_RACHA),
    "escalas_tiempo_por_juego": deepcopy(DEFAULT_ESCALAS_TIEMPO),
    "puntos_por_juego": dict(DEFAULT_PUNTOS_POR_JUEGO),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}


def _ordenar_tramos_bonus(bonus: BonusRachaConfig) -> BonusRachaConfig:
    return bonus.model_copy(
        update={"tramos": sorted(bonus.tramos, key=lambda tramo: tramo.dias)}
    )


def _normalizar_bonus_racha(raw: Any) -> BonusRachaConfig:
    """Normaliza el bonus guardado; ante datos inválidos cae a los defaults inactivos."""
    if not isinstance(raw, dict):
        raw = DEFAULT_BONUS_RACHA
    try:
        bonus = BonusRachaConfig(**raw)
    except (ValidationError, TypeError):
        logger.warning("[ECONOMIA] bonus_racha inválido en la base; se usan los defaults inactivos.")
        bonus = BonusRachaConfig(**DEFAULT_BONUS_RACHA)
    return _ordenar_tramos_bonus(bonus)


async def get_economy_config() -> EconomyConfigResponse:
    """Obtiene la configuración económica global; si no existe, la siembra con defaults."""
    db = get_database()
    doc = await db[COLL_CONFIG].find_one({"_id": "global_economy"})
    if not doc:
        now_str = datetime.now(timezone.utc).isoformat()
        initial = deepcopy(DEFAULT_ECONOMY_CONFIG)
        initial["updated_at"] = now_str
        await db[COLL_CONFIG].update_one(
            {"_id": "global_economy"}, {"$setOnInsert": initial}, upsert=True
        )
        doc = await db[COLL_CONFIG].find_one({"_id": "global_economy"}) or initial

    raw_escalas = doc.get("escalas_tiempo_por_juego") or DEFAULT_ESCALAS_TIEMPO
    escalas_map: Dict[str, List[EscalaCalificacionTiempo]] = {
        gid: [EscalaCalificacionTiempo(**item) for item in items]
        for gid, items in raw_escalas.items()
    }

    return EconomyConfigResponse(
        vidas_iniciales=int(doc.get("vidas_iniciales", 5)),
        costo_desbloqueo_dia_puntos=int(doc.get("costo_desbloqueo_dia_puntos", 100)),
        costo_pista_puntos=int(doc.get("costo_pista_puntos", 20)),
        puntos_por_calificacion=doc.get("puntos_por_calificacion", DEFAULT_ECONOMY_CONFIG["puntos_por_calificacion"]),
        escalas_tiempo_por_juego=escalas_map,
        puntos_por_juego=doc.get("puntos_por_juego", DEFAULT_ECONOMY_CONFIG["puntos_por_juego"]),
        guest_migration_max_points=int(
            doc.get("guest_migration_max_points", DEFAULT_ECONOMY_CONFIG["guest_migration_max_points"])
        ),
        bonus_racha=_normalizar_bonus_racha(doc.get("bonus_racha")),
        updated_at=str(doc.get("updated_at", "")),
    )


async def update_economy_config(req: EconomyConfigUpdateRequest) -> EconomyConfigResponse:
    """Actualiza la configuración económica desde la Torre de Control (Panel Administrador)."""
    db = get_database()
    update_fields: Dict[str, Any] = {}

    if req.vidas_iniciales is not None:
        update_fields["vidas_iniciales"] = max(1, req.vidas_iniciales)
    if req.costo_desbloqueo_dia_puntos is not None:
        update_fields["costo_desbloqueo_dia_puntos"] = max(0, req.costo_desbloqueo_dia_puntos)
    if req.costo_pista_puntos is not None:
        update_fields["costo_pista_puntos"] = max(0, req.costo_pista_puntos)
    if req.puntos_por_calificacion is not None:
        update_fields["puntos_por_calificacion"] = req.puntos_por_calificacion
    if req.escalas_tiempo_por_juego is not None:
        update_fields["escalas_tiempo_por_juego"] = {
            gid: [item.model_dump() for item in items]
            for gid, items in req.escalas_tiempo_por_juego.items()
        }
    if req.puntos_por_juego is not None:
        update_fields["puntos_por_juego"] = req.puntos_por_juego
    if req.guest_migration_max_points is not None:
        update_fields["guest_migration_max_points"] = max(0, req.guest_migration_max_points)
    if req.bonus_racha is not None:
        update_fields["bonus_racha"] = _ordenar_tramos_bonus(req.bonus_racha).model_dump()

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db[COLL_CONFIG].update_one(
        {"_id": "global_economy"}, {"$set": update_fields}, upsert=True
    )
    logger.info(f"[ECONOMIA] Configuración actualizada: {list(update_fields.keys())}")
    return await get_economy_config()
