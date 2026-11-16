"""CRUD de planes de suscripción administrados desde la Torre de Control."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException, status
from pydantic import ValidationError
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database

from .schemas import (
    ConfigSuscripcion,
    ConfigSuscripcionUpdate,
    PlanCreateRequest,
    PlanSuscripcion,
    PlanUpdateRequest,
    PrecioPlan,
)

COLL_PLANES = "planes_suscripcion"
COLL_CONFIG = "suscripcion_config"
CONFIG_ID = "global"


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _precio_guardado(valor: Any) -> PrecioPlan:
    if not isinstance(valor, dict):
        return PrecioPlan()
    try:
        return PrecioPlan(**valor)
    except (ValidationError, TypeError):
        return PrecioPlan()


def _descuento_anual(valor: Any) -> float:
    try:
        descuento = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, descuento))


def _precio_anual(precio: PrecioPlan, descuento: float) -> PrecioPlan:
    """Doce meses con el descuento aplicado; sin precio mensual no hay anual que ofrecer."""
    if precio.monto is None:
        return PrecioPlan(monto=None, moneda=precio.moneda)
    total = precio.monto * 12 * (1 - descuento / 100)
    return PrecioPlan(monto=round(total, 2), moneda=precio.moneda)


def _entero(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _serializar(doc: Dict[str, Any]) -> PlanSuscripcion:
    beneficios = doc.get("beneficios")
    precio = _precio_guardado(doc.get("precio"))
    descuento = _descuento_anual(doc.get("descuento_anual_pct"))
    return PlanSuscripcion(
        codigo=str(doc.get("codigo", "")),
        nombre=str(doc.get("nombre", "")),
        descripcion=str(doc.get("descripcion") or ""),
        precio=precio,
        descuento_anual_pct=descuento,
        precio_anual=_precio_anual(precio, descuento),
        beneficios=[beneficio for beneficio in beneficios if isinstance(beneficio, str)]
        if isinstance(beneficios, list)
        else [],
        orden=_entero(doc.get("orden")),
        visible=doc.get("visible", True) is not False,
        habilitado=doc.get("habilitado") is True,
        updated_at=doc.get("updated_at"),
    )


def _serializar_config(doc: Dict[str, Any] | None) -> ConfigSuscripcion:
    if not doc:
        return ConfigSuscripcion()
    return ConfigSuscripcion(
        anual_habilitado=doc.get("anual_habilitado") is True,
        updated_at=doc.get("updated_at"),
    )


def _no_encontrado(codigo: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Plan '{codigo}' no encontrado.",
    )


async def listar_planes(*, solo_visibles: bool) -> List[PlanSuscripcion]:
    """Devuelve el catálogo ordenado; los jugadores solo ven los planes marcados como visibles."""
    query: Dict[str, Any] = {"visible": True} if solo_visibles else {}
    docs = await get_database()[COLL_PLANES].find(query).sort(
        [("orden", 1), ("nombre", 1)]
    ).to_list(length=None)
    return [_serializar(doc) for doc in docs]


async def obtener_config() -> ConfigSuscripcion:
    doc = await get_database()[COLL_CONFIG].find_one({"_id": CONFIG_ID})
    return _serializar_config(doc)


async def actualizar_config(req: ConfigSuscripcionUpdate) -> ConfigSuscripcion:
    cambios = {"anual_habilitado": req.anual_habilitado, "updated_at": _ahora_iso()}
    await get_database()[COLL_CONFIG].update_one(
        {"_id": CONFIG_ID}, {"$set": cambios}, upsert=True
    )
    return ConfigSuscripcion(**cambios)


async def crear_plan(req: PlanCreateRequest) -> PlanSuscripcion:
    doc = {
        "codigo": req.codigo,
        "nombre": req.nombre,
        "descripcion": req.descripcion,
        "precio": req.precio.model_dump(),
        "descuento_anual_pct": req.descuento_anual_pct,
        "beneficios": req.beneficios,
        "orden": req.orden,
        "visible": req.visible,
        "habilitado": req.habilitado,
        "updated_at": _ahora_iso(),
    }
    try:
        await get_database()[COLL_PLANES].insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un plan con el código '{req.codigo}'.",
        ) from exc
    return _serializar(doc)


async def actualizar_plan(codigo: str, req: PlanUpdateRequest) -> PlanSuscripcion:
    cambios = req.model_dump(exclude_unset=True)
    if "precio" in cambios and req.precio is not None:
        cambios["precio"] = req.precio.model_dump()

    if not cambios:
        actual = await get_database()[COLL_PLANES].find_one({"codigo": codigo})
        if not actual:
            raise _no_encontrado(codigo)
        return _serializar(actual)

    cambios["updated_at"] = _ahora_iso()
    doc = await get_database()[COLL_PLANES].find_one_and_update(
        {"codigo": codigo},
        {"$set": cambios},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise _no_encontrado(codigo)
    return _serializar(doc)


async def eliminar_plan(codigo: str) -> Dict[str, Any]:
    resultado = await get_database()[COLL_PLANES].delete_one({"codigo": codigo})
    if resultado.deleted_count == 0:
        raise _no_encontrado(codigo)
    return {"success": True, "message": f"Plan '{codigo}' eliminado."}
