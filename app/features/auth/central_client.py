"""Cliente HTTP compartido para delegar operaciones al microservicio central de autenticación."""

import logging
from typing import Any, Callable, Dict, Optional, Protocol

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class _AsyncHttpClient(Protocol):
    async def __aenter__(self) -> "_AsyncHttpClient": ...
    async def __aexit__(self, *args: object) -> object: ...
    async def post(self, url: str, **kwargs: object) -> httpx.Response: ...


def _extract_error_detail(resp: httpx.Response, default_error: str) -> Any:
    """Extrae el campo `detail` de una respuesta JSON de error o devuelve `default_error`."""
    try:
        err_data = resp.json()
    except (ValueError, TypeError, AttributeError) as exc:
        logger.debug("Respuesta de error no JSON del Autenticador (%s): %s", resp.status_code, exc)
        return default_error
    if isinstance(err_data, dict) and "detail" in err_data:
        return err_data["detail"]
    return default_error


async def post_to_auth_service(
    endpoint: str,
    payload: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    default_error: str = "Error en el servicio de autenticación central",
    unavailable_prefix: str = "Servicio de autenticación central no disponible",
    client_cls: Callable[..., _AsyncHttpClient] = httpx.AsyncClient,
    fixed_error_status: Optional[int] = None,
    base_url: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Envía un POST al Autenticador Central y traduce fallos de red o HTTP a HTTPException."""
    raw_base = base_url if base_url is not None else settings.AUTH_SERVICE_URL
    auth_url = f"{raw_base.rstrip('/')}/{endpoint.lstrip('/')}"
    post_kwargs: Dict[str, Any] = {"json": payload}
    if headers is not None:
        post_kwargs["headers"] = headers

    try:
        async with client_cls(timeout=timeout) as client:
            resp = await client.post(auth_url, **post_kwargs)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{unavailable_prefix} ({raw_base}): {str(exc)}",
        ) from exc

    if resp.status_code != 200:
        if fixed_error_status is not None:
            raise HTTPException(status_code=fixed_error_status, detail=default_error)
        raise HTTPException(
            status_code=resp.status_code,
            detail=_extract_error_detail(resp, default_error),
        )

    data = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de autenticación central",
        )
    return data
