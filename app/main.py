import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import get_database  # noqa: F401
from app.core.lifespan import lifespan
from app.core.rate_limit import RateLimitMiddleware
from app.core.security_middleware import AbsoluteSecurityMiddleware
from app.core.spa_static import SPAStaticFiles
from app.features.auth.router import router as auth_router
from app.features.daily_challenges.crucigrama_admin.router import router as crucigrama_admin_router
from app.features.daily_challenges.router import router as daily_challenges_router
from app.features.economy.router import router as economy_router
from app.features.narrative.admin.router import router as narrative_admin_router
from app.features.narrative.game.router import router as narrative_router, router_v2 as narrative_v2_router
from app.features.profile.router import admin_router as profile_admin_router, router as profile_router
from app.features.sso.router import router as sso_router
from app.features.subscriptions.router import admin_router as subscriptions_admin_router, router as subscriptions_router
from app.features.user_attempts.router import router as user_attempts_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("AppMain")

openapi_tags = [
    {"name": "Estado"},
    {"name": "Autenticación"},
    {"name": "Autenticación - SSO"},
    {"name": "Desafíos Diarios"},
    {"name": "Desafíos Diarios - Administración de Crucigramas"},
    {"name": "Partidas e Intentos de Usuarios"},
    {"name": "Economía, Vidas y Mini-Tienda"},
    {"name": "Perfil"},
    {"name": "Perfil - Administración"},
    {"name": "Suscripciones"},
    {"name": "Suscripciones - Administración"},
    {"name": "Narrativo - Flujo de Juego"},
    {"name": "Narrativo - Administración"},
    {"name": "Narrativo - CRUD Universos"},
    {"name": "Narrativo - CRUD Personajes"},
    {"name": "Narrativo - CRUD Cartas"},
    {"name": "Narrativo - CRUD Finalizaciones"},
    {"name": "Narrativo - CRUD Eventos V2"},
    {"name": "Narrativo - CRUD Conversaciones V2"},
    {"name": "Narrativo - CRUD Eventos Especiales V2"},
    {"name": "Narrativo - CRUD Tags"},
]

app = FastAPI(
    title="Mayores Actualizaciones API",
    description="Backend en FastAPI + MongoDB para la plataforma educativa de adultos mayores",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)

# DIRECTIVA DE SEGURIDAD ABSOLUTA — REGLA SUPREMA INQUEBRANTABLE (Middleware perimetral y fail-closed)
app.add_middleware(AbsoluteSecurityMiddleware)

# Límite de solicitudes por identidad en economía, intentos y narrativo
app.add_middleware(RateLimitMiddleware)

# Configuración de CORS estricta (Solo orígenes autorizados)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Guest-Credential"],
)


# Manejador de excepciones HTTP estándar con sanitización de información
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.detail, "message": msg},
    )


# DIRECTIVA DE SEGURIDAD ABSOLUTA (FAIL-CLOSED):
# Interceptor global para excepciones no controladas. Nunca expone stack traces ni detalles del servidor.
@app.exception_handler(Exception)
async def global_fail_closed_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error interno no controlado en {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"success": False, "detail": "Solicitud no permitida."})


# Inclusión de routers esenciales (Auth, Desafíos, Narrativo, Economía, SSO)
for _router in (
    auth_router,
    daily_challenges_router,
    crucigrama_admin_router,
    user_attempts_router,
    economy_router,
    profile_router,
    profile_admin_router,
    subscriptions_router,
    subscriptions_admin_router,
    narrative_router,
    narrative_v2_router,
    narrative_admin_router,
    sso_router,
):
    app.include_router(_router)


@app.get("/", tags=["Estado"])
async def root():
    return {"status": "online", "service": "Mayores Actualizaciones API (FastAPI + MongoDB)", "version": "2.0.0"}


@app.get("/health", tags=["Estado"])
@app.get("/actuator/health", tags=["Estado"])
async def health_check():
    return {"status": "UP"}


@app.get("/demo-narrativo", include_in_schema=False)
async def demo_narrativo():
    """Demo HTML autocontenida que recorre el flujo real del narrativo V2."""
    demo_path = os.path.join(os.path.dirname(__file__), "static", "demo-narrativo.html")
    if not os.path.exists(demo_path):
        return JSONResponse(status_code=404, content={"detail": "Demo no disponible."})
    return FileResponse(demo_path, media_type="text/html")


# Panel de administración: SPA compilada desde frontend/admin_src con base /admin/.
static_admin_dir = os.path.join(os.path.dirname(__file__), "static", "admin")
os.makedirs(static_admin_dir, exist_ok=True)


@app.get("/admin", include_in_schema=False)
async def admin_panel():
    index_path = os.path.join(static_admin_dir, "index.html")
    if not os.path.exists(index_path):
        return RedirectResponse(url=f"{settings.AUTH_SERVICE_URL.rstrip('/')}/")
    return FileResponse(index_path)


app.mount("/admin", SPAStaticFiles(directory=static_admin_dir, html=True), name="admin")

# Montar carpeta de assets estáticos de narrativa (universos, personajes, cartas, eventos, etc.)
static_narrative_dir = os.path.join(os.path.dirname(__file__), "static", "narrative")
os.makedirs(static_narrative_dir, exist_ok=True)

# Alias en inglés para compatibilidad con semillas históricas y colecciones existentes
NARRATIVE_CATEGORY_ALIASES = {
    "characters": "personajes", "conversations": "conversaciones", "events": "eventos",
    "cards": "cartas", "results": "resultados", "endings": "finalizaciones", "universes": "universos",
}
for alias, real_folder in NARRATIVE_CATEGORY_ALIASES.items():
    real_path = os.path.join(static_narrative_dir, real_folder)
    os.makedirs(real_path, exist_ok=True)
    app.mount(f"/assets/narrative/{alias}", StaticFiles(directory=real_path), name=f"narrative_{alias}_alias")

app.mount("/assets/narrative", StaticFiles(directory=static_narrative_dir), name="narrative_assets")

if __name__ == "__main__":
    import uvicorn

    # app/data guarda la caché RAE que se reescribe durante la generación; los estáticos por el build del admin.
    app_dir = os.path.dirname(os.path.abspath(__file__))
    uvicorn.run(
        "app.main:app", host=settings.HOST, port=settings.PORT, reload=True, reload_dirs=[app_dir],
        reload_excludes=[os.path.join(app_dir, "data"), os.path.join(app_dir, "static"), "*.log"],
    )
