"""
history_enricher.py
Enriquecimiento de la bitácora mensual de una partida narrativa (cartas, eventos,
conversaciones y decisiones V2) sin requerir consultas al router de administración.
"""

import asyncio
from typing import Any, Dict, Iterable, List, Optional

from app.features.narrative.constants import (
    COLL_CARDS, COLL_CONVERSATIONS, COLL_EVENTS, COLL_RESULTS,
    COLL_V2_CONVERSATIONS, COLL_V2_EVENTOS_ESPECIALES, COLL_V2_EVENTS,
)


async def _cargar_mapa_por_ids(
    db: Any, collections: List[str], ids: Iterable[Optional[str]],
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
    decisiones_v2: List[Dict[str, Any]], tipos: tuple[str, ...], grafo_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    for decision in reversed(decisiones_v2):
        if decision.get("tipo") in tipos and (not grafo_id or decision.get("grafo_id") == grafo_id):
            return decision
    return None


def _normalizar_impacto_afinidad(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"personaje_id": item["personaje_id"], "delta": int(item.get("delta", 0))}
        for item in items if isinstance(item, dict) and item.get("personaje_id")
    ]


def _enriquecer_grafo_v2_campos(
    mes: Dict[str, Any], nodos: Dict[str, Any], decision_v2: Optional[Dict[str, Any]],
    opcion_id: Optional[str], nodo_id: Optional[str], campo_opcion: str,
    campo_resultado: str, impactos_acumulados: List[Dict[str, Any]],
) -> None:
    mes[campo_opcion] = mes.get(campo_opcion) or _buscar_opcion_en_nodos(nodos, opcion_id)
    nodo_final = nodos.get(nodo_id) if nodo_id else None
    mes[campo_resultado] = (
        mes.get(campo_resultado) or (nodo_final or {}).get("resultado_texto") or (decision_v2 or {}).get("resultado_texto")
    )
    impactos_acumulados.extend((nodo_final or {}).get("impactos_afinidad") or [])


def _enriquecer_evento_mes(
    mes: Dict[str, Any], item: Dict[str, Any], evento_doc: Dict[str, Any],
    decisiones_v2: List[Dict[str, Any]], impactos_acumulados: List[Dict[str, Any]],
) -> None:
    evento_dec = _buscar_decision_v2(decisiones_v2, ("evento", "evento_especial"), item.get("evento_id"))
    mes["evento_titulo"] = mes.get("evento_titulo") or evento_doc.get("titulo")
    opcion_id = item.get("opcion_elegida_id") or (evento_dec or {}).get("opcion_elegida_id")
    if isinstance(evento_doc.get("nodos"), dict):
        nodo_id = (evento_dec or {}).get("resultado_obtenido_id") or item.get("resultado_id")
        _enriquecer_grafo_v2_campos(
            mes, evento_doc["nodos"], evento_dec, opcion_id, nodo_id,
            "opcion_texto", "resultado_texto", impactos_acumulados,
        )
        return
    for opcion in evento_doc.get("opciones") or []:
        if isinstance(opcion, dict) and opcion.get("id") == opcion_id:
            mes["opcion_texto"] = mes.get("opcion_texto") or opcion.get("texto")
            break


def _enriquecer_conversacion_mes(
    mes: Dict[str, Any], item: Dict[str, Any], conv_doc: Dict[str, Any],
    decisiones_v2: List[Dict[str, Any]], impactos_acumulados: List[Dict[str, Any]],
) -> None:
    conv_dec = _buscar_decision_v2(decisiones_v2, ("conversacion",), item.get("conversacion_id"))
    mes["conversacion_titulo"] = mes.get("conversacion_titulo") or conv_doc.get("titulo")
    if isinstance(conv_doc.get("nodos"), dict):
        conv_opcion = (conv_dec or {}).get("opcion_elegida_id") or item.get("decision_conversacion_opcion")
        opcion_str = str(conv_opcion) if conv_opcion is not None else None
        nodo_id = (conv_dec or {}).get("resultado_obtenido_id")
        _enriquecer_grafo_v2_campos(
            mes, conv_doc["nodos"], conv_dec, opcion_str, nodo_id,
            "decision_texto", "decision_resultado_texto", impactos_acumulados,
        )
        return
    conv_opcion = item.get("decision_conversacion_opcion")
    if conv_opcion is not None:
        for dec in conv_doc.get("decisiones") or []:
            if isinstance(dec, dict) and str(dec.get("opcion")) == str(conv_opcion):
                mes["decision_texto"] = mes.get("decision_texto") or dec.get("texto")
                mes["decision_resultado_texto"] = mes.get("decision_resultado_texto") or dec.get("resultado_texto")
                impactos_acumulados.extend(dec.get("impacto_afinidad") or [])
                break


def _enriquecer_mes_historial(
    item: Dict[str, Any], cartas_map: Dict[str, Dict[str, Any]],
    eventos_map: Dict[str, Dict[str, Any]], conversaciones_map: Dict[str, Dict[str, Any]],
    resultados_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    mes = dict(item)
    decisiones_v2 = [d for d in (item.get("decisiones_v2") or []) if isinstance(d, dict)]

    carta_doc = cartas_map.get(item.get("carta_elegida_id")) if item.get("carta_elegida_id") else None
    if carta_doc and not mes.get("carta_nombre"):
        mes["carta_nombre"] = carta_doc.get("nombre") or carta_doc.get("titulo")

    impactos_acumulados: List[Dict[str, Any]] = []
    evento_doc = eventos_map.get(item.get("evento_id")) if item.get("evento_id") else None
    if evento_doc:
        _enriquecer_evento_mes(mes, item, evento_doc, decisiones_v2, impactos_acumulados)

    resultado_doc = resultados_map.get(item.get("resultado_id")) if item.get("resultado_id") else None
    if resultado_doc:
        mes["resultado"] = mes.get("resultado") or resultado_doc.get("titulo")
        mes["resultado_texto"] = mes.get("resultado_texto") or resultado_doc.get("texto")
        impactos_acumulados.extend(resultado_doc.get("impacto_afinidad") or [])

    conv_doc = conversaciones_map.get(item.get("conversacion_id")) if item.get("conversacion_id") else None
    if conv_doc:
        _enriquecer_conversacion_mes(mes, item, conv_doc, decisiones_v2, impactos_acumulados)

    if not mes.get("impacto_afinidad") and impactos_acumulados:
        mes["impacto_afinidad"] = _normalizar_impacto_afinidad(impactos_acumulados)
    return mes


async def _enriquecer_historial_mensual(db: Any, historial_raw: List[Any]) -> List[Any]:
    registros = [item for item in historial_raw if isinstance(item, dict)]
    if not registros:
        return historial_raw

    cartas_map, eventos_map, conversaciones_map, resultados_map = await asyncio.gather(
        _cargar_mapa_por_ids(db, [COLL_CARDS], (r.get("carta_elegida_id") for r in registros)),
        _cargar_mapa_por_ids(db, [COLL_V2_EVENTS, COLL_V2_EVENTOS_ESPECIALES, COLL_EVENTS], (r.get("evento_id") for r in registros)),
        _cargar_mapa_por_ids(db, [COLL_V2_CONVERSATIONS, COLL_CONVERSATIONS], (r.get("conversacion_id") for r in registros)),
        _cargar_mapa_por_ids(db, [COLL_RESULTS], (r.get("resultado_id") for r in registros)),
    )
    return [
        _enriquecer_mes_historial(item, cartas_map, eventos_map, conversaciones_map, resultados_map)
        if isinstance(item, dict) else item
        for item in historial_raw
    ]
