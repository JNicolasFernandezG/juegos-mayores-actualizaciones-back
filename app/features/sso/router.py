from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from app.core.dependencies import get_current_admin, security_bearer, set_auth_cookie
from app.features.sso.schemas import (
    CanjearTicketRequest,
    CanjearTicketResponse,
    CrearTicketRetornoRequest,
    CrearTicketRetornoResponse,
)
from app.features.sso.service import canjear_ticket_en_autenticador, crear_ticket_retorno

router = APIRouter(prefix="/api/auth/sso", tags=["Autenticación - SSO"])


@router.post(
    "/canjear-ticket",
    response_model=CanjearTicketResponse,
    summary="Canjear un ticket descartable de entrada emitido por el Autenticador para iniciar sesión en la Torre de Control",
)
async def endpoint_canjear_ticket(
    req: CanjearTicketRequest,
    request: Request,
    response: Response
):
    result = await canjear_ticket_en_autenticador(req.ticket)
    if result.get("token"):
        set_auth_cookie(response, request, result["token"])
    return result


@router.post(
    "/crear-ticket-retorno",
    response_model=CrearTicketRetornoResponse,
    summary="Generar un ticket descartable de retorno para saltar de regreso a otro panel (Solo Admin autenticado)",
)
async def endpoint_crear_ticket_retorno(
    req: CrearTicketRetornoRequest,
    request: Request,
    admin: Dict[str, Any] = Depends(get_current_admin),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
):
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request and request.cookies.get("access_token"):
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere token para emitir ticket de retorno.",
        )
    return await crear_ticket_retorno(
        token_actual=token,
        servicio_destino=req.servicioDestino or "autenticador",
    )
