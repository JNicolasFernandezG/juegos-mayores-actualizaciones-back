"""
actions_crud_service.py
Servicios CRUD con OCC para el catálogo de acciones y frecuencias del motor narrativo.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from app.core.database import get_database
from app.features.narrative.admin.actions_catalog_meta import (
    CATALOGO_PRIMITIVAS,
    EVENTOS_MOTOR,
    _frecuencias_default,
    obtener_usos_accion,
    obtener_usos_frecuencia,
)
from app.features.narrative.constants import COLL_ACTIONS, COLL_FREQUENCIES
from app.features.narrative.schemas.rules_schemas import (
    AccionCatalogoCreateRequest,
    AccionCatalogoResponse,
    AccionCatalogoUpdateRequest,
    FrecuenciasUniversoDocument,
    FrecuenciasUniversoUpdateRequest,
)

logger = logging.getLogger(__name__)


async def crear_accion(payload: AccionCatalogoCreateRequest) -> AccionCatalogoResponse:
    db = get_database()
    col = db[COLL_ACTIONS]

    # El _id es único en toda la colección: el mismo nombre en otro universo también choca.
    existente = await col.find_one({"_id": payload.id})
    if existente:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe una acción con ID '{payload.id}' en el universo "
                f"'{existente.get('universo_id')}'. Los IDs de acción son globales; usa otro ID."
            ),
        )

    doc = {
        "_id": payload.id,
        "universo_id": payload.universo_id,
        "nombre": payload.nombre,
        "descripcion": payload.descripcion or "",
        "primitiva": payload.primitiva.value,
        "permitido_en": payload.permitido_en,
        "activo": payload.activo,
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await col.insert_one(doc)
    return AccionCatalogoResponse(**doc)


async def listar_acciones(universo_id: Optional[str] = None) -> List[AccionCatalogoResponse]:
    db = get_database()
    filtro: Dict[str, Any] = {"universo_id": universo_id} if universo_id else {}
    docs = await db[COLL_ACTIONS].find(filtro).sort("nombre", 1).to_list(None)
    return [AccionCatalogoResponse(**d) for d in docs]


async def _buscar_accion_o_404(accion_id: str, universo_id: Optional[str] = None) -> tuple[Any, Dict[str, Any], Dict[str, Any]]:
    col = get_database()[COLL_ACTIONS]
    filtro: Dict[str, Any] = {"_id": accion_id}
    if universo_id:
        filtro["universo_id"] = universo_id
    doc = await col.find_one(filtro)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Acción '{accion_id}' no encontrada.")
    return col, filtro, doc


def _validar_occ(doc: Dict[str, Any], expected_version: Optional[int], mensaje_tpl: str) -> None:
    actual = doc.get("version", 1)
    if expected_version is not None and actual != expected_version:
        raise HTTPException(status_code=409, detail=mensaje_tpl.format(expected=expected_version, actual=actual))


async def obtener_accion_por_id(accion_id: str, universo_id: Optional[str] = None) -> AccionCatalogoResponse:
    _, _, doc = await _buscar_accion_o_404(accion_id, universo_id)
    return AccionCatalogoResponse(**doc)


async def actualizar_accion(
    accion_id: str,
    payload: AccionCatalogoUpdateRequest,
    universo_id: Optional[str] = None,
) -> AccionCatalogoResponse:
    col, filtro, doc = await _buscar_accion_o_404(accion_id, universo_id)
    _validar_occ(
        doc,
        payload.expected_version,
        "Conflicto de concurrencia: la versión esperada ({expected}) no coincide con la actual ({actual}).",
    )

    updates: Dict[str, Any] = {
        "version": doc.get("version", 1) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for campo in ("nombre", "descripcion", "permitido_en", "activo"):
        valor = getattr(payload, campo)
        if valor is not None:
            updates[campo] = valor
    if payload.primitiva is not None:
        updates["primitiva"] = payload.primitiva.value

    await col.update_one(filtro, {"$set": updates})
    doc.update(updates)
    return AccionCatalogoResponse(**doc)


async def eliminar_accion(accion_id: str, universo_id: Optional[str] = None) -> Dict[str, Any]:
    col, filtro, _ = await _buscar_accion_o_404(accion_id, universo_id)

    usos = await obtener_usos_accion(accion_id)
    if usos["total_usos"] > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar la acción '{accion_id}' porque está referenciada en {usos['total_usos']} entidad(es). Desactívela en su lugar.",
        )

    await col.delete_one(filtro)
    return {"message": f"Acción '{accion_id}' eliminada exitosamente.", "id": accion_id}


async def obtener_frecuencias_universo(universo_id: str) -> FrecuenciasUniversoDocument:
    """Lee el catálogo sin escribir: los defaults se materializan en memoria hasta que alguien los guarde."""
    db = get_database()
    doc = await db[COLL_FREQUENCIES].find_one({"_id": f"frecuencias_{universo_id}"})

    if not doc:
        return FrecuenciasUniversoDocument(
            _id=f"frecuencias_{universo_id}",
            universo_id=universo_id,
            version=0,
            items=_frecuencias_default(universo_id),
        )

    return FrecuenciasUniversoDocument(**doc)


def _validar_items_frecuencias(items: List[Any]) -> List[Dict[str, Any]]:
    eventos_validos = {e["evento_motor"] for e in EVENTOS_MOTOR}
    conteos_validos = {
        conteo for evento in EVENTOS_MOTOR for conteo in evento.get("opciones_conteo", [])
    }
    vistos = set()
    items_dict: List[Dict[str, Any]] = []
    for item in items:
        if item.id in vistos:
            raise HTTPException(status_code=422, detail=f"ID de frecuencia duplicado en el catálogo: '{item.id}'.")
        vistos.add(item.id)
        if item.evento_motor not in eventos_validos:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"La frecuencia '{item.id}' usa el evento '{item.evento_motor}', que el motor no emite. "
                    f"Válidos: {sorted(eventos_validos)}."
                ),
            )
        if item.evento_motor != "inicio_mes" and item.cada != 1:
            raise HTTPException(
                status_code=422,
                detail=f"La frecuencia '{item.id}' define 'cada={item.cada}' pero '{item.evento_motor}' no tiene periodicidad.",
            )
        if item.evento_motor == "inicio_mes" and item.conteo_desde not in conteos_validos:
            raise HTTPException(
                status_code=422,
                detail=f"La frecuencia '{item.id}' cuenta desde '{item.conteo_desde}', opción no soportada.",
            )
        items_dict.append(item.model_dump())
    return items_dict


async def actualizar_frecuencias_universo(
    universo_id: str,
    payload: FrecuenciasUniversoUpdateRequest,
) -> FrecuenciasUniversoDocument:
    db = get_database()
    col = db[COLL_FREQUENCIES]
    doc_id = f"frecuencias_{universo_id}"
    doc = await col.find_one({"_id": doc_id})

    if not doc:
        doc = {
            "_id": doc_id,
            "universo_id": universo_id,
            "version": 0,
            "items": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    _validar_occ(
        doc,
        payload.expected_version,
        "Conflicto de concurrencia: versión esperada {expected} difiere de la actual {actual}.",
    )

    items_dict = _validar_items_frecuencias(payload.items)
    updates = {
        "universo_id": universo_id,
        "version": doc.get("version", 1) + 1,
        "items": items_dict,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await col.update_one({"_id": doc_id}, {"$set": updates}, upsert=True)
    doc.update(updates)
    return FrecuenciasUniversoDocument(**doc)


__all__ = [
    "CATALOGO_PRIMITIVAS",
    "EVENTOS_MOTOR",
    "_frecuencias_default",
    "obtener_usos_accion",
    "obtener_usos_frecuencia",
    "crear_accion",
    "listar_acciones",
    "obtener_accion_por_id",
    "actualizar_accion",
    "eliminar_accion",
    "obtener_frecuencias_universo",
    "actualizar_frecuencias_universo",
]
