from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_admin, get_current_user

from .consejos import (
    actualizar_consejo,
    crear_consejo,
    eliminar_consejo,
    listar_consejos,
)
from .schemas import ConsejoAdmin, ConsejoUpsert, PerfilResumenResponse
from .service import obtener_resumen_de_perfil

router = APIRouter(tags=["Perfil"])
admin_router = APIRouter(tags=["Perfil - Administración"])


@router.get(
    "/api/profile/summary",
    response_model=PerfilResumenResponse,
    summary="Obtener medallas, rendimiento y actividad del usuario autenticado",
)
async def endpoint_perfil_resumen(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await obtener_resumen_de_perfil(int(current_user["id"]))


@admin_router.get(
    "/api/admin/profile/tips",
    response_model=List[ConsejoAdmin],
    summary="Listar los consejos del perfil, incluidos los inactivos (Solo Admin)",
)
async def endpoint_admin_consejos(
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await listar_consejos(solo_activos=False)


@admin_router.post(
    "/api/admin/profile/tips",
    response_model=ConsejoAdmin,
    summary="Crear un consejo del perfil (Solo Admin)",
)
async def endpoint_admin_crear_consejo(
    req: ConsejoUpsert,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await crear_consejo(req)


@admin_router.put(
    "/api/admin/profile/tips/{consejo_id}",
    response_model=ConsejoAdmin,
    summary="Editar un consejo, su orden o su visibilidad (Solo Admin)",
)
async def endpoint_admin_actualizar_consejo(
    consejo_id: str,
    req: ConsejoUpsert,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await actualizar_consejo(consejo_id, req)


@admin_router.delete(
    "/api/admin/profile/tips/{consejo_id}",
    summary="Eliminar un consejo del perfil (Solo Admin)",
)
async def endpoint_admin_eliminar_consejo(
    consejo_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    return await eliminar_consejo(consejo_id)
