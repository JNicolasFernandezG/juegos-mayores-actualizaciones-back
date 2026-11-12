"""
crud_service.py
Capa CRUD genérica reutilizable y servicios de administración para las colecciones
del catálogo narrativo V2 (Universos, Personajes, Cartas, Finalizaciones y Grafos V2).
"""

from typing import TypeVar, Type, Optional, List
from fastapi import HTTPException
from pydantic import BaseModel

from app.core.database import get_database
from app.features.narrative.validation import validar_efectos_almacenables, validar_grafo_para_guardado
from app.features.narrative.constants import (
    COLL_TAGS,
    COLL_SETTINGS,
    COLL_CHARACTERS,
    COLL_CARDS,
    COLL_ENDINGS,
    COLL_V2_EVENTS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    DIFICULTAD_FACIL_REDUCCION_DEFAULT,
)
from app.features.narrative.schemas.catalog_schemas import (
    UniversoCreateRequest,
    UniversoResponse,
    PersonajeCreateRequest,
    PersonajeResponse,
    CartaCreateRequest,
    CartaResponse,
    FinalizacionCreateRequest,
    FinalizacionResponse,
    TagCreateRequest,
    TagResponse
)
from app.features.narrative.schemas.v2_graph_schemas import (
    EventoV2GrafoSchema,
    ConversacionV2GrafoSchema,
    EventoEspecialV2GrafoSchema,
)

T = TypeVar("T", bound=BaseModel)

# ============================================================================
# OPERACIONES GENÉRICAS
# ============================================================================

async def guardar_item_catalogo(
    collection_name: str,
    item_id: str,
    data: BaseModel,
    response_cls: Type[T]
) -> T:
    """Inserta o actualiza un documento en la colección especificada y lo retorna validado."""
    db = get_database()
    doc = data.model_dump(by_alias=True)
    await db[collection_name].replace_one({"_id": item_id}, doc, upsert=True)
    return response_cls(**doc)

async def guardar_grafo_v2(
    collection_name: str,
    tipo: str,
    req: BaseModel,
    response_cls: Type[T]
) -> T:
    """
    Guarda un grafo V2 sólo si el motor puede ejecutar todo lo que declara.
    Un grafo con recursos, acciones o frecuencias inexistentes se guarda igual y
    falla en silencio recién en la partida, así que el guardado es la última barrera barata.
    """
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

async def guardar_item_con_efectos(
    collection_name: str,
    req: BaseModel,
    response_cls: Type[T]
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

async def listar_items_catalogo(
    collection_name: str,
    response_cls: Type[T],
    universo_id: Optional[str] = None,
    limit: Optional[int] = None,
    skip: int = 0
) -> List[T]:
    """Lista documentos de una colección aplicando filtro opcional de universo y paginación."""
    db = get_database()
    filtro = {}
    if universo_id:
        filtro["universo_id"] = universo_id

    cursor = db[collection_name].find(filtro).skip(skip)
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)

    docs = await cursor.to_list(length=limit or 500)
    return [response_cls(**d) for d in docs]

async def obtener_item_catalogo_por_id(
    collection_name: str,
    item_id: str,
    response_cls: Type[T]
) -> Optional[T]:
    """Recupera un documento específico de una colección por su ID."""
    db = get_database()
    doc = await db[collection_name].find_one({"_id": item_id})
    if not doc:
        return None
    return response_cls(**doc)

async def eliminar_item_catalogo_por_id(
    collection_name: str,
    item_id: str
) -> bool:
    """Elimina un documento de la colección dada por su identificador único."""
    db = get_database()
    res = await db[collection_name].delete_one({"_id": item_id})
    return res.deleted_count > 0

# ============================================================================
# CONVENIENCE WRAPPERS POR ENTIDAD
# ============================================================================

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

async def obtener_personajes(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[PersonajeResponse]:
    return await listar_items_catalogo(COLL_CHARACTERS, PersonajeResponse, universo_id, limit, skip)

async def obtener_personaje_por_id(personaje_id: str) -> Optional[PersonajeResponse]:
    return await obtener_item_catalogo_por_id(COLL_CHARACTERS, personaje_id, PersonajeResponse)

async def eliminar_personaje(personaje_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_CHARACTERS, personaje_id)

# Cartas
async def crear_o_actualizar_carta(req: CartaCreateRequest) -> CartaResponse:
    return await guardar_item_con_efectos(COLL_CARDS, req, CartaResponse)

async def obtener_cartas(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[CartaResponse]:
    return await listar_items_catalogo(COLL_CARDS, CartaResponse, universo_id, limit, skip)

async def obtener_carta_por_id(carta_id: str) -> Optional[CartaResponse]:
    return await obtener_item_catalogo_por_id(COLL_CARDS, carta_id, CartaResponse)

async def eliminar_carta(carta_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_CARDS, carta_id)

# Finalizaciones
async def crear_o_actualizar_finalizacion(req: FinalizacionCreateRequest) -> FinalizacionResponse:
    return await guardar_item_catalogo(COLL_ENDINGS, req.id, req, FinalizacionResponse)

async def obtener_finalizaciones(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[FinalizacionResponse]:
    return await listar_items_catalogo(COLL_ENDINGS, FinalizacionResponse, universo_id, limit, skip)

async def obtener_finalizacion_por_id(finalizacion_id: str) -> Optional[FinalizacionResponse]:
    return await obtener_item_catalogo_por_id(COLL_ENDINGS, finalizacion_id, FinalizacionResponse)

async def eliminar_finalizacion(finalizacion_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_ENDINGS, finalizacion_id)

# ============================================================================
# MOTOR NARRATIVO V2: GRAFOS DE EVENTOS Y CONVERSACIONES
# ============================================================================

# Eventos V2
async def crear_o_actualizar_evento_v2(req: EventoV2GrafoSchema) -> EventoV2GrafoSchema:
    return await guardar_grafo_v2(COLL_V2_EVENTS, "evento", req, EventoV2GrafoSchema)

async def obtener_eventos_v2(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[EventoV2GrafoSchema]:
    return await listar_items_catalogo(COLL_V2_EVENTS, EventoV2GrafoSchema, universo_id, limit, skip)

async def obtener_evento_v2_por_id(evento_id: str) -> Optional[EventoV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(COLL_V2_EVENTS, evento_id, EventoV2GrafoSchema)

async def eliminar_evento_v2(evento_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_EVENTS, evento_id)

# Conversaciones V2
async def crear_o_actualizar_conversacion_v2(req: ConversacionV2GrafoSchema) -> ConversacionV2GrafoSchema:
    return await guardar_grafo_v2(COLL_V2_CONVERSATIONS, "conversacion", req, ConversacionV2GrafoSchema)

async def obtener_conversaciones_v2(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[ConversacionV2GrafoSchema]:
    return await listar_items_catalogo(COLL_V2_CONVERSATIONS, ConversacionV2GrafoSchema, universo_id, limit, skip)

async def obtener_conversacion_v2_por_id(conversacion_id: str) -> Optional[ConversacionV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(COLL_V2_CONVERSATIONS, conversacion_id, ConversacionV2GrafoSchema)

async def eliminar_conversacion_v2(conversacion_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_CONVERSATIONS, conversacion_id)

# Eventos Especiales V2 (lealtad/traición por umbral de afinidad)
async def crear_o_actualizar_evento_especial_v2(req: EventoEspecialV2GrafoSchema) -> EventoEspecialV2GrafoSchema:
    return await guardar_grafo_v2(COLL_V2_EVENTOS_ESPECIALES, "evento_especial", req, EventoEspecialV2GrafoSchema)

async def obtener_eventos_especiales_v2(universo_id: Optional[str] = None, limit: Optional[int] = None, skip: int = 0) -> List[EventoEspecialV2GrafoSchema]:
    return await listar_items_catalogo(COLL_V2_EVENTOS_ESPECIALES, EventoEspecialV2GrafoSchema, universo_id, limit, skip)

async def obtener_evento_especial_v2_por_id(evento_id: str) -> Optional[EventoEspecialV2GrafoSchema]:
    return await obtener_item_catalogo_por_id(COLL_V2_EVENTOS_ESPECIALES, evento_id, EventoEspecialV2GrafoSchema)

async def eliminar_evento_especial_v2(evento_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_V2_EVENTOS_ESPECIALES, evento_id)



# ============================================================================
# TAGS NARRATIVOS (narrative_tags)
# ============================================================================

async def crear_o_actualizar_tag(req: TagCreateRequest) -> TagResponse:
    return await guardar_item_catalogo(COLL_TAGS, req.id, req, TagResponse)

async def obtener_tags(
    universo_id: Optional[str] = None,
    limit: Optional[int] = None,
    skip: int = 0
) -> List[TagResponse]:
    return await listar_items_catalogo(COLL_TAGS, TagResponse, universo_id, limit, skip)

async def obtener_tag_por_id(tag_id: str) -> Optional[TagResponse]:
    return await obtener_item_catalogo_por_id(COLL_TAGS, tag_id, TagResponse)

async def eliminar_tag(tag_id: str) -> bool:
    return await eliminar_item_catalogo_por_id(COLL_TAGS, tag_id)
