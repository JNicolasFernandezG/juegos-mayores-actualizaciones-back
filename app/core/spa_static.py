"""Servicio estático para SPA del panel de administración con fallback a index.html."""

import os

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings


class SPAStaticFiles(StaticFiles):
    """Sirve el build del panel y delega las rutas del cliente a index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Un asset faltante es un 404 real; solo las rutas del cliente caen al index.
            if exc.status_code != 404 or os.path.splitext(path)[1]:
                raise
            return await self._index(scope)

    async def _index(self, scope):
        try:
            return await super().get_response("index.html", scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            # Sin build disponible se conserva el comportamiento previo: derivar al Autenticador.
            return RedirectResponse(url=f"{settings.AUTH_SERVICE_URL.rstrip('/')}/")
