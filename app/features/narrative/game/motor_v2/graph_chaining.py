"""
graph_chaining.py
Normalización de nodos, activación de raíz, construcción de DTO de estado V2 y
encadenamiento de eventos especiales de afinidad o conversaciones incidentales.
"""

import random
from typing import Any, Callable, Dict, List, Optional
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import COLL_V2_EVENTOS_ESPECIALES
from app.features.narrative.enums import RunPhaseEnum
from app.features.narrative.game.motor_v2.graph_sampler import sortear_conversacion_v2
from app.features.narrative.schemas.v2_graph_schemas import (
    EstadoGrafoV2Response,
    NodoClienteSchema,
    NodoNarrativoSchema,
)


def obtener_nodos_dict(grafo: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza los nodos del grafo asegurando formato diccionario indexado por ID."""
    nodos_raw = grafo.get("nodos", {})
    if isinstance(nodos_raw, list):
        return {n["id"]: n for n in nodos_raw if isinstance(n, dict) and "id" in n}
    return nodos_raw if isinstance(nodos_raw, dict) else {}


def activar_raiz_grafo(
    run: Dict[str, Any], grafo: Dict[str, Any], tipo: str, fase: str
) -> NodoClienteSchema:
    """Valida el nodo raíz, fija `grafo_activo` y `fase_actual` en memoria y devuelve su vista cliente."""
    grafo_id = grafo["_id"]
    nodo_raiz_id = grafo["nodo_raiz"]
    nodo_raiz_dict = obtener_nodos_dict(grafo).get(nodo_raiz_id)
    if not nodo_raiz_dict:
        raise HTTPException(
            status_code=500,
            detail=f"El grafo '{grafo_id}' no contiene su nodo raíz '{nodo_raiz_id}'.",
        )
    nodo_cliente = NodoNarrativoSchema(**nodo_raiz_dict).to_cliente_schema(run)
    run["grafo_activo"] = {"tipo": tipo, "grafo_id": grafo_id, "nodo_actual_id": nodo_raiz_id}
    run["fase_actual"] = fase
    return nodo_cliente


def construir_estado_grafo_v2(
    run: Dict[str, Any],
    grafo: Dict[str, Any],
    tipo: str,
    grafo_id: str,
    nodo_cliente: NodoClienteSchema,
    *,
    fase_actual: Optional[str] = None,
    afinidad: Optional[Dict[str, int]] = None,
    recursos: Optional[Dict[str, int]] = None,
    finalizacion: Optional[Dict[str, Any]] = None,
    puntos_ganados: Optional[int] = None,
    conversacion_dto: Optional[Dict[str, Any]] = None,
    default_status: str = "CONTINUA",
) -> EstadoGrafoV2Response:
    """Construye la respuesta estándar de estado de grafo V2 sin duplicar mapeos."""
    return EstadoGrafoV2Response(
        fase_actual=fase_actual if fase_actual is not None else run["fase_actual"],
        grafo_id=grafo_id,
        tipo=tipo,
        titulo=grafo.get("titulo", ""),
        imagen=grafo.get("imagen", ""),
        nodo_actual=nodo_cliente,
        afinidad=afinidad,
        recursos=recursos,
        finalizacion=finalizacion,
        status=run.get("status", default_status),
        puntos_ganados=puntos_ganados,
        conversacion_actual=conversacion_dto,
    )


async def _obtener_evento_especial(
    personaje_id: str, direccion: str, universo_id: str, *, db=None
) -> Optional[Dict[str, Any]]:
    """Recupera el grafo de evento especial para un personaje y dirección de umbral."""
    database = db if db is not None else get_database()
    return await database[COLL_V2_EVENTOS_ESPECIALES].find_one(
        {"universo_id": universo_id, "personaje_id": personaje_id, "direccion": direccion}
    )


async def _obtener_siguiente_especial_pendiente(
    run: Dict[str, Any], *, db=None
) -> Optional[Dict[str, Any]]:
    """Desencola el próximo evento especial de afinidad pendiente y devuelve su grafo si existe."""
    pendientes = run.get("especiales_pendientes", [])
    universo_id = run.get("universo_id", "corte_medieval")
    while pendientes:
        item = pendientes.pop(0)
        grafo = await _obtener_evento_especial(
            item["personaje_id"], item["direccion"], universo_id, db=db
        )
        if grafo:
            return grafo
    return None


def _encolar_cruces(run: Dict[str, Any], cruces_afinidad: List[tuple]) -> None:
    if not cruces_afinidad:
        return
    pendientes = run.setdefault("especiales_pendientes", [])
    claves = {(p["personaje_id"], p["direccion"]) for p in pendientes}
    for pj_id, direccion in cruces_afinidad:
        if (pj_id, direccion) not in claves:
            pendientes.append({"personaje_id": pj_id, "direccion": direccion})
            claves.add((pj_id, direccion))


def _construir_conversacion_dto(
    next_grafo: Dict[str, Any], nodo_raiz_id: str, nodo_cliente_next: NodoClienteSchema
) -> Dict[str, Any]:
    return {
        "_id": next_grafo["_id"],
        "nodo_id": nodo_raiz_id,
        "titulo": next_grafo.get("titulo", ""),
        "imagen": nodo_cliente_next.imagen or next_grafo.get("imagen", ""),
        "requisitos": [{"personajeId": nodo_cliente_next.hablante_id}],
        "frases": [{"personajeId": nodo_cliente_next.hablante_id, "texto": nodo_cliente_next.texto}],
        "decisiones": [
            {"opcion": opt.id, "texto": opt.texto, "resultado_texto": "", "impacto_afinidad": []}
            for opt in nodo_cliente_next.opciones
            if opt.disponible
        ],
    }


async def _encadenar_siguiente_grafo(
    run: Dict[str, Any],
    tipo: str,
    cruces_afinidad: List[tuple],
    db: Any,
    sortear_conversacion_fn: Optional[Callable[..., Any]],
) -> Optional[Dict[str, Any]]:
    _encolar_cruces(run, cruces_afinidad)
    next_grafo = await _obtener_siguiente_especial_pendiente(run, db=db)
    next_tipo = "evento_especial" if next_grafo else None

    if not next_grafo and tipo == "evento" and random.random() < 0.40:
        universo_id = run.get("universo_id", "corte_medieval")
        conv = (
            await sortear_conversacion_fn(run=run, pool_ids=None, universo_id=universo_id)
            if sortear_conversacion_fn is not None
            else await sortear_conversacion_v2(run=run, pool_ids=None, universo_id=universo_id, db=db)
        )
        if conv:
            next_grafo, next_tipo = conv, "conversacion"

    if not next_grafo:
        run["grafo_activo"] = None
        run["fase_actual"] = RunPhaseEnum.BALANCE_MES.value
        return None

    nodo_cliente_next = activar_raiz_grafo(
        run, next_grafo, next_tipo, RunPhaseEnum.RESOLVER_CONVERSACION.value
    )
    run.setdefault("turno_actual", {})["conversacion_actual_id"] = next_grafo["_id"]
    return _construir_conversacion_dto(next_grafo, next_grafo["nodo_raiz"], nodo_cliente_next)
