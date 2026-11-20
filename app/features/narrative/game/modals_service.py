"""
modals_service.py
Consultas de lectura para modales del jugador (bitácora, inventario, corte y epílogo).
"""

import logging

from app.core.database import get_database
from app.features.narrative.constants import COLL_CARDS, COLL_CHARACTERS
from app.features.narrative.engine.tag_state import personajes_activos
from app.features.narrative.game.history_enricher import (
    _buscar_decision_v2,
    _buscar_opcion_en_nodos,
    _cargar_mapa_por_ids,
    _enriquecer_historial_mensual,
    _enriquecer_mes_historial,
    _normalizar_impacto_afinidad,
)
from app.features.narrative.game.run_repository import obtener_run_activo_o_404
from app.features.narrative.schemas.catalog_schemas import (
    CartaResponse,
    FinalizacionResponse,
    PersonajeResponse,
)
from app.features.narrative.schemas.game_schemas import (
    CortePartidaResponse,
    FinalizacionPartidaResponse,
    HistorialPartidaResponse,
    InventarioPartidaResponse,
    PersonajeCorteDetalle,
)

logger = logging.getLogger(__name__)


async def obtener_historial_partida(user_id: int, date: str) -> HistorialPartidaResponse:
    """Consulta la bitácora mensual acumulada de los meses transcurridos en la partida."""
    db = get_database()
    run = await obtener_run_activo_o_404(user_id, date, db=db)
    historial_enriquecido = await _enriquecer_historial_mensual(db, run.get("historial_mensual", []))
    return HistorialPartidaResponse(
        date=date,
        mes_actual=run.get("mes_actual", 1),
        status=run.get("status", "in_progress"),
        fase_actual=run.get("fase_actual", ""),
        historial_mensual=historial_enriquecido,
    )


async def obtener_inventario_partida(user_id: int, date: str) -> InventarioPartidaResponse:
    """Consulta las cartas en mano y tags activos acumulados por el jugador."""
    db = get_database()
    run = await obtener_run_activo_o_404(user_id, date, db=db)
    cartas_ids = run.get("cartas_en_mano", [])
    docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_ids}}).to_list(None) if cartas_ids else []
    return InventarioPartidaResponse(
        date=date,
        cartas=[CartaResponse(**d) for d in docs],
        tags_activos=run.get("tags_activos", []),
    )


async def obtener_corte_partida(user_id: int, date: str) -> CortePartidaResponse:
    """Consulta los miembros activos de la corte y sus afinidades numéricas actuales."""
    db = get_database()
    run = await obtener_run_activo_o_404(user_id, date, db=db)
    afinidades = run.get("afinidad", {})
    corte_ids = personajes_activos(run)
    docs = await db[COLL_CHARACTERS].find({"_id": {"$in": corte_ids}}).to_list(None) if corte_ids else []
    corte_detalle = [
        PersonajeCorteDetalle(personaje=PersonajeResponse(**d), afinidad=afinidades.get(d["_id"], 50))
        for d in docs
    ]
    return CortePartidaResponse(date=date, corte=corte_detalle, afinidad=afinidades)


async def obtener_finalizacion_partida(user_id: int, date: str) -> FinalizacionPartidaResponse:
    """Consulta la tarjeta de finalización o derrota al término de la partida."""
    run = await obtener_run_activo_o_404(user_id, date, db=get_database())
    fin_doc = run.get("finalizacion")
    return FinalizacionPartidaResponse(
        date=date,
        status=run.get("status", "in_progress"),
        mes_actual=run.get("mes_actual", 1),
        finalizacion=FinalizacionResponse(**fin_doc) if fin_doc else None,
        epilogo_final=fin_doc,
    )


__all__ = [
    "_cargar_mapa_por_ids",
    "_buscar_opcion_en_nodos",
    "_buscar_decision_v2",
    "_normalizar_impacto_afinidad",
    "_enriquecer_mes_historial",
    "_enriquecer_historial_mensual",
    "obtener_historial_partida",
    "obtener_inventario_partida",
    "obtener_corte_partida",
    "obtener_finalizacion_partida",
]
