from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from app.core.rate_limit import rate_limit
from app.core.dependencies import get_optional_user, set_auth_cookie, clear_auth_cookie
from app.features.auth.schemas import (
    LoginSistemasRequest, LoginCodigoRequest, VerificarTokenRequest,
    RegisterRequest, GuestCredentialResponse
)
from app.features.auth.service import (
    login_sistemas, login_codigo, verificar_token, register_usuario,
    emitir_credencial_invitado, format_user_response
)
from app.shared.streak import registrar_ingreso_y_racha

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
    summary="Consultar estado de sesión actual desde cookie protegida o Bearer token (devuelve authenticated=false para invitados)"
)
async def endpoint_check_session(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)
):
    if not current_user:
        return {
            "success": True,
            "authenticated": False,
            "user": None,
            "racha": 0,
            "racha_ultima_fecha": None,
            "racha_hoy_ingresada": False,
        }

    # Verificar la sesión es el otro punto de arranque de la app: registra el ingreso del día
    # aunque la sesión persista por cookie y el cliente no vuelva a pedir credenciales.
    racha = await registrar_ingreso_y_racha(int(current_user["id"]))
    return {
        "success": True,
        "authenticated": True,
        "user": format_user_response(current_user),
        "racha": racha.actual,
        "racha_ultima_fecha": racha.ultima_fecha,
        "racha_hoy_ingresada": racha.hoy_ingresada,
    }


@router.post("/api/auth/verificar-token", summary="Verificar validez de token JWT y estado activo")
async def endpoint_verificar_token(
    req: VerificarTokenRequest,
    request: Request,
    response: Response,
):
    result = await verificar_token(req)
    if result.get("token"):
        set_auth_cookie(response, request, result["token"])
    return result


@router.post(
    "/api/auth/register",
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))],
    summary="Registrar nuevo usuario alumno delegando al Autenticador Central"
)
async def endpoint_register(
    req: RegisterRequest,
    request: Request,
    response: Response,
):
    # Registro público siempre crea cuentas de alumno (is_admin_creation=False)
    result = await register_usuario(req, is_admin_creation=False)
    if result.get("token"):
        set_auth_cookie(response, request, result["token"])
    return result


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
