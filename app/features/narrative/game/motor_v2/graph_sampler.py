"""
graph_sampler.py
Sorteo ponderado de grafos de eventos y conversaciones V2.
Filtra por universo, historial de jugados, requisitos previos y condiciones dinámicas,
aplicando sinergias con la corte, cartas en mano y recursos en crisis.
"""

import logging
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHARACTERS,
    COLL_SETTINGS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTS,
)
from app.features.narrative.engine.rule_engine import evaluar_condiciones
from app.features.narrative.engine.tag_state import personajes_activos

logger = logging.getLogger(__name__)


async def _cargar_tags_corte(db, corte_activa: Set[str]) -> Set[str]:
    tags: Set[str] = set()
    if not corte_activa:
        return tags
    pjs_docs = await db[COLL_CHARACTERS].find({"_id": {"$in": list(corte_activa)}}).to_list(None)
    for pj in pjs_docs:
        for tag in pj.get("tags", []):
            tags.add(tag.lower())
    return tags


async def _cargar_tags_cartas(db, cartas_mano: List[str]) -> Set[str]:
    tags: Set[str] = set()
    if not cartas_mano:
        return tags
    cartas_docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_mano}}).to_list(None)
    for carta in cartas_docs:
        for tag in carta.get("tags", []):
            tags.add(tag.lower())
    return tags


def _calcular_peso_evento(
    evt: Dict[str, Any],
    tags_corte: Set[str],
    tags_cartas: Set[str],
    recursos_en_crisis: Set[str],
) -> float:
    peso = float(evt.get("peso_base", 100.0))
    tags_evento = {t.lower() for t in evt.get("tags_tematicos", [])}
    if tags_corte.intersection(tags_evento):
        peso *= 2.0
    if tags_cartas.intersection(tags_evento):
        peso *= 2.5
    if recursos_en_crisis.intersection(tags_evento):
        peso *= 3.0
    return max(1.0, peso)


def _filtrar_eventos_elegibles(
    candidatos: List[Dict[str, Any]],
    eventos_previos: Set[str],
    corte_activa: Set[str],
    tags_corte: Set[str],
    tags_cartas: Set[str],
    recursos_en_crisis: Set[str],
    run: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[float]]:
    disponibles: List[Dict[str, Any]] = []
    pesos: List[float] = []
    for evt in candidatos:
        if evt.get("_id") in eventos_previos:
            continue
        req_previos = evt.get("requisitos_eventos_previos", [])
        if req_previos and not set(req_previos).issubset(eventos_previos):
            continue
        req_pjs = evt.get("requisitos_personajes", [])
        if req_pjs and not set(req_pjs).issubset(corte_activa):
            continue
        condiciones = evt.get("condiciones_disparo", [])
        if condiciones and not evaluar_condiciones(condiciones, run):
            continue
        disponibles.append(evt)
        pesos.append(_calcular_peso_evento(evt, tags_corte, tags_cartas, recursos_en_crisis))
    return disponibles, pesos


async def sortear_evento_v2(
    run: Dict[str, Any],
    pool_ids: Optional[List[str]] = None,
    universo_id: str = "corte_medieval",
    *,
    db=None,
) -> Optional[Dict[str, Any]]:
    """
    Sortea un evento V2 elegible respetando universo, pool, historial, arcos previos,
    personajes en corte, condiciones de disparo y ponderación por sinergias y crisis.
    """
    database = db if db is not None else get_database()
    query: Dict[str, Any] = {"universo_id": universo_id}
    if pool_ids:
        query["_id"] = {"$in": pool_ids}

    candidatos = await database[COLL_V2_EVENTS].find(query).to_list(None)
    if not candidatos and pool_ids:
        logger.warning(
            "Mazo de eventos sin coincidencias (universo=%s, %d ids); se usa el universo completo.",
            universo_id,
            len(pool_ids),
        )
        candidatos = await database[COLL_V2_EVENTS].find({"universo_id": universo_id}).to_list(None)
    if not candidatos:
        return None

    eventos_jugados = set(run.get("eventos_jugados", []))
    corte_activa = set(personajes_activos(run))
    tags_corte = await _cargar_tags_corte(database, corte_activa)
    tags_cartas = await _cargar_tags_cartas(database, run.get("cartas_en_mano", []))
    recursos_crisis = {k.lower() for k, v in run.get("recursos", {}).items() if float(v) < 25.0}

    disponibles, pesos = _filtrar_eventos_elegibles(
        candidatos, eventos_jugados, corte_activa, tags_corte, tags_cartas, recursos_crisis, run
    )
    if not disponibles and pool_ids:
        logger.warning(
            "Sin eventos elegibles dentro del mazo anunciado (universo=%s, %d ids); "
            "se sortea sobre el universo completo.",
            universo_id,
            len(pool_ids),
        )
        candidatos = await database[COLL_V2_EVENTS].find({"universo_id": universo_id}).to_list(None)
        disponibles, pesos = _filtrar_eventos_elegibles(
            candidatos, eventos_jugados, corte_activa, tags_corte, tags_cartas, recursos_crisis, run
        )

    if not disponibles and eventos_jugados:
        universo_doc = await database[COLL_SETTINGS].find_one({"_id": universo_id}, {"reciclaje_eventos_v2": 1})
        reciclar = bool(run.get("reciclaje_eventos_v2") or (universo_doc or {}).get("reciclaje_eventos_v2"))
        if reciclar:
            logger.info("Mazo agotado; reciclando historial de eventos V2 (universo=%s).", universo_id)
            # Reciclaje controlado: libera el historial al agotar elegibles para completar los 12 meses.
            run["eventos_jugados"] = []
            run["reciclajes_eventos_v2"] = int(run.get("reciclajes_eventos_v2", 0)) + 1
            disponibles, pesos = _filtrar_eventos_elegibles(
                candidatos, set(), corte_activa, tags_corte, tags_cartas, recursos_crisis, run
            )

    return random.choices(disponibles, weights=pesos, k=1)[0] if disponibles else None


async def sortear_conversacion_v2(
    run: Dict[str, Any],
    pool_ids: Optional[List[str]] = None,
    universo_id: str = "corte_medieval",
    *,
    db=None,
) -> Optional[Dict[str, Any]]:
    """
    Sortea una conversación V2 elegible respetando universo, pool, historial de jugadas,
    consejeros activos en corte y condiciones_disparo.
    """
    database = db if db is not None else get_database()
    query: Dict[str, Any] = {"universo_id": universo_id}
    if pool_ids:
        query["_id"] = {"$in": pool_ids}

    candidatas = await database[COLL_V2_CONVERSATIONS].find(query).to_list(None)
    if not candidatas and pool_ids:
        candidatas = await database[COLL_V2_CONVERSATIONS].find({"universo_id": universo_id}).to_list(None)
    if not candidatas:
        return None

    convs_jugadas = set(run.get("conversaciones_jugadas", []))
    corte_activa = set(personajes_activos(run))

    def _filtrar_convs(lista: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for conv in lista:
            if conv.get("_id") in convs_jugadas:
                continue
            if not set(conv.get("requisitos", [])).issubset(corte_activa):
                continue
            condiciones = conv.get("condiciones_disparo", [])
            if condiciones and not evaluar_condiciones(condiciones, run):
                continue
            out.append(conv)
        return out

    validas = _filtrar_convs(candidatas)
    if not validas and pool_ids:
        candidatas = await database[COLL_V2_CONVERSATIONS].find({"universo_id": universo_id}).to_list(None)
        validas = _filtrar_convs(candidatas)

    return random.choice(validas) if validas else None
