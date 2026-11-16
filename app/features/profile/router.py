from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user

from .schemas import PerfilResumenResponse
from .service import obtener_resumen_de_perfil

router = APIRouter(tags=["Perfil"])


@router.get(
    "/api/profile/summary",
    response_model=PerfilResumenResponse,
    summary="Obtener medallas, rendimiento y actividad del usuario autenticado",
)
async def endpoint_perfil_resumen(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await obtener_resumen_de_perfil(int(current_user["id"]))
