import re
import urllib.parse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import logging

logger = logging.getLogger("SecurityDirective")

# Expresiones regulares para patrones sospechosos, sondas de exfiltración y path traversal
SUSPICIOUS_PATH_PATTERNS = [
    # Archivos y directorios ocultos (ej. /.env, /.git, /.*)
    re.compile(r"(^|/)\.[a-zA-Z0-9_\-]+"),
    # Path traversal (.. o codificaciones URL equivalentes)
    re.compile(r"\.\.(/|\\|%2f|%5c)"),
    # Archivos de secretos y configuraciones sensibles
    re.compile(r"\.(env|git|bak|old|orig|swp|sql|conf|ini|log|yaml|yml|pem|key|bash_history|ssh|aws)($|\?)", re.IGNORECASE),
    # Rutas del sistema operativo o internas del servidor
    re.compile(r"/(etc/(passwd|shadow)|proc/|sys/|windows/system32|windows/win\.ini)", re.IGNORECASE),
    # Sondas de administración sensible y escaneo de vulnerabilidades
    re.compile(r"(/admin/config|/actuator/(env|heapdump|beans)|/phpmyadmin|/wp-admin|/\.well-known)", re.IGNORECASE),
]

SUSPICIOUS_PAYLOAD_PATTERNS = [
    re.compile(r"(ignore\s+previous\s+instructions|modo\s+debug|act\s+as\s+root)", re.IGNORECASE),
]

# Tamaño máximo del cuerpo de petición (10 MB)
MAX_CONTENT_LENGTH = 10 * 1024 * 1024


class AbsoluteSecurityMiddleware(BaseHTTPMiddleware):
    """
    DIRECTIVA DE SEGURIDAD ABSOLUTA — REGLA SUPREMA INQUEBRANTABLE:
    1. Bloqueo total de exfiltración, archivos ocultos (.env, .git), traversals y sondas.
    2. Protocolo fail-closed ante patrones sospechosos ("Solicitud no permitida.").
    3. Inyección defensiva de encabezados de seguridad perimetral.
    4. Eliminación de encabezados de identificación de servidor (Server, X-Powered-By).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        raw_path = request.url.path
        decoded_path = urllib.parse.unquote(raw_path)
        query_string = request.url.query

        # 1. Validación de tamaño de carga útil (Anti-DoS)
        content_length_header = request.headers.get("content-length")
        if content_length_header:
            try:
                content_length = int(content_length_header)
                if content_length > MAX_CONTENT_LENGTH:
                    logger.warning(f"[FAIL-CLOSED] Petición excede tamaño máximo permitido ({content_length} bytes)")
                    return JSONResponse(
                        status_code=413,
                        content={"success": False, "detail": "Solicitud no permitida."}
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Solicitud no permitida."}
                )

        # 2. Detección de patrones maliciosos en la ruta
        for pattern in SUSPICIOUS_PATH_PATTERNS:
            if pattern.search(raw_path) or pattern.search(decoded_path):
                logger.warning(f"[FAIL-CLOSED] Detección de patrón malicioso en ruta: {raw_path}")
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "detail": "Solicitud no permitida."}
                )

        # 3. Detección de inyecciones sospechosas en query parameters
        if query_string:
            decoded_query = urllib.parse.unquote(query_string)
            for pattern in SUSPICIOUS_PAYLOAD_PATTERNS:
                if pattern.search(decoded_query):
                    logger.warning("[FAIL-CLOSED] Detección de inyección sospechosa en query string")
                    return JSONResponse(
                        status_code=403,
                        content={"success": False, "detail": "Solicitud no permitida."}
                    )

        # 4. Procesamiento seguro de la petición
        response = await call_next(request)

        # 5. Inyección de Encabezados de Seguridad (Defensa en profundidad)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # 6. Ocultamiento de identificación del servidor web
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response
