"""
crud_base.py
Primitivas genéricas de persistencia CRUD sobre colecciones de catálogo narrativo.
"""

from typing import Optional, List, Type, TypeVar
from pydantic import BaseModel

from app.core.database import get_database

T = TypeVar("T", bound=BaseModel)


async def guardar_item_catalogo(
    collection_name: str,
    item_id: str,
    data: BaseModel,
    response_cls: Type[T],
) -> T:
    """Inserta o actualiza un documento en la colección especificada y lo retorna validado."""
    db = get_database()
    doc = data.model_dump(by_alias=True)
    await db[collection_name].replace_one({"_id": item_id}, doc, upsert=True)
    return response_cls(**doc)


async def listar_items_catalogo(
    collection_name: str,
    response_cls: Type[T],
    universo_id: Optional[str] = None,
    limit: Optional[int] = None,
    skip: int = 0,
) -> List[T]:
    """Lista documentos de una colección aplicando filtro opcional de universo y paginación."""
    db = get_database()
    filtro = {"universo_id": universo_id} if universo_id else {}
    cursor = db[collection_name].find(filtro).skip(skip)
    if limit is not None and limit > 0:
        cursor = cursor.limit(limit)
    docs = await cursor.to_list(length=limit or 500)
    return [response_cls(**d) for d in docs]


async def obtener_item_catalogo_por_id(
    collection_name: str,
    item_id: str,
    response_cls: Type[T],
) -> Optional[T]:
    """Recupera un documento específico de una colección por su ID."""
    db = get_database()
    doc = await db[collection_name].find_one({"_id": item_id})
    return response_cls(**doc) if doc else None


async def eliminar_item_catalogo_por_id(collection_name: str, item_id: str) -> bool:
    """Elimina un documento de la colección dada por su identificador único."""
    db = get_database()
    res = await db[collection_name].delete_one({"_id": item_id})
    return res.deleted_count > 0
