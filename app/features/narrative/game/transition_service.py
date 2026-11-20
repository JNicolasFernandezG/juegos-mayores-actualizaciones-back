"""
transition_service.py
Gestión de la Fase 4 (Balance y Transición Mensual): bitácora, victoria en Mes 12,
despacho de pasivos recurrentes `cada_mes`, verificación de colapso y nuevo draft.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHALLENGES,
    COLL_CHARACTERS,
    COLL_SETTINGS,
)
from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
from app.features.narrative.engine.rule_engine import despachar_efectos_entidades_activas
from app.features.narrative.engine.tag_state import personajes_activos, sincronizar_personajes
from app.features.narrative.enums import DisparadorEnum, RunPhaseEnum
from app.features.narrative.game.draft_sampling import (
    nuevo_turno_actual,
    preparar_draft_mensual,
    sortear_cartas_draft,
)
from app.features.narrative.game.endings_service import (
    calcular_finalizacion_victoria,
    sincronizar_intento_usuario,
    verificar_colapso_recursos,
)
from app.features.narrative.game.run_repository import obtener_run_activo_o_404, persistir_run
from app.features.narrative.game.universe_resources import obtener_mapa_recursos_universo
from app.features.narrative.schemas.catalog_schemas import CartaResponse, FinalizacionResponse
from app.features.narrative.schemas.game_schemas import AvanzarMesRequest, AvanzarMesV2Response

logger = logging.getLogger(__name__)


def _respuesta_cierre_mes(
    run: Dict[str, Any],
    cartas_draft_actual: List[CartaResponse],
    puntos_ganados: Optional[int] = None,
) -> AvanzarMesV2Response:
    fin_resp = FinalizacionResponse(**run["finalizacion"]) if run.get("finalizacion") else None
    return AvanzarMesV2Response(
        mes_actual=run.get("mes_actual", 1),
        fase_actual=run.get("fase_actual", ""),
        status=run.get("status", "in_progress"),
        recursos=run.get("recursos", {}),
        cartas_draft_actual=cartas_draft_actual,
        finalizacion=fin_resp,
        puntos_ganados=puntos_ganados,
    )


def _registrar_mes_en_historial(run: Dict[str, Any], turno: Dict[str, Any], mes_actual: int) -> None:
    decisiones_v2 = [
        dict(decision)
        for decision in run.get("historial_grafos", [])
        if decision.get("mes") == mes_actual
    ]
    run["historial_mensual"].append({
        "mes": mes_actual,
        "carta_elegida_id": turno.get("carta_elegida_id"),
        "evento_id": turno.get("evento_actual_id"),
        "opcion_elegida_id": turno.get("opcion_elegida_id"),
        "resultado_id": turno.get("resultado_obtenido_id"),
        "conversacion_id": turno.get("conversacion_actual_id"),
        "decision_conversacion_opcion": turno.get("decision_conversacion_opcion"),
        "decisiones_v2": decisiones_v2,
        "recursos_fin_mes": dict(run.get("recursos", {})),
    })
    evento_id = turno.get("evento_actual_id")
    if evento_id and evento_id not in run.get("eventos_jugados", []):
        run["eventos_jugados"].append(evento_id)


async def _aplicar_pasivos_mensuales(run: Dict[str, Any], db: Any, recursos_mapa: Dict[str, Any]) -> None:
    corte_ids = personajes_activos(run)
    personajes_docs = await db[COLL_CHARACTERS].find({"_id": {"$in": corte_ids}}).to_list(None)
    cartas_docs = await db[COLL_CARDS].find({"_id": {"$in": run["cartas_en_mano"]}}).to_list(None)
    cat_acciones, cat_frecuencias = await obtener_catalogos_universo(run["universo_id"], db)

    despachar_efectos_entidades_activas(
        DisparadorEnum.CADA_MES,
        run,
        [*personajes_docs, *cartas_docs],
        recursos_mapa,
        mes_actual=run["mes_actual"],
        catalogo_acciones=cat_acciones,
        catalogo_frecuencias=cat_frecuencias,
    )
    await sincronizar_personajes(run, personajes_activos(run), db)


async def avanzar_mes(user_id: int, req: AvanzarMesRequest) -> AvanzarMesV2Response:
    """
    Fase 4: Aplica efectos pasivos 'cada_mes' y avanza al siguiente mes.
    Retorna los recursos post-pasivos y las 3 nuevas cartas de draft (o epílogo si terminó).
    """
    db = get_database()
    run = await obtener_run_activo_o_404(user_id, req.date, db=db)

    fase_actual = run.get("fase_actual")
    if fase_actual in (RunPhaseEnum.DRAFT_MENSUAL.value, RunPhaseEnum.FINALIZADA.value):
        turno_previo = run.get("turno_actual", {})
        draft_ids = turno_previo.get("cartas_ofrecidas_ids", []) if fase_actual == RunPhaseEnum.DRAFT_MENSUAL.value else []
        draft_docs_previos = await db[COLL_CARDS].find({"_id": {"$in": draft_ids}}).to_list(None) if draft_ids else []
        return _respuesta_cierre_mes(run, [CartaResponse(**c) for c in draft_docs_previos])

    if fase_actual != RunPhaseEnum.BALANCE_MES.value:
        raise HTTPException(status_code=400, detail="La partida no se encuentra en fase de balance mensual.")

    turno = run.get("turno_actual", {})
    mes_actual = run.get("mes_actual", 1)
    _registrar_mes_en_historial(run, turno, mes_actual)

    if mes_actual >= 12:
        run["fase_actual"] = RunPhaseEnum.FINALIZADA.value
        run["status"] = "completed"
        universo_doc = await db[COLL_SETTINGS].find_one({"_id": run.get("universo_id")})
        run["finalizacion"] = calcular_finalizacion_victoria(run, universo_doc)
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        await persistir_run(run)
        return _respuesta_cierre_mes(run, [], await sincronizar_intento_usuario(run))

    run["mes_actual"] = mes_actual + 1
    run["fase_actual"] = RunPhaseEnum.DRAFT_MENSUAL.value
    recursos_mapa = await obtener_mapa_recursos_universo(run["universo_id"])
    await _aplicar_pasivos_mensuales(run, db, recursos_mapa)

    if await verificar_colapso_recursos(run):
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        await persistir_run(run)
        return _respuesta_cierre_mes(run, [], await sincronizar_intento_usuario(run))

    challenge = await db[COLL_CHALLENGES].find_one({"game_id": "narrativo", "date": req.date})
    pool_mensuales = challenge.get("config", {}).get("pool_cartas_mensuales_ids", [])
    cartas_sorteadas = await preparar_draft_mensual(run, pool_mensuales, db, sortear_fn=sortear_cartas_draft)
    run["turno_actual"] = nuevo_turno_actual(cartas_sorteadas)
    run["updated_at"] = datetime.now(timezone.utc).isoformat()
    await persistir_run(run)

    draft_docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_sorteadas}}).to_list(None)
    return _respuesta_cierre_mes(run, [CartaResponse(**c) for c in draft_docs])
