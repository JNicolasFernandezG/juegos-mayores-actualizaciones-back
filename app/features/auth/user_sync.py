"""Normalización, sincronización local en MongoDB y formateo de usuarios autenticados."""

from datetime import date, datetime, timezone
from typing import Any, Dict, Mapping

from app.core.database import get_database

_ESTADO_CODIGOS = {1: "PENDIENTE_VERIFICACION", 2: "ACTIVO"}


def _extract_first(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        val = data.get(key)
        if val not in (None, ""):
            return val
    return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in ("true", "1", "yes", "si", "sí"):
            return True
        if norm in ("false", "0", "no", ""):
            return False
    return bool(value)


def _normalize_role(remote_user: Mapping[str, Any], default: int = 1) -> int:
    raw = _extract_first(remote_user, "tipoUsuario", "tipo_usuario")
    if raw is None:
        return default
    try:
        return int(raw) or default
    except (TypeError, ValueError):
        return default


def format_user_response(user: dict, include_access_code: bool = True) -> dict:
    """Formatea el documento de MongoDB al contrato JSON esperado por el frontend."""
    date_start = user.get("date_start")
    if isinstance(date_start, datetime):
        date_start_str = date_start.strftime("%Y-%m-%dT%H:%M:%S")
    elif isinstance(date_start, date):
        date_start_str = date_start.strftime("%Y-%m-%dT00:00:00")
    else:
        date_start_str = date_start

    date_end = user.get("date_end")
    date_end_str = (
        date_end.strftime("%Y-%m-%d") if isinstance(date_end, (datetime, date)) else date_end
    )

    estado_id = user.get("estado_id", 2 if user.get("activo", True) else 3)
    estado_codigo = user.get("estado_codigo") or _ESTADO_CODIGOS.get(estado_id, "SUSPENDIDO")

    payload: Dict[str, Any] = {
        "id": user.get("id"),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "tipoUsuario": user.get("tipo_usuario", 1),
        "black": bool(user.get("black", False)),
        "activo": bool(user.get("activo", True)),
        "estadoId": estado_id,
        "estadoCodigo": estado_codigo,
        "dateStart": date_start_str,
        "dateEnd": date_end_str,
    }
    if include_access_code:
        payload["codigoAcceso"] = user.get("codigo_acceso", "")
    return payload


async def sync_local_user_from_auth_service(remote_user: dict) -> dict:
    """Sincroniza o crea el usuario en MongoDB mediante upsert atómico por ``id``."""
    if not remote_user:
        return {}

    db = get_database()
    user_id = int(remote_user["id"])
    email = str(remote_user.get("email") or "").lower().strip()
    estado_id = int(_extract_first(remote_user, "estadoId", "estado_id", default=2) or 2)
    update_fields = {
        "id": user_id,
        "name": _extract_first(remote_user, "name", "nombre", default=""),
        "email": email,
        "codigo_acceso": _extract_first(remote_user, "codigoAcceso", "codigo_acceso", default=""),
        "tipo_usuario": _normalize_role(remote_user),
        "black": _to_bool(remote_user.get("black"), default=False),
        "activo": _to_bool(remote_user.get("activo"), default=True),
        "estado_id": estado_id,
        "estado_codigo": _extract_first(
            remote_user, "estadoCodigo", "estado_codigo", default="ACTIVO"
        ),
    }

    if email:
        await db["usuarios"].delete_many({"email": email, "id": {"$ne": user_id}})

    await db["usuarios"].update_one(
        {"id": user_id},
        {
            "$set": update_fields,
            "$setOnInsert": {"date_start": datetime.now(timezone.utc), "date_end": None, "puntos": 0},
        },
        upsert=True,
    )

    return await db["usuarios"].find_one({"id": user_id}) or {}
