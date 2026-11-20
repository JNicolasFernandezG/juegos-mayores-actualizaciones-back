"""
router.py
Controlador FastAPI de la Torre de Control y Administración (/api/narrative/admin).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Path, Query, UploadFile

from app.core.dependencies import get_current_admin
from app.features.narrative.admin.actions_router import actions_admin_router
from app.features.narrative.admin.challenge_service import generar_mes_narrativo, sembrar_finalizaciones_para_universo
from app.features.narrative.admin.crud_service import (
    crear_o_actualizar_carta, crear_o_actualizar_finalizacion, crear_o_actualizar_personaje,
    crear_o_actualizar_tag, crear_o_actualizar_universo, eliminar_carta, eliminar_finalizacion,
    eliminar_personaje, eliminar_tag, eliminar_universo, obtener_carta_por_id, obtener_cartas,
    obtener_finalizacion_por_id, obtener_finalizaciones, obtener_personaje_por_id, obtener_personajes,
    obtener_tag_por_id, obtener_tags, obtener_universo_por_id, obtener_universos,
)
from app.features.narrative.admin.image_service import procesar_y_guardar_imagen_narrativa
from app.features.narrative.admin.rules_catalog import obtener_catalogo_reglas_dict
from app.features.narrative.admin.v2_graphs_router import (
    _contar_grafos_v2, _eliminar_o_404, _obtener_o_404, _resolver_validador_v2,
    endpoint_ejecutar_seed_v2, endpoint_eliminar_conversacion_v2, endpoint_eliminar_evento_especial_v2,
    endpoint_eliminar_evento_v2, endpoint_estado_seed_v2, endpoint_guardar_conversacion_v2,
    endpoint_guardar_evento_especial_v2, endpoint_guardar_evento_v2, endpoint_listar_conversaciones_v2,
    endpoint_listar_eventos_especiales_v2, endpoint_listar_eventos_v2, endpoint_obtener_conversacion_v2,
    endpoint_obtener_evento_especial_v2, endpoint_obtener_evento_v2, endpoint_validar_grafos_v2,
    v2_graphs_router,
)
from app.features.narrative.schemas import (
    CartaCreateRequest, CartaResponse, FinalizacionCreateRequest, FinalizacionResponse,
    PersonajeCreateRequest, PersonajeResponse, TagCreateRequest, TagResponse,
    TagUpdateRequest, UniversoCreateRequest, UniversoResponse,
)

router = APIRouter(prefix="/api/narrative/admin", dependencies=[Depends(get_current_admin)])


@router.get("/catalogo-reglas", summary="Obtener el catálogo formal de disparadores, operadores y acciones", tags=["Narrativo - Administración"])
async def endpoint_obtener_catalogo_reglas():
    """Retorna el catálogo canónico de disparadores, operadores y acciones para desplegables de UI."""
    return obtener_catalogo_reglas_dict()


@router.post("/upload-imagen", summary="Subir y optimizar imagen a WebP para cualquier categoría del juego narrativo", tags=["Narrativo - Administración"])
async def endpoint_subir_imagen_narrativa(
    file: UploadFile = File(...),
    categoria: str = Query(..., description="Categoría (universos, personajes, cartas, eventos, resultados, conversaciones, finalizaciones)"),
):
    """Procesa una imagen JPG/PNG, la redimensiona proporcionalmente y la comprime a WebP."""
    return await procesar_y_guardar_imagen_narrativa(file=file, categoria=categoria)


@router.get("/universos", response_model=List[UniversoResponse], summary="Listar todos los universos", tags=["Narrativo - CRUD Universos"])
async def endpoint_listar_universos():
    return await obtener_universos()


@router.get("/universos/{universo_id}", response_model=UniversoResponse, summary="Obtener universo por ID", tags=["Narrativo - CRUD Universos"])
async def endpoint_obtener_universo(universo_id: str = Path(...)):
    return await _obtener_o_404(obtener_universo_por_id, universo_id, "Universo no encontrado.")


@router.post("/universos", response_model=UniversoResponse, summary="Crear o actualizar un universo", tags=["Narrativo - CRUD Universos"])
async def endpoint_guardar_universo(req: UniversoCreateRequest):
    return await crear_o_actualizar_universo(req)


@router.delete("/universos/{universo_id}", summary="Eliminar un universo", tags=["Narrativo - CRUD Universos"])
async def endpoint_eliminar_universo(universo_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_universo, universo_id, "Universo no encontrado.", "Universo eliminado correctamente.")


@router.get("/personajes", response_model=List[PersonajeResponse], summary="Listar personajes", tags=["Narrativo - CRUD Personajes"])
async def endpoint_listar_personajes(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Paginación offset"),
):
    return await obtener_personajes(universo_id=universo_id, limit=limit, skip=skip)


@router.get("/personajes/{personaje_id}", response_model=PersonajeResponse, summary="Obtener personaje por ID", tags=["Narrativo - CRUD Personajes"])
async def endpoint_obtener_personaje(personaje_id: str = Path(...)):
    return await _obtener_o_404(obtener_personaje_por_id, personaje_id, "Personaje no encontrado.")


@router.post("/personajes", response_model=PersonajeResponse, summary="Crear o actualizar personaje", tags=["Narrativo - CRUD Personajes"])
async def endpoint_guardar_personaje(req: PersonajeCreateRequest):
    return await crear_o_actualizar_personaje(req)


@router.delete("/personajes/{personaje_id}", summary="Eliminar personaje", tags=["Narrativo - CRUD Personajes"])
async def endpoint_eliminar_personaje(personaje_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_personaje, personaje_id, "Personaje no encontrado.", "Personaje eliminado correctamente.")


@router.get("/cartas", response_model=List[CartaResponse], summary="Listar cartas", tags=["Narrativo - CRUD Cartas"])
async def endpoint_listar_cartas(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Paginación offset"),
):
    return await obtener_cartas(universo_id=universo_id, limit=limit, skip=skip)


@router.get("/cartas/{carta_id}", response_model=CartaResponse, summary="Obtener carta por ID", tags=["Narrativo - CRUD Cartas"])
async def endpoint_obtener_carta(carta_id: str = Path(...)):
    return await _obtener_o_404(obtener_carta_por_id, carta_id, "Carta no encontrada.")


@router.post("/cartas", response_model=CartaResponse, summary="Crear o actualizar carta", tags=["Narrativo - CRUD Cartas"])
async def endpoint_guardar_carta(req: CartaCreateRequest):
    return await crear_o_actualizar_carta(req)


@router.delete("/cartas/{carta_id}", summary="Eliminar carta", tags=["Narrativo - CRUD Cartas"])
async def endpoint_eliminar_carta(carta_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_carta, carta_id, "Carta no encontrada.", "Carta eliminada correctamente.")


@router.get("/finalizaciones", response_model=List[FinalizacionResponse], summary="Listar finalizaciones", tags=["Narrativo - CRUD Finalizaciones"])
async def endpoint_listar_finalizaciones(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Paginación offset"),
):
    return await obtener_finalizaciones(universo_id=universo_id, limit=limit, skip=skip)


@router.get("/finalizaciones/{finalizacion_id}", response_model=FinalizacionResponse, summary="Obtener finalización por ID", tags=["Narrativo - CRUD Finalizaciones"])
async def endpoint_obtener_finalizacion(finalizacion_id: str = Path(...)):
    return await _obtener_o_404(obtener_finalizacion_por_id, finalizacion_id, "Finalización no encontrada.")


@router.post("/finalizaciones", response_model=FinalizacionResponse, summary="Crear o actualizar finalización", tags=["Narrativo - CRUD Finalizaciones"])
async def endpoint_guardar_finalizacion(req: FinalizacionCreateRequest):
    return await crear_o_actualizar_finalizacion(req)


@router.delete("/finalizaciones/{finalizacion_id}", summary="Eliminar finalización", tags=["Narrativo - CRUD Finalizaciones"])
async def endpoint_eliminar_finalizacion(finalizacion_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_finalizacion, finalizacion_id, "Finalización no encontrada.", "Finalización eliminada correctamente.")


@router.post("/universos/{universo_id}/sembrar-finalizaciones", response_model=List[FinalizacionResponse], summary="Sembrar automáticamente las finalizaciones de derrota base (<= 0) para cada recurso del universo", tags=["Narrativo - CRUD Finalizaciones"])
async def endpoint_sembrar_finalizaciones_universo(universo_id: str = Path(...)):
    return await sembrar_finalizaciones_para_universo(universo_id)


@router.post("/generar-mes", summary="Generar masivamente los 28-31 desafíos diarios del mes para el juego narrativo", tags=["Narrativo - Administración"])
async def endpoint_generar_mes_narrativo(
    year: int = Query(..., description="Año (ej: 2026)"),
    month: int = Query(..., ge=1, le=12, description="Mes (1 a 12)"),
    universo_id: str = Query(..., description="ID del universo (ej: corte_medieval)"),
):
    return await generar_mes_narrativo(year=year, month=month, universo_id=universo_id)


router.include_router(v2_graphs_router)


@router.get("/tags", response_model=List[TagResponse], summary="Listar tags narrativos del catálogo", tags=["Narrativo - CRUD Tags"])
async def endpoint_listar_tags(
    universo_id: Optional[str] = Query(None, description="Filtrar por universo"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    skip: int = Query(0, description="Offset de paginación"),
):
    return await obtener_tags(universo_id=universo_id, limit=limit, skip=skip)


@router.get("/tags/{tag_id}", response_model=TagResponse, summary="Obtener tag por ID (slug)", tags=["Narrativo - CRUD Tags"])
async def endpoint_obtener_tag(tag_id: str = Path(...)):
    return await _obtener_o_404(obtener_tag_por_id, tag_id, f"Tag '{tag_id}' no encontrado.")


@router.post("/tags", response_model=TagResponse, summary="Crear o actualizar tag narrativo", tags=["Narrativo - CRUD Tags"])
async def endpoint_guardar_tag(req: TagCreateRequest):
    return await crear_o_actualizar_tag(req)


@router.put("/tags/{tag_id}", response_model=TagResponse, summary="Actualizar tag existente", tags=["Narrativo - CRUD Tags"])
async def endpoint_actualizar_tag(tag_id: str = Path(...), req: TagUpdateRequest = ...):
    actual = await _obtener_o_404(obtener_tag_por_id, tag_id, f"Tag '{tag_id}' no encontrado.")
    data_dict = actual.model_dump(by_alias=True)
    data_dict.update(req.model_dump(exclude_unset=True))
    return await crear_o_actualizar_tag(TagCreateRequest(**data_dict))


@router.delete("/tags/{tag_id}", summary="Eliminar tag del catálogo", tags=["Narrativo - CRUD Tags"])
async def endpoint_eliminar_tag(tag_id: str = Path(...)):
    return await _eliminar_o_404(eliminar_tag, tag_id, "Tag no encontrado.", "Tag eliminado correctamente.")


router.include_router(actions_admin_router)
