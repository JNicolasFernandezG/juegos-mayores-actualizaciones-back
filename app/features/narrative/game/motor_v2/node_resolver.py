"""
node_resolver.py
Resolución de nodos terminales V2: cálculo de pesos de desenlaces, aplicación de impactos,
disparo de efectos reactivos y detección de cruces de afinidad.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.database import get_database
from app.features.narrative.constants import (
    AFINIDAD_UMBRAL_LEALTAD,
    AFINIDAD_UMBRAL_TRAICION,
    COLL_CARDS,
    COLL_CHARACTERS,
)
from app.features.narrative.engine.action_executor import clampear_afinidad
from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
from app.features.narrative.engine.rule_engine import (
    aplicar_delta_recurso,
    despachar_efectos,
    despachar_efectos_entidades_activas,
    evaluar_condicion,
)
from app.features.narrative.engine.tag_state import personajes_activos, sincronizar_personajes
from app.features.narrative.enums import DisparadorEnum
from app.features.narrative.game import endings_service, universe_resources
from app.features.narrative.game.motor_v2.graph_chaining import (
    _construir_conversacion_dto,
    _encadenar_siguiente_grafo,
    _encolar_cruces,
    _obtener_evento_especial,
    _obtener_siguiente_especial_pendiente,
    construir_estado_grafo_v2,
    obtener_nodos_dict,
)
from app.features.narrative.game.run_repository import persistir_run
from app.features.narrative.schemas.v2_graph_schemas import (
    DesenlaceNodoSchema,
    EstadoGrafoV2Response,
    NodoClienteSchema,
    NodoNarrativoSchema,
)


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
    run: Dict[str, Any], disparador: DisparadorEnum, recursos_mapa: Dict[str, Any],
    cat_acciones: Dict[str, Any], cat_frecuencias: Dict[str, Any], db: Any,
) -> None:
    """Descarga cartas y corte y despacha sus efectos reactivos."""
    entidades: List[Dict[str, Any]] = []
    for col, ids in ((COLL_CARDS, run.get("cartas_en_mano", [])), (COLL_CHARACTERS, personajes_activos(run))):
        if ids:
            entidades.extend(await db[col].find({"_id": {"$in": ids}}, {"efectos": 1}).to_list(None))

    despachar_efectos_entidades_activas(
        disparador, run, entidades, recursos_mapa,
        mes_actual=run.get("mes_actual", 1), catalogo_acciones=cat_acciones, catalogo_frecuencias=cat_frecuencias,
    )


async def _aplicar_impactos_terminal(
    run: Dict[str, Any], siguiente_nodo: NodoNarrativoSchema, recursos_mapa: Dict[str, Any],
    cat_acciones: Dict[str, Any], cat_frecuencias: Dict[str, Any], db: Any,
) -> List[tuple]:
    afinidad = run.setdefault("afinidad", {})
    for imp_rec in siguiente_nodo.impactos_recursos:
        aplicar_delta_recurso(run, imp_rec.recurso.lower(), float(imp_rec.delta), recursos_mapa)

    afinidad_before = dict(afinidad)
    for imp_af in siguiente_nodo.impactos_afinidad:
        if imp_af.personaje_id in afinidad:
            afinidad[imp_af.personaje_id] = clampear_afinidad(afinidad[imp_af.personaje_id] + imp_af.delta)

    tags_activos = run.setdefault("tags_activos", [])
    for tag in siguiente_nodo.impactos_tags:
        if tag not in tags_activos:
            tags_activos.append(tag)

    if siguiente_nodo.efectos:
        despachar_efectos(
            DisparadorEnum.AL_DESENLACE, run, siguiente_nodo.efectos, recursos_mapa,
            mes_actual=run.get("mes_actual", 1), catalogo_acciones=cat_acciones, catalogo_frecuencias=cat_frecuencias,
        )

    disparador = _senal_desenlace(siguiente_nodo, sum(float(i.delta) for i in siguiente_nodo.impactos_recursos))
    if disparador:
        await _despachar_reactivos(run, disparador, recursos_mapa, cat_acciones, cat_frecuencias, db)

    await sincronizar_personajes(run, personajes_activos(run), db)
    return _detectar_cruces_afinidad(afinidad_before, afinidad)


def _registrar_cierre_nodo(
    run: Dict[str, Any], tipo: str, grafo_id: str, opcion_id: str,
    siguiente_nodo_id: str, siguiente_nodo: NodoNarrativoSchema,
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


def _construir_estado_terminal(
    run: Dict[str, Any], grafo: Dict[str, Any], tipo: str, grafo_id: str,
    nodo_cliente: NodoClienteSchema, **extra: Any,
) -> EstadoGrafoV2Response:
    return construir_estado_grafo_v2(
        run, grafo, tipo, grafo_id, nodo_cliente,
        afinidad=run.get("afinidad", {}), recursos=run.get("recursos", {}), **extra,
    )


async def resolver_nodo_terminal(
    run: Dict[str, Any], grafo: Dict[str, Any], tipo: str, grafo_id: str, opcion_id: str,
    siguiente_nodo_id: str, siguiente_nodo: NodoNarrativoSchema, nodo_cliente: NodoClienteSchema,
    *, db=None, persistir_fn=None, sortear_conversacion_fn=None,
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


__all__ = [
    "obtener_nodos_dict", "_detectar_cruces_afinidad", "_pesos_desenlaces",
    "_senal_desenlace", "_despachar_reactivos", "_obtener_evento_especial",
    "_obtener_siguiente_especial_pendiente", "_encolar_cruces",
    "_construir_conversacion_dto", "_encadenar_siguiente_grafo",
    "_construir_estado_terminal", "resolver_nodo_terminal",
]
