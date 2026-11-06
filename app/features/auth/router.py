from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from app.core.rate_limit import rate_limit
from app.core.dependencies import get_current_user, set_auth_cookie, clear_auth_cookie
from app.features.auth.schemas import (
    LoginSistemasRequest, LoginCodigoRequest, VerificarTokenRequest,
    RegisterRequest, GuestCredentialResponse
)
from app.features.auth.service import (
    login_sistemas, login_codigo, verificar_token, register_usuario,
    emitir_credencial_invitado, format_user_response
)

router = APIRouter(tags=["Autenticación"])


@router.post(
    "/api/auth/login-sistemas",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
    summary="Iniciar sesión como Operador de Sistemas (Con Rate Limiting y Cookie HttpOnly)"
)
async def endpoint_login_sistemas(
    req: LoginSistemasRequest,
    request: Request,
    response: Response
):
    result = await login_sistemas(req)
    if result.get("token"):
        set_auth_cookie(response, request, result["token"])
    return result


@router.post(
    "/api/auth/ingresar-codigo",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
    summary="Ingreso de alumnos mediante PIN de 6 dígitos (Con Rate Limiting y Cookie HttpOnly)"
)
async def endpoint_login_codigo(
    req: LoginCodigoRequest,
    request: Request,
    response: Response
):
    result = await login_codigo(req)
    if result.get("token"):
        set_auth_cookie(response, request, result["token"])
    return result


@router.post(
    "/api/auth/logout",
    summary="Cerrar sesión y limpiar cookies protegidas de sesión"
)
async def endpoint_logout(response: Response):
    clear_auth_cookie(response)
    return {"success": True, "message": "Sesión cerrada exitosamente."}


@router.get(
    "/api/auth/session",
    summary="Verificar sesión actual desde cookie protegida o Bearer token"
)
async def endpoint_check_session(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    return {
        "success": True,
        "authenticated": True,
        "user": format_user_response(current_user)
    }


@router.post("/api/auth/verificar-token", summary="Verificar validez de token JWT y estado activo")
async def endpoint_verificar_token(req: VerificarTokenRequest):
    return await verificar_token(req)


@router.post(
    "/api/auth/register",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
    summary="Registrar nuevo usuario alumno delegando al Autenticador Central"
)
async def endpoint_register(req: RegisterRequest):
    # Registro público siempre crea cuentas de alumno (is_admin_creation=False)
    return await register_usuario(req, is_admin_creation=False)


@router.post(
    "/api/auth/guest-credential",
    response_model=GuestCredentialResponse,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))],
    summary="Emitir o renovar una credencial firmada de invitado para el narrativo"
)
async def endpoint_guest_credential(
    x_guest_credential: Optional[str] = Header(None)
):
    """Devuelve una identidad de invitado verificable; el cliente no puede elegirla."""
    return emitir_credencial_invitado(x_guest_credential)
