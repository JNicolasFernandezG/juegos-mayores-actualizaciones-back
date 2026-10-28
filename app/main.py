import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.security_middleware import AbsoluteSecurityMiddleware
from app.scripts.init_db import seed_estados_usuario
from app.features.auth.router import router as auth_router
from app.features.usuario.router import router as usuario_router
from app.features.progreso.router import router as progreso_router
from app.features.daily_challenges.router import router as daily_challenges_router
from app.features.user_attempts.router import router as user_attempts_router
from app.features.narrative.game.router import (
    router as narrative_router,
    router_v2 as narrative_v2_router
)
from app.features.narrative.admin.router import router as narrative_admin_router
from app.features.sso.router import router as sso_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("AppMain")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Conectar a MongoDB, inicializar índices y catálogo esencial de estados de usuario
    logger.info("Iniciando aplicación Mayores Actualizaciones (FastAPI)...")
    await connect_to_mongo()
    await seed_estados_usuario()
    logger.info(f"Servidor listo en el puerto {settings.PORT}.")
    yield
    # Shutdown: Cerrar conexiones limpiamente
    logger.info("Deteniendo aplicación y cerrando conexiones...")
    await close_mongo_connection()

app = FastAPI(
    title="Mayores Actualizaciones API",
    description="Backend en FastAPI + MongoDB para la plataforma educativa de adultos mayores",
    version="2.0.0",
    docs_url=None,       # Desactivado en endpoints públicos para evitar sondeo de esquemas
    redoc_url=None,      # Desactivado para evitar sondeo de documentación
    openapi_url=None,    # Desactivado en producción según directiva de seguridad
    lifespan=lifespan
)

# DIRECTIVA DE SEGURIDAD ABSOLUTA — REGLA SUPREMA INQUEBRANTABLE (Middleware perimetral y fail-closed)
app.add_middleware(AbsoluteSecurityMiddleware)

# Configuración de CORS estricta (Solo orígenes autorizados)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Manejador de excepciones HTTP estándar con sanitización de información
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "detail": exc.detail,
            "message": msg
        }
    )

# DIRECTIVA DE SEGURIDAD ABSOLUTA (FAIL-CLOSED):
# Interceptor global para excepciones no controladas. Nunca expone stack traces ni detalles del servidor.
@app.exception_handler(Exception)
async def global_fail_closed_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error interno no controlado en {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "detail": "Solicitud no permitida."
        }
    )

# Inclusión de routers esenciales (Auth, Usuarios, Progreso de Cursos, Desafíos, Narrativo, SSO)
app.include_router(auth_router)
app.include_router(usuario_router)
app.include_router(progreso_router)
app.include_router(daily_challenges_router)
app.include_router(user_attempts_router)
app.include_router(narrative_router)
app.include_router(narrative_v2_router)
app.include_router(narrative_admin_router)
app.include_router(sso_router)

@app.get("/", tags=["Estado"])
async def root():
    return {
        "status": "online",
        "service": "Mayores Actualizaciones API (FastAPI + MongoDB)",
        "version": "2.0.0"
    }

@app.get("/health", tags=["Estado"])
@app.get("/actuator/health", tags=["Estado"])
async def health_check():
    return {"status": "UP"}

# Redirección de administración hacia el Autenticador Central (Única fuente de verdad de usuarios)
@app.get("/admin", include_in_schema=False)
@app.get("/admin/{path:path}", include_in_schema=False)
async def admin_redirect(path: str = ""):
    return RedirectResponse(url=f"{settings.AUTH_SERVICE_URL.rstrip('/')}/")

# Montar carpeta de assets estáticos de narrativa (universos, personajes, cartas, eventos, etc.)
static_narrative_dir = os.path.join(os.path.dirname(__file__), "static", "narrative")
os.makedirs(static_narrative_dir, exist_ok=True)
static_personajes_dir = os.path.join(static_narrative_dir, "personajes")
os.makedirs(static_personajes_dir, exist_ok=True)
app.mount("/assets/narrative/characters", StaticFiles(directory=static_personajes_dir), name="narrative_characters_alias")
app.mount("/assets/narrative", StaticFiles(directory=static_narrative_dir), name="narrative_assets")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
