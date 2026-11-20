"""Casos de uso de autenticación delegados al microservicio central."""

from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import (
    GUEST_ID_PATTERN,
    crear_credencial_invitado,
    decode_guest_credential,
    generar_guest_id,
)
from app.features.auth.central_client import post_to_auth_service
from app.features.auth.schemas import (
    LoginCodigoRequest,
    LoginSistemasRequest,
    RegisterRequest,
    VerificarTokenRequest,
)
from app.features.auth.user_sync import (  # noqa: F401
    _extract_first,
    _normalize_role,
    _to_bool,
    format_user_response,
    sync_local_user_from_auth_service,
)


async def _post_auth(
    endpoint: str,
    payload: Dict[str, Any],
    *,
    default_error: str,
    fixed_error_status: Optional[int] = None,
) -> Dict[str, Any]:
    return await post_to_auth_service(
        endpoint,
        payload,
        default_error=default_error,
        client_cls=httpx.AsyncClient,
        fixed_error_status=fixed_error_status,
        base_url=settings.AUTH_SERVICE_URL,
    )


async def _finalize_auth_response(
    data: Dict[str, Any],
    default_message: str,
    *,
    use_remote_message: bool = False,
    token_fallback: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    remote_user = data.get("user") if isinstance(data.get("user"), dict) else {}
    local_user = await sync_local_user_from_auth_service(remote_user)
    token = data.get("token") if token_fallback is None else (data.get("token") or token_fallback)
    message = (data.get("message") or default_message) if use_remote_message else default_message
    return {
        "success": True,
        "message": message,
        "token": token,
        "user": format_user_response(local_user),
        **extra,
    }


async def login_sistemas(req: LoginSistemasRequest) -> Dict[str, Any]:
    """Autentica al operador de sistemas delegando en el microservicio central."""
    data = await _post_auth(
        "/auth/login",
        {"email": req.email.lower().strip(), "password": req.password, "servicio": settings.SERVICE_KEY},
        default_error="Credenciales incorrectas",
    )
    remote_user = data.get("user") if isinstance(data.get("user"), dict) else {}
    if _normalize_role(remote_user) != 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: Se requieren permisos de Operador de Sistemas",
        )
    return await _finalize_auth_response(data, "Inicio de sesión exitoso")


async def login_codigo(req: LoginCodigoRequest) -> Dict[str, Any]:
    """Autentica alumnos por correo y PIN de 6 dígitos en el microservicio central."""
    email_clean, code = str(req.email).strip().lower(), req.get_codigo()
    if not email_clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El correo electrónico es obligatorio")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La clave de 6 dígitos es obligatoria")

    data = await _post_auth(
        "/auth/validar-acceso",
        {"email": email_clean, "codigoAcceso": code, "servicio": settings.SERVICE_KEY},
        default_error="Correo o clave de 6 dígitos incorrecta",
    )
    if not data.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if data.get("success") else status.HTTP_401_UNAUTHORIZED,
            detail=data.get("message") or "Acceso denegado: correo o clave incorrecta.",
        )
    return await _finalize_auth_response(data, "Acceso concedido exitosamente.")


async def verificar_token(req: VerificarTokenRequest) -> Dict[str, Any]:
    """Verifica la validez de un token JWT contra el microservicio central."""
    data = await _post_auth(
        "/auth/validar-acceso",
        {"token": req.token, "servicio": settings.SERVICE_KEY},
        default_error="Token inválido o expirado",
        fixed_error_status=status.HTTP_401_UNAUTHORIZED,
    )
    if not data.get("allowed"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=data.get("message") or "Token inválido o no autorizado para el servicio.",
        )
    return await _finalize_auth_response(
        data, "Token verificado con éxito", token_fallback=req.token, valid=True
    )


async def register_usuario(req: RegisterRequest, is_admin_creation: bool = False) -> Dict[str, Any]:
    """Registra un nuevo usuario delegando creación y PIN al Autenticador Central."""
    payload: Dict[str, object] = {
        "name": req.name.strip(),
        "email": req.email.lower().strip(),
        "password": req.password,
        "codigoAcceso": req.codigoAcceso,
        "servicioOrigen": settings.SERVICE_KEY,
        "tipoUsuario": req.tipoUsuario if (is_admin_creation and req.tipoUsuario is not None) else 1,
        "black": bool(req.black) if (is_admin_creation and req.black is not None) else False,
        "activo": bool(req.activo) if (is_admin_creation and req.activo is not None) else True,
        "servicios": {settings.SERVICE_KEY: True, "cognijuegos": True},
    }
    data = await _post_auth(
        "/auth/register",
        payload,
        default_error="Error al registrar el usuario en el Autenticador Central",
    )
    return await _finalize_auth_response(data, "Usuario registrado con éxito.", use_remote_message=True)


def emitir_credencial_invitado(credencial_actual: Optional[str]) -> dict:
    """Emite o renueva una credencial firmada de invitado."""
    guest_id = None
    if credencial_actual:
        payload = decode_guest_credential(credencial_actual)
        candidato = (payload or {}).get("sub")
        if isinstance(candidato, str) and GUEST_ID_PATTERN.match(candidato):
            guest_id = candidato
    if not guest_id:
        guest_id = generar_guest_id()

    return {
        "success": True,
        "guest_id": guest_id,
        "credential": crear_credencial_invitado(guest_id),
        "expires_in_days": settings.GUEST_CREDENTIAL_EXPIRATION_DAYS,
    }
