"""
v2_graphs_router.py
Subrouter FastAPI de administración para grafos V2 (eventos, conversaciones, eventos especiales),
siembra insert-only y validación estática de grafos.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.core.database import get_database
from app.features.narrative.admin.v2_crud_service import (
    crear_o_actualizar_conversacion_v2,
    crear_o_actualizar_evento_especial_v2,
    crear_o_actualizar_evento_v2,
    eliminar_conversacion_v2,
    eliminar_evento_especial_v2,
    eliminar_evento_v2,
    obtener_conversacion_v2_por_id,
    obtener_conversaciones_v2,
    obtener_evento_especial_v2_por_id,
    obtener_evento_v2_por_id,
    obtener_eventos_especiales_v2,
    obtener_eventos_v2,
)
from app.features.narrative.constants import (
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.schemas.v2_graph_schemas import (
    ConversacionV2GrafoSchema,
    EventoEspecialV2GrafoSchema,
    EventoV2GrafoSchema,
    ValidarGrafoV2Request,
    ValidarGrafoV2Response,
)
from app.features.narrative.validation import (
    TIPOS_VALIDOS,
    validar_grafo_para_guardado,
    validar_grafos_almacenados,
)

v2_graphs_router = APIRouter()


async def _obtener_o_404(getter: Callable[[str], Awaitable[Any]], item_id: str, detail: str) -> Any:
    item = await getter(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=detail)
    return item


async def _eliminar_o_404(
    deleter: Callable[[str], Awaitable[bool]], item_id: str, not_found: str, deleted_msg: str
) -> Dict[str, str]:
    if not await deleter(item_id):
        raise HTTPException(status_code=404, detail=not_found)
    return {"message": deleted_msg}


async def _contar_grafos_v2(db: Any) -> Dict[str, int]:
    return {
        "eventos": await db[COLL_V2_EVENTS].count_documents({}),
        "conversaciones": await db[COLL_V2_CONVERSATIONS].count_documents({}),
        "eventos_especiales": await db[COLL_V2_EVENTOS_ESPECIALES].count_documents({}),
    }


async def _resolver_validador_v2(req: ValidarGrafoV2Request) -> list:
    if req.tipo is not None and req.tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: '{req.tipo}'. Válidos: {list(TIPOS_VALIDOS)}.")

    if req.grafo is not None:
        if not req.tipo:
            raise HTTPException(status_code=400, detail="Para validar un grafo inline se requiere indicar 'tipo'.")
        return [await validar_grafo_para_guardado(req.grafo, req.tipo)]

    resultados = await validar_grafos_almacenados(
        tipos=[req.tipo] if req.tipo else None,
        grafo_id=req.grafo_id,
        universo_id=req.universo_id,
    )
    if req.grafo_id and not resultados:
        raise HTTPException(status_code=404, detail=f"Grafo '{req.grafo_id}' no encontrado.")
    return resultados


# --- Eventos V2 ---
@v2_graphs_router.get("/v2/eventos", response_model=List[EventoV2GrafoSchema], summary="Listar eventos de grafos V2", tags=["Narrativo - CRUD Eventos V2"])
async def endpoint_listar_eventos_v2(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Offset de paginación"),
):
    return await obtener_eventos_v2(universo_id=universo_id, limit=limit, skip=skip)


@v2_graphs_router.get("/v2/eventos/{evento_id}", response_model=EventoV2GrafoSchema, summary="Obtener evento V2 por ID", tags=["Narrativo - CRUD Eventos V2"])
async def endpoint_obtener_evento_v2(evento_id: str = Path(...)):
    return await _obtener_o_404(obtener_evento_v2_por_id, evento_id, "Evento V2 no encontrado.")


@v2_graphs_router.post("/v2/eventos", response_model=EventoV2GrafoSchema, summary="Crear o actualizar evento V2", tags=["Narrativo - CRUD Eventos V2"])
async def endpoint_guardar_evento_v2(req: EventoV2GrafoSchema):
    return await crear_o_actualizar_evento_v2(req)


@v2_graphs_router.delete("/v2/eventos/{evento_id}", summary="Eliminar evento V2", tags=["Narrativo - CRUD Eventos V2"])
async def endpoint_eliminar_evento_v2(evento_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_evento_v2, evento_id, "Evento V2 no encontrado.", "Evento V2 eliminado correctamente.")


# --- Conversaciones V2 ---
@v2_graphs_router.get("/v2/conversaciones", response_model=List[ConversacionV2GrafoSchema], summary="Listar conversaciones de grafos V2", tags=["Narrativo - CRUD Conversaciones V2"])
async def endpoint_listar_conversaciones_v2(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Offset de paginación"),
):
    return await obtener_conversaciones_v2(universo_id=universo_id, limit=limit, skip=skip)


@v2_graphs_router.get("/v2/conversaciones/{conversacion_id}", response_model=ConversacionV2GrafoSchema, summary="Obtener conversación V2 por ID", tags=["Narrativo - CRUD Conversaciones V2"])
async def endpoint_obtener_conversacion_v2(conversacion_id: str = Path(...)):
    return await _obtener_o_404(obtener_conversacion_v2_por_id, conversacion_id, "Conversación V2 no encontrada.")


@v2_graphs_router.post("/v2/conversaciones", response_model=ConversacionV2GrafoSchema, summary="Crear o actualizar conversación V2", tags=["Narrativo - CRUD Conversaciones V2"])
async def endpoint_guardar_conversacion_v2(req: ConversacionV2GrafoSchema):
    return await crear_o_actualizar_conversacion_v2(req)


@v2_graphs_router.delete("/v2/conversaciones/{conversacion_id}", summary="Eliminar conversación V2", tags=["Narrativo - CRUD Conversaciones V2"])
async def endpoint_eliminar_conversacion_v2(conversacion_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_conversacion_v2, conversacion_id, "Conversación V2 no encontrada.", "Conversación V2 eliminada correctamente.")


# --- Eventos Especiales V2 ---
@v2_graphs_router.get("/v2/eventos-especiales", response_model=List[EventoEspecialV2GrafoSchema], summary="Listar eventos especiales de afinidad (lealtad/traición)", tags=["Narrativo - CRUD Eventos Especiales V2"])
async def endpoint_listar_eventos_especiales_v2(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Offset de paginación"),
):
    return await obtener_eventos_especiales_v2(universo_id=universo_id, limit=limit, skip=skip)


@v2_graphs_router.get("/v2/eventos-especiales/{evento_id}", response_model=EventoEspecialV2GrafoSchema, summary="Obtener evento especial V2 por ID", tags=["Narrativo - CRUD Eventos Especiales V2"])
async def endpoint_obtener_evento_especial_v2(evento_id: str = Path(...)):
    return await _obtener_o_404(obtener_evento_especial_v2_por_id, evento_id, "Evento especial V2 no encontrado.")


@v2_graphs_router.post("/v2/eventos-especiales", response_model=EventoEspecialV2GrafoSchema, summary="Crear o actualizar evento especial V2", tags=["Narrativo - CRUD Eventos Especiales V2"])
async def endpoint_guardar_evento_especial_v2(req: EventoEspecialV2GrafoSchema):
    return await crear_o_actualizar_evento_especial_v2(req)


@v2_graphs_router.delete("/v2/eventos-especiales/{evento_id}", summary="Eliminar evento especial V2", tags=["Narrativo - CRUD Eventos Especiales V2"])
async def endpoint_eliminar_evento_especial_v2(evento_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_evento_especial_v2, evento_id, "Evento especial V2 no encontrado.", "Evento especial V2 eliminado correctamente.")


# --- Seed & Validación V2 ---
@v2_graphs_router.get("/v2/seed", summary="Estado del último intento de siembra de grafos V2", tags=["Narrativo - Administración"])
async def endpoint_estado_seed_v2(request: Request):
    """Reporta qué hizo el arranque y cuántos grafos hay hoy, sin exponer logs."""
    return {
        "arranque": getattr(request.app.state, "seed_v2_status", "sin_registro"),
        **await _contar_grafos_v2(get_database()),
    }


@v2_graphs_router.post("/v2/seed", summary="Ejecutar la siembra insert-only de grafos V2", tags=["Narrativo - Administración"])
async def endpoint_ejecutar_seed_v2():
    """Dispara el mismo seed del arranque y devuelve el resultado o el error real."""
    from app.scripts.seed_narrative_v2_graphs import seed_v2_graphs

    try:
        await seed_v2_graphs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Seed V2 falló: {type(exc).__name__}: {exc}")

    return {"success": True, **await _contar_grafos_v2(get_database())}


@v2_graphs_router.post(
    "/v2/validar",
    response_model=ValidarGrafoV2Response,
    summary="Validar grafos V2 (estructura, catálogo y ejecutabilidad de los desenlaces)",
    tags=["Narrativo - Administración"],
)
async def endpoint_validar_grafos_v2(req: ValidarGrafoV2Request):
    """Valida un grafo inline, uno almacenado o todos los grafos de un universo."""
    resultados = await _resolver_validador_v2(req)
    return {
        "resultados": [r.as_dict() for r in resultados],
        "total": len(resultados),
        "invalidos": sum(1 for r in resultados if not r.valido),
    }
