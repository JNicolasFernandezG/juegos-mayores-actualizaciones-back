"""
node_resolver.py
Resolución de nodos terminales V2: cálculo de pesos de desenlaces, aplicación de impactos,
disparo de efectos reactivos, detección de cruces de afinidad y encadenamiento de diálogos.
"""

import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    AFINIDAD_UMBRAL_LEALTAD,
    AFINIDAD_UMBRAL_TRAICION,
    COLL_CARDS,
    COLL_CHARACTERS,
    COLL_V2_EVENTOS_ESPECIALES,
)
from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
from app.features.narrative.engine.rule_engine import (
    aplicar_delta_recurso,
    despachar_efectos,
    evaluar_condicion,
)
from app.features.narrative.engine.tag_state import personajes_activos, sincronizar_personajes
from app.features.narrative.enums import DisparadorEnum, RunPhaseEnum
from app.features.narrative.game import endings_service, universe_resources
from app.features.narrative.game.motor_v2.graph_sampler import sortear_conversacion_v2
from app.features.narrative.game.run_repository import persistir_run
from app.features.narrative.schemas.rules_schemas import EfectoSchema
from app.features.narrative.schemas.v2_graph_schemas import (
    DesenlaceNodoSchema,
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


def _detectar_cruces_afinidad(afinidad_before: Dict[str, Any], afinidad_after: Dict[str, Any]) -> List[tuple]:
    """Detecta cruces de umbral de afinidad ('lealtad' >= 95 o 'traicion' < 15)."""
    cruces: List[tuple] = []
    for pj_id, valor_actual in afinidad_after.items():
        valor_previo = afinidad_before.get(pj_id)
        if valor_previo is None:
            continue
        if valor_previo < AFINIDAD_UMBRAL_LEALTAD and valor_actual >= AFINIDAD_UMBRAL_LEALTAD:
            cruces.append((pj_id, "lealtad"))
        if valor_previo >= AFINIDAD_UMBRAL_TRAICION and valor_actual < AFINIDAD_UMBRAL_TRAICION:
            cruces.append((pj_id, "traicion"))
    return cruces


def _pesos_desenlaces(desenlaces: List[DesenlaceNodoSchema], run: Dict[str, Any]) -> List[float]:
    """Pesos efectivos del sorteo de desenlaces aplicando modificadores condicionales (suelo 0.0)."""
    pesos: List[float] = []
    for desenlace in desenlaces:
        peso = float(desenlace.peso)
        for mod in desenlace.modificadores_probabilidad:
            if evaluar_condicion(mod.condicion.model_dump(), run):
                peso += float(mod.delta_peso)
        pesos.append(max(0.0, peso))
    return pesos


def _senal_desenlace(nodo: NodoNarrativoSchema, net_delta_recursos: float) -> Optional[DisparadorEnum]:
    """Resuelve el signo percibido por cartas y corte al cerrarse un desenlace."""
    if nodo.tipo_desenlace is not None:
        signo = nodo.tipo_desenlace.value if hasattr(nodo.tipo_desenlace, "value") else str(nodo.tipo_desenlace)
    else:
        signo = "positivo" if net_delta_recursos > 0 else ("negativo" if net_delta_recursos < 0 else "neutro")
    if signo == "positivo":
        return DisparadorEnum.EN_EVENTO_POSITIVO
    if signo == "negativo":
        return DisparadorEnum.EN_EVENTO_NEGATIVO
    return None


async def _despachar_reactivos(
    run: Dict[str, Any],
    disparador: DisparadorEnum,
    recursos_mapa: Dict[str, Any],
    cat_acciones: Dict[str, Any],
    cat_frecuencias: Dict[str, Any],
    db,
) -> None:
    """Descarga cartas y corte en dos consultas y despacha sus efectos reactivos."""
    duenios: List[Tuple[str, List[Any]]] = []
    cartas_ids = run.get("cartas_en_mano", [])
    if cartas_ids:
        docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_ids}}, {"efectos": 1}).to_list(None)
        duenios.extend((str(d["_id"]), d.get("efectos") or []) for d in docs)

    corte_ids = list(run.get("afinidad", {}).keys())
    if corte_ids:
        docs = await db[COLL_CHARACTERS].find({"_id": {"$in": corte_ids}}, {"efectos": 1}).to_list(None)
        duenios.extend((str(d["_id"]), d.get("efectos") or []) for d in docs)

    for duenio_id, efectos in duenios:
        if efectos:
            despachar_efectos(
                disparador,
                run,
                [EfectoSchema(**e) for e in efectos],
                recursos_mapa,
                duenio_id=duenio_id,
                mes_actual=run.get("mes_actual", 1),
                catalogo_acciones=cat_acciones,
                catalogo_frecuencias=cat_frecuencias,
            )


async def _obtener_evento_especial(
    personaje_id: str, direccion: str, universo_id: str, *, db=None
) -> Optional[Dict[str, Any]]:
    """Recupera el grafo de evento especial para un personaje y dirección de umbral."""
    database = db if db is not None else get_database()
    return await database[COLL_V2_EVENTOS_ESPECIALES].find_one(
        {"universo_id": universo_id, "personaje_id": personaje_id, "direccion": direccion}
    )


async def _obtener_siguiente_especial_pendiente(run: Dict[str, Any], *, db=None) -> Optional[Dict[str, Any]]:
    """Desencola el próximo evento especial de afinidad pendiente y devuelve su grafo si existe."""
    pendientes = run.get("especiales_pendientes", [])
    universo_id = run.get("universo_id", "corte_medieval")
    while pendientes:
        item = pendientes.pop(0)
        grafo = await _obtener_evento_especial(item["personaje_id"], item["direccion"], universo_id, db=db)
        if grafo:
            return grafo
    return None


async def _aplicar_impactos_terminal(
    run: Dict[str, Any],
    siguiente_nodo: NodoNarrativoSchema,
    recursos_mapa: Dict[str, Any],
    cat_acciones: Dict[str, Any],
    cat_frecuencias: Dict[str, Any],
    db,
) -> List[tuple]:
    afinidad = run.setdefault("afinidad", {})
    for imp_rec in siguiente_nodo.impactos_recursos:
        aplicar_delta_recurso(run, imp_rec.recurso.lower(), float(imp_rec.delta), recursos_mapa)

    afinidad_before = dict(afinidad)
    for imp_af in siguiente_nodo.impactos_afinidad:
        if imp_af.personaje_id in afinidad:
            afinidad[imp_af.personaje_id] = max(0, min(100, afinidad[imp_af.personaje_id] + imp_af.delta))

    tags_activos = run.setdefault("tags_activos", [])
    for tag in siguiente_nodo.impactos_tags:
        if tag not in tags_activos:
            tags_activos.append(tag)

    if siguiente_nodo.efectos:
        despachar_efectos(
            DisparadorEnum.AL_DESENLACE,
            run,
            siguiente_nodo.efectos,
            recursos_mapa,
            mes_actual=run.get("mes_actual", 1),
            catalogo_acciones=cat_acciones,
            catalogo_frecuencias=cat_frecuencias,
        )

    disparador = _senal_desenlace(siguiente_nodo, sum(float(i.delta) for i in siguiente_nodo.impactos_recursos))
    if disparador:
        await _despachar_reactivos(run, disparador, recursos_mapa, cat_acciones, cat_frecuencias, db)

    await sincronizar_personajes(run, personajes_activos(run), db)
    return _detectar_cruces_afinidad(afinidad_before, afinidad)


def _registrar_cierre_nodo(
    run: Dict[str, Any], tipo: str, grafo_id: str, opcion_id: str, siguiente_nodo_id: str, siguiente_nodo: NodoNarrativoSchema
) -> None:
    claves = {"evento": "eventos_jugados", "conversacion": "conversaciones_jugadas", "evento_especial": "eventos_especiales_jugados"}
    if tipo in claves:
        run.setdefault(claves[tipo], []).append(grafo_id)

    turno = run.setdefault("turno_actual", {})
    turno["opcion_elegida_id"] = opcion_id
    turno["resultado_obtenido_id"] = siguiente_nodo_id
    run["grafo_activo"] = None
    run.setdefault("historial_grafos", []).append({
        "mes": run.get("mes_actual", 1),
        "tipo": tipo,
        "grafo_id": grafo_id,
        "opcion_elegida_id": opcion_id,
        "resultado_obtenido_id": siguiente_nodo_id,
        "resultado_texto": siguiente_nodo.resultado_texto,
    })


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


def _encolar_cruces(run: Dict[str, Any], cruces_afinidad: List[tuple]) -> None:
    if not cruces_afinidad:
        return
    pendientes = run.setdefault("especiales_pendientes", [])
    claves = {(p["personaje_id"], p["direccion"]) for p in pendientes}
    for pj_id, direccion in cruces_afinidad:
        if (pj_id, direccion) not in claves:
            pendientes.append({"personaje_id": pj_id, "direccion": direccion})
            claves.add((pj_id, direccion))


async def _encadenar_siguiente_grafo(
    run: Dict[str, Any],
    tipo: str,
    cruces_afinidad: List[tuple],
    db,
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

    nodo_raiz_id = next_grafo["nodo_raiz"]
    nodo_raiz_dict = obtener_nodos_dict(next_grafo).get(nodo_raiz_id)
    if not nodo_raiz_dict:
        raise HTTPException(status_code=500, detail=f"El grafo '{next_grafo['_id']}' no contiene su nodo raíz '{nodo_raiz_id}'.")

    nodo_cliente_next = NodoNarrativoSchema(**nodo_raiz_dict).to_cliente_schema(run)
    run["grafo_activo"] = {"tipo": next_tipo, "grafo_id": next_grafo["_id"], "nodo_actual_id": nodo_raiz_id}
    run["fase_actual"] = RunPhaseEnum.RESOLVER_CONVERSACION.value
    run.setdefault("turno_actual", {})["conversacion_actual_id"] = next_grafo["_id"]
    return _construir_conversacion_dto(next_grafo, nodo_raiz_id, nodo_cliente_next)


def _construir_estado_terminal(
    run: Dict[str, Any],
    grafo: Dict[str, Any],
    tipo: str,
    grafo_id: str,
    nodo_cliente: NodoClienteSchema,
    *,
    finalizacion: Optional[Dict[str, Any]] = None,
    puntos_ganados: Optional[int] = None,
    conversacion_dto: Optional[Dict[str, Any]] = None,
    default_status: str = "CONTINUA",
) -> EstadoGrafoV2Response:
    return EstadoGrafoV2Response(
        fase_actual=run["fase_actual"],
        grafo_id=grafo_id,
        tipo=tipo,
        titulo=grafo.get("titulo", ""),
        imagen=grafo.get("imagen", ""),
        nodo_actual=nodo_cliente,
        afinidad=run.get("afinidad", {}),
        recursos=run.get("recursos", {}),
        finalizacion=finalizacion,
        status=run.get("status", default_status),
        puntos_ganados=puntos_ganados,
        conversacion_actual=conversacion_dto,
    )


async def resolver_nodo_terminal(
    run: Dict[str, Any],
    grafo: Dict[str, Any],
    tipo: str,
    grafo_id: str,
    opcion_id: str,
    siguiente_nodo_id: str,
    siguiente_nodo: NodoNarrativoSchema,
    nodo_cliente: NodoClienteSchema,
    *,
    db=None,
    persistir_fn=None,
    sortear_conversacion_fn=None,
) -> EstadoGrafoV2Response:
    """Aplica impactos de un nodo final, evalúa colapso y encadena el siguiente grafo o balance."""
    database = db if db is not None else get_database()
    persistir = persistir_fn if persistir_fn is not None else persistir_run
    run.setdefault("recursos", {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50})
    run.setdefault("afinidad", {})

    universo_id = run.get("universo_id", "corte_medieval")
    recursos_mapa = await universe_resources.obtener_mapa_recursos_universo(universo_id)
    cat_acciones, cat_frecuencias = await obtener_catalogos_universo(universo_id, database)

    cruces_afinidad = await _aplicar_impactos_terminal(
        run, siguiente_nodo, recursos_mapa, cat_acciones, cat_frecuencias, database
    )
    _registrar_cierre_nodo(run, tipo, grafo_id, opcion_id, siguiente_nodo_id, siguiente_nodo)

    if await endings_service.verificar_colapso_recursos(run):
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        await persistir(run)
        puntos_ganados = await endings_service.sincronizar_intento_usuario(run)
        return _construir_estado_terminal(
            run, grafo, tipo, grafo_id, nodo_cliente,
            finalizacion=run.get("finalizacion"), puntos_ganados=puntos_ganados, default_status="game_over",
        )

    conversacion_dto = await _encadenar_siguiente_grafo(
        run, tipo, cruces_afinidad, database, sortear_conversacion_fn
    )
    run["updated_at"] = datetime.now(timezone.utc).isoformat()
    await persistir(run)
    return _construir_estado_terminal(
        run, grafo, tipo, grafo_id, nodo_cliente, conversacion_dto=conversacion_dto
    )
