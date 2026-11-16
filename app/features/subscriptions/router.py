"""Catálogo de planes de suscripción y su administración."""

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_admin, get_current_user

from .schemas import (
    CatalogoPlanes,
    ConfigSuscripcion,
    ConfigSuscripcionUpdate,
    PlanCreateRequest,
    PlanSuscripcion,
    PlanUpdateRequest,
)
from .service import (
    actualizar_config,
    actualizar_plan,
    crear_plan,
    eliminar_plan,
    listar_planes,
    obtener_config,
)

router = APIRouter(tags=["Suscripciones"])
admin_router = APIRouter(tags=["Suscripciones - Administración"])


@router.get(
    "/api/subscription/plans",
    response_model=CatalogoPlanes,
    summary="Listar los planes visibles y si el cobro anual está disponible",
)
async def endpoint_planes_visibles(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    config = await obtener_config()
    planes = await listar_planes(solo_visibles=True)
    return CatalogoPlanes(anual_habilitado=config.anual_habilitado, planes=planes)


@admin_router.get(
    "/api/admin/subscription/plans",
    response_model=list[PlanSuscripcion],
    summary="Listar todos los planes de suscripción, incluidos los ocultos (Solo Admin)",
)
async def endpoint_admin_planes(
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await listar_planes(solo_visibles=False)


@admin_router.get(
    "/api/admin/subscription/settings",
    response_model=ConfigSuscripcion,
    summary="Leer la configuración global de suscripciones (Solo Admin)",
)
async def endpoint_admin_config(
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await obtener_config()


@admin_router.put(
    "/api/admin/subscription/settings",
    response_model=ConfigSuscripcion,
    summary="Activar o desactivar las membresías anuales (Solo Admin)",
)
async def endpoint_admin_actualizar_config(
    req: ConfigSuscripcionUpdate,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await actualizar_config(req)


@admin_router.post(
    "/api/admin/subscription/plans",
    response_model=PlanSuscripcion,
    summary="Crear un plan de suscripción (Solo Admin)",
)
async def endpoint_admin_crear_plan(
    req: PlanCreateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await crear_plan(req)


@admin_router.put(
    "/api/admin/subscription/plans/{codigo}",
    response_model=PlanSuscripcion,
    summary="Editar un plan, incluidos los flags de visibilidad y compra (Solo Admin)",
)
async def endpoint_admin_actualizar_plan(
    codigo: str,
    req: PlanUpdateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await actualizar_plan(codigo, req)


@admin_router.delete(
    "/api/admin/subscription/plans/{codigo}",
    summary="Eliminar un plan de suscripción (Solo Admin)",
)
async def endpoint_admin_eliminar_plan(
    codigo: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await eliminar_plan(codigo)
