"""
v2_crud_service.py
Servicios CRUD para grafos V2 (eventos, conversaciones, eventos especiales) y catálogo de tags.
"""

from typing import List, Optional, Type, TypeVar
from fastapi import HTTPException
from pydantic import BaseModel

from app.features.narrative.admin.crud_base import (
    eliminar_item_catalogo_por_id,
    guardar_item_catalogo,
    listar_items_catalogo,
    obtener_item_catalogo_por_id,
)
from app.features.narrative.constants import (
    COLL_TAGS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.schemas.catalog_schemas import TagCreateRequest, TagResponse
from app.features.narrative.schemas.v2_graph_schemas import (
    ConversacionV2GrafoSchema,
    EventoEspecialV2GrafoSchema,
    EventoV2GrafoSchema,
)
from app.features.narrative.validation import validar_grafo_para_guardado

T = TypeVar("T", bound=BaseModel)


async def guardar_grafo_v2(
    collection_name: str,
    tipo: str,
    req: BaseModel,
    response_cls: Type[T],
) -> T:
    """Guarda un grafo V2 sólo si el motor puede ejecutar todo lo que declara."""
    resultado = await validar_grafo_para_guardado(req, tipo)
    if not resultado.valido:
        raise HTTPException(
            status_code=422,
            detail={
                "mensaje": f"El {tipo} declara contenido que el motor no puede ejecutar.",
                "errores": [h.as_dict() for h in resultado.errores],
            },
        )
    return await guardar_item_catalogo(collection_name, req.id, req, response_cls)


# Eventos V2
async def crear_o_actualizar_evento_v2(req: EventoV2GrafoSchema) -> EventoV2GrafoSchema:
    return await guardar_grafo_v2(COLL_V2_EVENTS, "evento", req, EventoV2GrafoSchema)


async def obtener_eventos_v2(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[EventoV2GrafoSchema]:
    return await listar_items_catalogo(COLL_V2_EVENTS, EventoV2GrafoSchema, universo_id, limit, skip)


async def obtener_evento_v2_por_id(evento_id: str) -> Optional[EventoV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(COLL_V2_EVENTS, evento_id, EventoV2GrafoSchema)


async def eliminar_evento_v2(evento_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_EVENTS, evento_id)


# Conversaciones V2
async def crear_o_actualizar_conversacion_v2(req: ConversacionV2GrafoSchema) -> ConversacionV2GrafoSchema:
    return await guardar_grafo_v2(COLL_V2_CONVERSATIONS, "conversacion", req, ConversacionV2GrafoSchema)


async def obtener_conversaciones_v2(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[ConversacionV2GrafoSchema]:
    return await listar_items_catalogo(COLL_V2_CONVERSATIONS, ConversacionV2GrafoSchema, universo_id, limit, skip)


async def obtener_conversacion_v2_por_id(conversacion_id: str) -> Optional[ConversacionV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(COLL_V2_CONVERSATIONS, conversacion_id, ConversacionV2GrafoSchema)


async def eliminar_conversacion_v2(conversacion_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_CONVERSATIONS, conversacion_id)


# Eventos Especiales V2
async def crear_o_actualizar_evento_especial_v2(
    req: EventoEspecialV2GrafoSchema,
) -> EventoEspecialV2GrafoSchema:
    return await guardar_grafo_v2(
        COLL_V2_EVENTOS_ESPECIALES, "evento_especial", req, EventoEspecialV2GrafoSchema
    )


async def obtener_eventos_especiales_v2(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[EventoEspecialV2GrafoSchema]:
    return await listar_items_catalogo(
        COLL_V2_EVENTOS_ESPECIALES, EventoEspecialV2GrafoSchema, universo_id, limit, skip
    )


async def obtener_evento_especial_v2_por_id(evento_id: str) -> Optional[EventoEspecialV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(
        COLL_V2_EVENTOS_ESPECIALES, evento_id, EventoEspecialV2GrafoSchema
    )


async def eliminar_evento_especial_v2(evento_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_EVENTOS_ESPECIALES, evento_id)


# Tags narrativos (narrative_tags)
async def crear_o_actualizar_tag(req: TagCreateRequest) -> TagResponse:
    return await guardar_item_catalogo(COLL_TAGS, req.id, req, TagResponse)


async def obtener_tags(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[TagResponse]:
    return await listar_items_catalogo(COLL_TAGS, TagResponse, universo_id, limit, skip)


async def obtener_tag_por_id(tag_id: str) -> Optional[TagResponse]:
    return await obtener_item_catalogo_por_id(COLL_TAGS, tag_id, TagResponse)


async def eliminar_tag(tag_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_TAGS, tag_id)
