"""
setup_service.py
Fase 0 del motor narrativo V2:
- Oferta diaria de personajes y cartas para la selección inicial.
- Creación de la partida (motor V2 de grafos).
- Reinicio de la partida del día.
"""

import logging
from typing import Any, Dict
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CARDS, COLL_CHALLENGES, COLL_CHARACTERS, COLL_RUNS, COLL_SETTINGS,
)
from app.features.narrative.engine.rule_engine import evaluar_condiciones
from app.features.narrative.game.draft_sampling import preparar_draft_mensual, sortear_cartas_draft
from app.features.narrative.game.endings_service import sincronizar_intento_usuario, verificar_colapso_recursos
from app.features.narrative.game.event_cycle import cargar_eventos_del_dia_setup
from app.features.narrative.game.identity import filtro_run
from app.features.narrative.game.run_initializer import (
    _proxima_generacion, _reduccion_por_dificultad, construir_run_inicial, validar_seleccion_inicial,
)
from app.features.narrative.game.run_repository import RunAlreadyExistsError, archivar_run, crear_run
from app.features.narrative.game.universe_resources import obtener_mapa_recursos_universo
from app.features.narrative.schemas.catalog_schemas import CartaResponse, FinalizacionResponse, PersonajeResponse
from app.features.narrative.schemas.game_schemas import (
    EventoMuestraSetupResponse, IniciarPartidaRequest, IniciarPartidaV2Response, SetupDesafioResponse,
)

logger = logging.getLogger(__name__)


def _respuesta_inicio(
    run: Dict[str, Any],
    cartas_draft_actual: list,
    puntos_ganados: int | None = None,
) -> IniciarPartidaV2Response:
    fin_resp = FinalizacionResponse(**run["finalizacion"]) if run.get("finalizacion") else None
    return IniciarPartidaV2Response(
        mes_actual=run["mes_actual"],
        fase_actual=run["fase_actual"],
        recursos=run["recursos"],
        afinidad=run["afinidad"],
        cartas_draft_actual=cartas_draft_actual,
        finalizacion=fin_resp,
        motor=run.get("motor", "v2"),
        puntos_ganados=puntos_ganados,
    )


async def obtener_setup_desafio(user_id: int, date: str) -> SetupDesafioResponse:
    """Retorna los 5 personajes y 5 cartas ofrecidas para la selección inicial (Fase 0)."""
    db = get_database()
    challenge = await db[COLL_CHALLENGES].find_one({"game_id": "narrativo", "date": date})
    if not challenge:
        raise HTTPException(status_code=404, detail=f"No se ha configurado el desafío narrativo para la fecha {date}.")

    cfg = challenge.get("config", {})
    universo_id = cfg.get("universo_id")
    universo_doc = await db[COLL_SETTINGS].find_one({"_id": universo_id})
    if not universo_doc:
        raise HTTPException(status_code=404, detail=f"El universo '{universo_id}' no existe.")

    p_ids = cfg.get("setup_corte_ofrecidos_ids", [])
    personajes_docs = await db[COLL_CHARACTERS].find({"_id": {"$in": p_ids}}).to_list(length=10)
    c_ids = cfg.get("setup_cartas_ofrecidas_ids", [])
    cartas_docs = await db[COLL_CARDS].find({"_id": {"$in": c_ids}}).to_list(length=10)

    run_activa = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    estado_eval = run_activa or {
        "recursos": cfg.get("atributos_iniciales", {}),
        "afinidad": {},
        "corte_activa": [],
        "tags_activos": [],
        "cartas_en_mano": [],
    }

    p_elegibles = [p for p in personajes_docs if evaluar_condiciones(p.get("condiciones_aparicion", []), estado_eval)]
    if len(p_elegibles) >= 3:
        personajes_docs = p_elegibles

    c_elegibles = [c for c in cartas_docs if evaluar_condiciones(c.get("condiciones_aparicion", []), estado_eval)]
    if len(c_elegibles) >= 3:
        cartas_docs = c_elegibles

    # Con run activa, el mazo anunciado es el que la partida va a sortear, no el del
    # challenge (que puede haberse regenerado después). Run sin pool = universo completo.
    pool_run = (run_activa.get("pool_eventos_disponibles_ids") or []) if run_activa else None
    eventos_dia = await cargar_eventos_del_dia_setup(db, cfg, universo_doc, pool_ids=pool_run)

    return SetupDesafioResponse(
        date=date,
        universo_id=universo_id,
        universo_nombre=universo_doc.get("nombre", universo_id),
        universo_descripcion=universo_doc.get("descripcion", ""),
        atributos_iniciales=cfg.get("atributos_iniciales", {}),
        personajes_ofrecidos=[PersonajeResponse(**p) for p in personajes_docs],
        cartas_ofrecidas=[CartaResponse(**c) for c in cartas_docs],
        eventos_del_dia=[EventoMuestraSetupResponse(**e) for e in eventos_dia],
        tiene_partida_activa=bool(run_activa),
        fase_partida_activa=run_activa.get("fase_actual") if run_activa else None,
    )


async def iniciar_partida(user_id: int, req: IniciarPartidaRequest) -> IniciarPartidaV2Response:
    """
    Fase 0: Inicializa la partida con 3 miembros de corte y 3 cartas de apoyo.
    Retorna los recursos iniciales, las 3 cartas de draft del Mes 1 y el motor del universo.
    """
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, req.date))
    if not run:
        challenge = await db[COLL_CHALLENGES].find_one({"game_id": "narrativo", "date": req.date})
        if not challenge:
            raise HTTPException(status_code=404, detail=f"No existe desafío narrativo para la fecha {req.date}.")

        cfg = challenge.get("config", {})
        universo_id = cfg.get("universo_id")
        universo_doc = await db[COLL_SETTINGS].find_one({"_id": universo_id})
        validar_seleccion_inicial(req, cfg)

        recursos_mapa = await obtener_mapa_recursos_universo(universo_id)
        run = await construir_run_inicial(user_id, req, cfg, universo_doc, recursos_mapa, db)

        derrota = await verificar_colapso_recursos(run)
        if not derrota:
            pool_mensuales = cfg.get("pool_cartas_mensuales_ids", [])
            run["turno_actual"]["cartas_ofrecidas_ids"] = await preparar_draft_mensual(
                run, pool_mensuales, db, sortear_fn=sortear_cartas_draft
            )

        try:
            await crear_run(run)
        except RunAlreadyExistsError:
            run = await db[COLL_RUNS].find_one(filtro_run(user_id, req.date))
            if not run:
                raise HTTPException(
                    status_code=409,
                    detail="Otra petición creó la partida; recargá el estado antes de reintentar.",
                )
        else:
            if derrota:
                puntos_ganados = await sincronizar_intento_usuario(run)
                return _respuesta_inicio(run, [], puntos_ganados)

    draft_ids = run.get("turno_actual", {}).get("cartas_ofrecidas_ids", [])
    draft_docs = await db[COLL_CARDS].find({"_id": {"$in": draft_ids}}).to_list(None) if draft_ids else []
    return _respuesta_inicio(run, [CartaResponse(**c) for c in draft_docs])


async def reiniciar_partida(
    user_id: int,
    date: str,
    expected_version: int | None = None,
) -> Dict[str, Any]:
    """Archiva la generación activa y habilita una nueva sin borrar su evidencia."""
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        return {
            "success": False,
            "message": f"No hay una partida activa para reiniciar el {date}.",
            "eliminada": False,
            "previous_run_id": None,
            "next_generation": None,
        }

    generacion_anterior = int(run.get("generation") or 1)
    await archivar_run(run, expected_version)
    return {
        "success": True,
        "message": f"Partida del {date} reiniciada con una nueva generación.",
        "eliminada": True,
        "previous_run_id": run["_id"],
        "next_generation": generacion_anterior + 1,
    }


__all__ = [
    "_proxima_generacion",
    "_reduccion_por_dificultad",
    "iniciar_partida",
    "obtener_setup_desafio",
    "reiniciar_partida",
]
