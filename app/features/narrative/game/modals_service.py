"""
modals_service.py
Consultas de lectura comunes a ambos motores:
- Modal de la bitácora mensual (historial enriquecido sin consultar /admin/*).
- Modal de inventario (cartas en mano y tags activos).
- Modal de corte activa (personajes asignados y afinidad).
- Modal de epílogo / finalización detallada.
"""

import asyncio
import logging
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CHARACTERS,
    COLL_CARDS,
    COLL_CONVERSATIONS,
    COLL_EVENTS,
    COLL_RESULTS,
    COLL_RUNS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.schemas.catalog_schemas import (
    PersonajeResponse,
    CartaResponse,
    FinalizacionResponse
)
from app.features.narrative.schemas.game_schemas import (
    HistorialPartidaResponse,
    InventarioPartidaResponse,
    PersonajeCorteDetalle,
    CortePartidaResponse,
    FinalizacionPartidaResponse,
)
from app.features.narrative.game.identity import filtro_run

logger = logging.getLogger(__name__)


async def _cargar_mapa_por_ids(
    db: Any,
    collections: List[str],
    ids: Iterable[Optional[str]],
) -> Dict[str, Dict[str, Any]]:
    pendientes = {doc_id for doc_id in ids if isinstance(doc_id, str) and doc_id}
    resultado: Dict[str, Dict[str, Any]] = {}
    for coll in collections:
        if not pendientes:
            break
        docs = await db[coll].find({"_id": {"$in": list(pendientes)}}).to_list(None)
        for doc in docs:
            doc_id = doc.get("_id")
            if doc_id:
                resultado[doc_id] = doc
                pendientes.discard(doc_id)
    return resultado


def _buscar_opcion_en_nodos(nodos: Any, opcion_id: Optional[str]) -> Optional[str]:
    if not isinstance(nodos, dict) or not opcion_id:
        return None
    for nodo in nodos.values():
        if not isinstance(nodo, dict):
            continue
        for opcion in nodo.get("opciones") or []:
            if isinstance(opcion, dict) and opcion.get("id") == opcion_id:
                return opcion.get("texto")
    return None


def _buscar_decision_v2(
    decisiones_v2: List[Dict[str, Any]],
    tipos: tuple[str, ...],
    grafo_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    for decision in reversed(decisiones_v2):
        if decision.get("tipo") in tipos and (not grafo_id or decision.get("grafo_id") == grafo_id):
            return decision
    return None


def _normalizar_impacto_afinidad(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    impactos: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("personaje_id"):
            impactos.append(
                {
                    "personaje_id": item["personaje_id"],
                    "delta": int(item.get("delta", 0)),
                }
            )
    return impactos


def _enriquecer_mes_historial(
    item: Dict[str, Any],
    cartas_map: Dict[str, Dict[str, Any]],
    eventos_map: Dict[str, Dict[str, Any]],
    conversaciones_map: Dict[str, Dict[str, Any]],
    resultados_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    mes = dict(item)
    decisiones_v2 = [d for d in (item.get("decisiones_v2") or []) if isinstance(d, dict)]

    carta_id = item.get("carta_elegida_id")
    carta_doc = cartas_map.get(carta_id) if carta_id else None
    if carta_doc and not mes.get("carta_nombre"):
        mes["carta_nombre"] = carta_doc.get("nombre") or carta_doc.get("titulo")

    impactos_acumulados: List[Dict[str, Any]] = []

    evento_id = item.get("evento_id")
    evento_doc = eventos_map.get(evento_id) if evento_id else None
    evento_dec = _buscar_decision_v2(decisiones_v2, ("evento", "evento_especial"), evento_id)
    if evento_doc:
        mes["evento_titulo"] = mes.get("evento_titulo") or evento_doc.get("titulo")
        opcion_id = item.get("opcion_elegida_id") or (evento_dec or {}).get("opcion_elegida_id")
        if isinstance(evento_doc.get("nodos"), dict):
            mes["opcion_texto"] = mes.get("opcion_texto") or _buscar_opcion_en_nodos(evento_doc["nodos"], opcion_id)
            nodo_id = (evento_dec or {}).get("resultado_obtenido_id") or item.get("resultado_id")
            nodo_final = evento_doc["nodos"].get(nodo_id) if nodo_id else None
            mes["resultado_texto"] = (
                mes.get("resultado_texto")
                or (nodo_final or {}).get("resultado_texto")
                or (evento_dec or {}).get("resultado_texto")
            )
            impactos_acumulados.extend((nodo_final or {}).get("impactos_afinidad") or [])
        else:
            for opcion in evento_doc.get("opciones") or []:
                if isinstance(opcion, dict) and opcion.get("id") == opcion_id:
                    mes["opcion_texto"] = mes.get("opcion_texto") or opcion.get("texto")
                    break

    resultado_id = item.get("resultado_id")
    resultado_doc = resultados_map.get(resultado_id) if resultado_id else None
    if resultado_doc:
        mes["resultado"] = mes.get("resultado") or resultado_doc.get("titulo")
        mes["resultado_texto"] = mes.get("resultado_texto") or resultado_doc.get("texto")
        impactos_acumulados.extend(resultado_doc.get("impacto_afinidad") or [])

    conversacion_id = item.get("conversacion_id")
    conv_doc = conversaciones_map.get(conversacion_id) if conversacion_id else None
    conv_dec = _buscar_decision_v2(decisiones_v2, ("conversacion",), conversacion_id)
    if conv_doc:
        mes["conversacion_titulo"] = mes.get("conversacion_titulo") or conv_doc.get("titulo")
        if isinstance(conv_doc.get("nodos"), dict):
            conv_opcion = (conv_dec or {}).get("opcion_elegida_id") or item.get("decision_conversacion_opcion")
            mes["decision_texto"] = mes.get("decision_texto") or _buscar_opcion_en_nodos(
                conv_doc["nodos"], str(conv_opcion) if conv_opcion is not None else None
            )
            conv_nodo_id = (conv_dec or {}).get("resultado_obtenido_id")
            conv_nodo = conv_doc["nodos"].get(conv_nodo_id) if conv_nodo_id else None
            mes["decision_resultado_texto"] = (
                mes.get("decision_resultado_texto")
                or (conv_nodo or {}).get("resultado_texto")
                or (conv_dec or {}).get("resultado_texto")
            )
            impactos_acumulados.extend((conv_nodo or {}).get("impactos_afinidad") or [])
        else:
            conv_opcion = item.get("decision_conversacion_opcion")
            if conv_opcion is not None:
                for decision in conv_doc.get("decisiones") or []:
                    if isinstance(decision, dict) and str(decision.get("opcion")) == str(conv_opcion):
                        mes["decision_texto"] = mes.get("decision_texto") or decision.get("texto")
                        mes["decision_resultado_texto"] = mes.get("decision_resultado_texto") or decision.get("resultado_texto")
                        impactos_acumulados.extend(decision.get("impacto_afinidad") or [])
                        break

    if not mes.get("impacto_afinidad") and impactos_acumulados:
        mes["impacto_afinidad"] = _normalizar_impacto_afinidad(impactos_acumulados)

    return mes


async def _enriquecer_historial_mensual(db: Any, historial_raw: List[Any]) -> List[Any]:
    registros = [item for item in historial_raw if isinstance(item, dict)]
    if not registros:
        return historial_raw

    cartas_map, eventos_map, conversaciones_map, resultados_map = await asyncio.gather(
        _cargar_mapa_por_ids(db, [COLL_CARDS], (item.get("carta_elegida_id") for item in registros)),
        _cargar_mapa_por_ids(
            db,
            [COLL_V2_EVENTS, COLL_V2_EVENTOS_ESPECIALES, COLL_EVENTS],
            (item.get("evento_id") for item in registros),
        ),
        _cargar_mapa_por_ids(
            db,
            [COLL_V2_CONVERSATIONS, COLL_CONVERSATIONS],
            (item.get("conversacion_id") for item in registros),
        ),
        _cargar_mapa_por_ids(db, [COLL_RESULTS], (item.get("resultado_id") for item in registros)),
    )

    return [
        _enriquecer_mes_historial(item, cartas_map, eventos_map, conversaciones_map, resultados_map)
        if isinstance(item, dict)
        else item
        for item in historial_raw
    ]


async def obtener_historial_partida(user_id: int, date: str) -> HistorialPartidaResponse:
    """Consulta la bitácora mensual acumulada de los meses transcurridos en la partida."""
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail="Partida no encontrada.")
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
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail="Partida no encontrada.")
    cartas_ids = run.get("cartas_en_mano", [])
    docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_ids}}).to_list(None) if cartas_ids else []
    return InventarioPartidaResponse(
        date=date,
        cartas=[CartaResponse(**d) for d in docs],
        tags_activos=run.get("tags_activos", [])
    )

async def obtener_corte_partida(user_id: int, date: str) -> CortePartidaResponse:
    """Consulta los miembros activos de la corte y sus afinidades numéricas actuales."""
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail="Partida no encontrada.")
    afinidades = run.get("afinidad", {})
    corte_ids = list(afinidades.keys()) or run.get("corte_activa", [])
    docs = await db[COLL_CHARACTERS].find({"_id": {"$in": corte_ids}}).to_list(None) if corte_ids else []
    corte_detalle = [
        PersonajeCorteDetalle(
            personaje=PersonajeResponse(**d),
            afinidad=afinidades.get(d["_id"], 50)
        )
        for d in docs
    ]
    return CortePartidaResponse(
        date=date,
        corte=corte_detalle,
        afinidad=afinidades
    )

async def obtener_finalizacion_partida(user_id: int, date: str) -> FinalizacionPartidaResponse:
    """Consulta la tarjeta de finalización o derrota al término de la partida."""
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail="Partida no encontrada.")
    fin_doc = run.get("finalizacion")
    fin_resp = FinalizacionResponse(**fin_doc) if fin_doc else None
    return FinalizacionPartidaResponse(
        date=date,
        status=run.get("status", "in_progress"),
        mes_actual=run.get("mes_actual", 1),
        finalizacion=fin_resp,
        epilogo_final=fin_doc
    )
