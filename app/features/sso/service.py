import httpx
from typing import Dict, Any
from fastapi import HTTPException, status
from app.core.config import settings
from app.features.auth.central_client import post_to_auth_service
from app.features.auth.service import sync_local_user_from_auth_service, format_user_response


async def canjear_ticket_en_autenticador(ticket: str) -> Dict[str, Any]:
    """
    Canjea el ticket efímero de acceso contra el microservicio central de Autenticación.
    Al validarse, el Autenticador quema el ticket en el mismo instante y emite el JWT oficial.
    SIPI-BACK sincroniza de inmediato el perfil local del administrador.
    """
    if not ticket or not ticket.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El ticket es obligatorio para realizar el canje.",
        )

    data = await post_to_auth_service(
        "/auth/sso/consume-ticket",
        {"ticket": ticket.strip(), "servicio": settings.SERVICE_KEY},
        default_error="Ticket inválido, expirado o ya utilizado.",
        client_cls=httpx.AsyncClient,
        base_url=settings.AUTH_SERVICE_URL,
    )
    remote_user = data.get("user") if isinstance(data.get("user"), dict) else {}
    local_user = await sync_local_user_from_auth_service(remote_user)

    return {
        "success": True,
        "message": "Acceso SSO concedido exitosamente.",
        "token": data.get("token"),
        "user": format_user_response(local_user),
    }


async def crear_ticket_retorno(token_actual: str, servicio_destino: str = "autenticador") -> Dict[str, Any]:
    """
    Solicita al Autenticador Central un ticket efímero de retorno
    para que el administrador pueda saltar de regreso al panel central de usuarios.
    """
    return await post_to_auth_service(
        "/auth/sso/create-ticket",
        {"servicio": servicio_destino.strip().lower()},
        headers={"Authorization": f"Bearer {token_actual}"},
        default_error="No se pudo generar el ticket de retorno SSO.",
        client_cls=httpx.AsyncClient,
        base_url=settings.AUTH_SERVICE_URL,
    )
