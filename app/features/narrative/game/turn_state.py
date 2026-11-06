"""Estado común del turno para recargas/F5: expone el motor V2 y el grafo activo."""

from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_RUNS,
)
from app.features.narrative.schemas.catalog_schemas import (
    CartaResponse,
    ResultadoResponse,
    FinalizacionResponse,
)
from app.features.narrative.schemas.game_schemas import (
    EstadoTurnoResponse,
)
from app.features.narrative.game.motor_v2.v2_graph_service import proyectar_grafo_actual
from app.features.narrative.game.identity import filtro_run


async def obtener_turno_actual(user_id: int, date: str) -> EstadoTurnoResponse:
    """Retorna el estado reactivo del turno actual para sincronización de frontend o recarga F5."""
    db = get_database()
    run = await db[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail="Partida no encontrada.")

    turno = run.get("turno_actual", {})
    draft_ids = turno.get("cartas_ofrecidas_ids", [])

    draft_docs = await db[COLL_CARDS].find({"_id": {"$in": draft_ids}}).to_list(None) if draft_ids else []

    res_doc = None
    if run.get("historial_grafos"):
        ultimo_nodo = run["historial_grafos"][-1]
        if ultimo_nodo.get("mes") == run.get("mes_actual", 1):
            from app.features.narrative.game.motor_v2.graph_engine import graph_engine
            g_doc = await graph_engine.obtener_grafo(ultimo_nodo.get("tipo", "evento"), ultimo_nodo.get("grafo_id", ""))
            res_doc = {
                "_id": str(ultimo_nodo.get("resultado_obtenido_id") or "res_v2"),
                "universo_id": run.get("universo_id", "corte_medieval"),
                "titulo": (g_doc or {}).get("titulo", "Desenlace"),
                "texto": str(ultimo_nodo.get("resultado_texto") or ""),
                "tipo_resultado": "neutro",
                "imagen": (g_doc or {}).get("imagen", ""),
                "efectos": []
            }

    return EstadoTurnoResponse(
        date=date,
        mes_actual=run.get("mes_actual", 1),
        fase_actual=run.get("fase_actual", ""),
        status=run.get("status", "in_progress"),
        recursos=run.get("recursos", {}),
        afinidad=run.get("afinidad", {}),
        cartas_draft_actual=[CartaResponse(**c) for c in draft_docs],
        evento_actual=None,
        resultado_actual=ResultadoResponse(**res_doc) if res_doc else None,
        conversacion_actual=None,
        finalizacion=FinalizacionResponse(**run["finalizacion"]) if run.get("finalizacion") else None,
        grafo_actual=await proyectar_grafo_actual(run),
        motor=run.get("motor", "v2"),
    )
