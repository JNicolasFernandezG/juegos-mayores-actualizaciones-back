"""
crud_service.py
Servicios CRUD del catálogo base (Universos, Personajes, Cartas, Finalizaciones)
y re-exportación compatible de grafos V2 y tags.
"""

from typing import List, Optional, Type, TypeVar
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.database import get_database
from app.features.narrative.admin.crud_base import (
    eliminar_item_catalogo_por_id,
    guardar_item_catalogo,
    listar_items_catalogo,
    obtener_item_catalogo_por_id,
)
from app.features.narrative.admin.v2_crud_service import (
    crear_o_actualizar_conversacion_v2,
    crear_o_actualizar_evento_especial_v2,
    crear_o_actualizar_evento_v2,
    crear_o_actualizar_tag,
    eliminar_conversacion_v2,
    eliminar_evento_especial_v2,
    eliminar_evento_v2,
    eliminar_tag,
    guardar_grafo_v2,
    obtener_conversacion_v2_por_id,
    obtener_conversaciones_v2,
    obtener_evento_especial_v2_por_id,
    obtener_evento_v2_por_id,
    obtener_eventos_especiales_v2,
    obtener_eventos_v2,
    obtener_tag_por_id,
    obtener_tags,
)
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHARACTERS,
    COLL_ENDINGS,
    COLL_SETTINGS,
    DIFICULTAD_FACIL_REDUCCION_DEFAULT,
)
from app.features.narrative.schemas.catalog_schemas import (
    CartaCreateRequest,
    CartaResponse,
    FinalizacionCreateRequest,
    FinalizacionResponse,
    PersonajeCreateRequest,
    PersonajeResponse,
    UniversoCreateRequest,
    UniversoResponse,
)
from app.features.narrative.validation import validar_efectos_almacenables

T = TypeVar("T", bound=BaseModel)


async def guardar_item_con_efectos(
    collection_name: str,
    req: BaseModel,
    response_cls: Type[T],
) -> T:
    """Guarda una carta o personaje sólo si cada efecto es ejecutable por el motor."""
    hallazgos = await validar_efectos_almacenables(
        getattr(req, "efectos", None) or [],
        req.universo_id,
        tags=getattr(req, "tags", None) or [],
        condiciones_aparicion=getattr(req, "condiciones_aparicion", None) or [],
    )
    if hallazgos:
        raise HTTPException(
            status_code=422,
            detail={
                "mensaje": "Los efectos declaran contenido que el motor no puede ejecutar.",
                "errores": [h.as_dict() for h in hallazgos],
            },
        )
    return await guardar_item_catalogo(collection_name, req.id, req, response_cls)


# Universos
async def crear_o_actualizar_universo(req: UniversoCreateRequest) -> UniversoResponse:
    """El panel no conoce el factor de dificultad: si no lo envía, se conserva el guardado."""
    db = get_database()
    doc = req.model_dump(by_alias=True)
    if req.dificultad_facil_reduccion is None:
        existente = await db[COLL_SETTINGS].find_one(
            {"_id": req.id}, {"dificultad_facil_reduccion": 1}
        )
        doc["dificultad_facil_reduccion"] = (existente or {}).get(
            "dificultad_facil_reduccion", DIFICULTAD_FACIL_REDUCCION_DEFAULT
        )
    await db[COLL_SETTINGS].replace_one({"_id": req.id}, doc, upsert=True)
    return UniversoResponse(**doc)


async def obtener_universos() -> List[UniversoResponse]:
    return await listar_items_catalogo(COLL_SETTINGS, UniversoResponse)


async def obtener_universo_por_id(universo_id: str) -> Optional[UniversoResponse]:
    return await obtener_item_catalogo_por_id(COLL_SETTINGS, universo_id, UniversoResponse)


async def eliminar_universo(universo_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_SETTINGS, universo_id)


# Personajes
async def crear_o_actualizar_personaje(req: PersonajeCreateRequest) -> PersonajeResponse:
    return await guardar_item_con_efectos(COLL_CHARACTERS, req, PersonajeResponse)


async def obtener_personajes(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[PersonajeResponse]:
    return await listar_items_catalogo(COLL_CHARACTERS, PersonajeResponse, universo_id, limit, skip)


async def obtener_personaje_por_id(personaje_id: str) -> Optional[PersonajeResponse]:
    return await obtener_item_catalogo_por_id(COLL_CHARACTERS, personaje_id, PersonajeResponse)


async def eliminar_personaje(personaje_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_CHARACTERS, personaje_id)


# Cartas
async def crear_o_actualizar_carta(req: CartaCreateRequest) -> CartaResponse:
    return await guardar_item_con_efectos(COLL_CARDS, req, CartaResponse)


async def obtener_cartas(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[CartaResponse]:
    return await listar_items_catalogo(COLL_CARDS, CartaResponse, universo_id, limit, skip)


async def obtener_carta_por_id(carta_id: str) -> Optional[CartaResponse]:
    return await obtener_item_catalogo_por_id(COLL_CARDS, carta_id, CartaResponse)


async def eliminar_carta(carta_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_CARDS, carta_id)


# Finalizaciones
async def crear_o_actualizar_finalizacion(req: FinalizacionCreateRequest) -> FinalizacionResponse:
    return await guardar_item_catalogo(COLL_ENDINGS, req.id, req, FinalizacionResponse)


async def obtener_finalizaciones(
    universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0
) -> List[FinalizacionResponse]:
    return await listar_items_catalogo(COLL_ENDINGS, FinalizacionResponse, universo_id, limit, skip)


async def obtener_finalizacion_por_id(finalizacion_id: str) -> Optional[FinalizacionResponse]:
    return await obtener_item_catalogo_por_id(COLL_ENDINGS, finalizacion_id, FinalizacionResponse)


async def eliminar_finalizacion(finalizacion_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_ENDINGS, finalizacion_id)


__all__ = [
    "guardar_item_catalogo", "listar_items_catalogo",
    "obtener_item_catalogo_por_id", "eliminar_item_catalogo_por_id",
    "guardar_grafo_v2", "guardar_item_con_efectos",
    "crear_o_actualizar_universo", "obtener_universos", "obtener_universo_por_id", "eliminar_universo",
    "crear_o_actualizar_personaje", "obtener_personajes", "obtener_personaje_por_id", "eliminar_personaje",
    "crear_o_actualizar_carta", "obtener_cartas", "obtener_carta_por_id", "eliminar_carta",
    "crear_o_actualizar_finalizacion", "obtener_finalizaciones", "obtener_finalizacion_por_id", "eliminar_finalizacion",
    "crear_o_actualizar_evento_v2", "obtener_eventos_v2", "obtener_evento_v2_por_id", "eliminar_evento_v2",
    "crear_o_actualizar_conversacion_v2", "obtener_conversaciones_v2", "obtener_conversacion_v2_por_id", "eliminar_conversacion_v2",
    "crear_o_actualizar_evento_especial_v2", "obtener_eventos_especiales_v2", "obtener_evento_especial_v2_por_id", "eliminar_evento_especial_v2",
    "crear_o_actualizar_tag", "obtener_tags", "obtener_tag_por_id", "eliminar_tag",
]
