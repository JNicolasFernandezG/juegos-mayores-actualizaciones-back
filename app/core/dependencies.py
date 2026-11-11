from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.security import decode_access_token
from app.core.database import get_database
from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)

def set_auth_cookie(response: Response, request: Request, token: str) -> None:
    """Configura una cookie de sesión protegida con HttpOnly, SameSite=Lax y Secure."""
    is_secure = bool(
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
        or request.headers.get("x-forwarded-ssl") == "on"
        or (request.url.hostname and "asistodo.com.ar" in request.url.hostname)
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=settings.JWT_EXPIRATION_DAYS * 86400,
        path="/"
    )

def clear_auth_cookie(response: Response) -> None:
    """Elimina la cookie de sesión protegida al cerrar sesión."""
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        samesite="lax"
    )

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, Any]:
    """
    Extrae y valida el token JWT del encabezado Authorization Bearer o de la cookie HttpOnly 'access_token'.
    Verifica firma con JWT_SECRET compartido con el Autenticador Central,
    valida expiración y permisos de servicio para 'mayoresactualizaciones' / 'cognijuegos'.
    Garantiza que el perfil local exista en MongoDB para asegurar la persistencia
    de progresos y partidas de juegos.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request and request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    elif request and request.cookies.get("admin_session_token"):
        token = request.cookies.get("admin_session_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Token no proporcionado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Validar permisos específicos para el servicio cognijuegos
    tipo_usuario = int(payload.get("tipo_usuario") or payload.get("tipoUsuario") or 1)
    servicios = payload.get("servicios")
    if servicios is not None and isinstance(servicios, dict):
        tiene_permiso = bool(
            tipo_usuario == 2
            or servicios.get(settings.SERVICE_KEY, False)
            or servicios.get("cognijuegos", False)
        )
    else:
        tiene_permiso = True

    if not tiene_permiso:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: El usuario no tiene permisos habilitados para el servicio '{settings.SERVICE_KEY}'."
        )

    user_id = payload.get("id") or payload.get("sub")
    email = payload.get("email")

    db = get_database()
    query = {}
    if user_id:
        try:
            query["id"] = int(user_id)
        except (ValueError, TypeError):
            query["id"] = user_id
    elif email:
        query["email"] = email
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene una identidad de usuario válida.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = await db["usuarios"].find_one(query)
    if not user:
        # Sincronización automática de perfil local para compatibilidad de juegos y progreso
        try:
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            user_id_int = 0

        user = {
            "id": user_id_int,
            "name": payload.get("name") or payload.get("nombre") or "",
            "email": email or "",
            "codigo_acceso": payload.get("codigoAcceso") or "",
            "tipo_usuario": tipo_usuario,
            "black": bool(payload.get("black", False)),
            "activo": bool(payload.get("activo", True)),
            "date_start": datetime.now(timezone.utc),
            "date_end": None,
        }
        await db["usuarios"].update_one(
            {"id": user_id_int},
            {"$setOnInsert": user},
            upsert=True
        )
        user = await db["usuarios"].find_one({"id": user_id_int})

    if user.get("activo") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta de usuario se encuentra inactiva. Contacta al administrador."
        )

    return user


async def get_optional_user(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> Optional[Dict[str, Any]]:
    """
    Resuelve la sesión actual sin exigir autenticación obligatoria (ej. GET /api/auth/session).
    Si no hay credencial o el token expiró/es inválido (401), limpia la cookie vencida si existía
    y devuelve None para evitar falsos errores HTTP 401 en visitantes invitados.
    """
    try:
        return await get_current_user(request=request, credentials=credentials)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        if request and request.cookies.get("access_token"):
            clear_auth_cookie(response)
        return None


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Valida que el usuario autenticado tenga rol de Operador de Sistemas / Administrador (tipo_usuario == 2).
    """
    if current_user.get("tipo_usuario") != 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido: Se requieren permisos de Operador de Sistemas / Administrador."
        )
    return current_user
