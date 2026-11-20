"""
run_initializer.py
Validación de selección inicial de Fase 0, construcción del documento `narrative_runs`
y despacho de efectos `al_obtener` iniciales de corte y cartas.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHARACTERS,
    COLL_RUNS,
    COLL_RUNS_ARCHIVE,
    DIFICULTAD_FACIL_REDUCCION_DEFAULT,
)
from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
from app.features.narrative.engine.rule_engine import despachar_efectos_entidades_activas
from app.features.narrative.engine.tag_state import (
    personajes_activos,
    registrar_tags,
    sincronizar_personajes,
)
from app.features.narrative.enums import DisparadorEnum, RunPhaseEnum
from app.features.narrative.game.draft_sampling import nuevo_turno_actual
from app.features.narrative.game.identity import filtro_run, id_run, resolver_identidad
from app.features.narrative.schemas.game_schemas import IniciarPartidaRequest


def _reduccion_por_dificultad(dificultad: str, universo_doc: Optional[Dict[str, Any]]) -> int:
    """Amortiguación de pérdidas del modo fácil; 0 en normal. Se clampea para no invertir el signo."""
    if dificultad != "facil":
        return 0
    raw = (universo_doc or {}).get("dificultad_facil_reduccion", DIFICULTAD_FACIL_REDUCCION_DEFAULT)
    try:
        return max(0, min(90, int(raw)))
    except (TypeError, ValueError):
        return DIFICULTAD_FACIL_REDUCCION_DEFAULT


async def _proxima_generacion(user_id: int, date: str, db: Any = None) -> int:
    """La primera run es 1; tras archivar la activa, la siguiente continúa la secuencia."""
    database = db if db is not None else get_database()
    filtro = filtro_run(user_id, date)
    activa = await database[COLL_RUNS].find_one(filtro, {"generation": 1})
    if activa:
        return int(activa.get("generation") or 1)

    archivada = await database[COLL_RUNS_ARCHIVE].find_one(
        filtro, {"generation": 1}, sort=[("generation", -1)]
    )
    return int((archivada or {}).get("generation") or 0) + 1


def validar_seleccion_inicial(req: IniciarPartidaRequest, cfg: Dict[str, Any]) -> None:
    """Valida que la selección inicial de 3 personajes y 3 cartas pertenezca a la oferta."""
    if len(req.corte_elegida_ids) != 3:
        raise HTTPException(status_code=400, detail="Debes seleccionar exactamente 3 personajes para la corte.")
    if len(req.cartas_iniciales_ids) != 3:
        raise HTTPException(status_code=400, detail="Debes seleccionar exactamente 3 cartas de apoyo iniciales.")

    ofrecidos_corte = cfg.get("setup_corte_ofrecidos_ids", [])
    for pid in req.corte_elegida_ids:
        if pid not in ofrecidos_corte:
            raise HTTPException(status_code=400, detail=f"El personaje '{pid}' no estaba en la oferta inicial.")

    ofrecidas_cartas = cfg.get("setup_cartas_ofrecidas_ids", [])
    for cid in req.cartas_iniciales_ids:
        if cid not in ofrecidas_cartas:
            raise HTTPException(status_code=400, detail=f"La carta '{cid}' no estaba en la oferta inicial.")


def _armar_documento_run(
    user_id: int, req: IniciarPartidaRequest, cfg: Dict[str, Any], universo_doc: Optional[Dict[str, Any]],
    recursos_mapa: Dict[str, Dict[str, Any]], personajes_docs: List[Dict[str, Any]], generation: int,
) -> Dict[str, Any]:
    universo_id = cfg.get("universo_id")
    interno_id, guest_id = resolver_identidad(user_id)
    run: Dict[str, Any] = {
        "_id": id_run(user_id, req.date, generation), "user_id": interno_id, "date": req.date,
        "game_id": "narrativo", "generation": generation, "universo_id": universo_id,
        "motor": universo_doc.get("motor", "v2") if universo_doc else "v2",
        "dificultad": req.dificultad,
        "dificultad_reduccion": _reduccion_por_dificultad(req.dificultad, universo_doc),
        "mes_actual": 1, "fase_actual": RunPhaseEnum.DRAFT_MENSUAL.value, "status": "in_progress",
        "recursos": dict(cfg.get("atributos_iniciales", {})),
        "afinidad": {p["_id"]: p.get("afinidad_inicial", 50) for p in personajes_docs},
        "cartas_en_mano": req.cartas_iniciales_ids, "tags_activos": [], "tags_origen": {},
        "turno_actual": nuevo_turno_actual([]), "eventos_jugados": [], "conversaciones_jugadas": [],
        "historial_mensual": [], "updated_at": datetime.now(timezone.utc).isoformat(),
        "adquisiciones": {}, "modificadores_pasivos": [], "variables": {},
        "pool_eventos_disponibles_ids": list(cfg.get("pool_eventos_disponibles_ids", [])),
        "pool_conversaciones_ids": list(cfg.get("pool_conversaciones_ids", [])),
        "limites": {k: {"min": r.get("min", 0), "max": r.get("max", 100)} for k, r in recursos_mapa.items()},
    }
    if guest_id:
        run["guest_id"] = guest_id
    return run


async def construir_run_inicial(
    user_id: int, req: IniciarPartidaRequest, cfg: Dict[str, Any], universo_doc: Optional[Dict[str, Any]],
    recursos_mapa: Dict[str, Dict[str, Any]], db: Any,
) -> Dict[str, Any]:
    """Construye la run inicial y despacha los efectos `al_obtener` de corte y cartas."""
    personajes_docs = await db[COLL_CHARACTERS].find({"_id": {"$in": req.corte_elegida_ids}}).to_list(None)
    cartas_docs = await db[COLL_CARDS].find({"_id": {"$in": req.cartas_iniciales_ids}}).to_list(None)
    generation = await _proxima_generacion(user_id, req.date, db=db)
    run = _armar_documento_run(user_id, req, cfg, universo_doc, recursos_mapa, personajes_docs, generation)

    for tipo_entidad, docs in (("personaje", personajes_docs), ("carta", cartas_docs)):
        for doc in docs:
            oid = str(doc["_id"])
            registrar_tags(run, oid, doc.get("tags") or [])
            run["adquisiciones"][oid] = {"mes": 1, "tipo": tipo_entidad}

    cat_acciones, cat_frecuencias = await obtener_catalogos_universo(cfg.get("universo_id"), db)
    despachar_efectos_entidades_activas(
        DisparadorEnum.AL_OBTENER, run, [*personajes_docs, *cartas_docs], recursos_mapa,
        mes_actual=1, catalogo_acciones=cat_acciones, catalogo_frecuencias=cat_frecuencias,
    )
    await sincronizar_personajes(run, personajes_activos(run), db)
    return run
