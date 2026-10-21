# ==============================================================================
# Etapa 1: Builder (Instalación de dependencias y compilación de wheels)
# ==============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# ==============================================================================
# Etapa 2: Runtime (Imagen final ligera y endurecida con usuario no-root)
# ==============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Variables de entorno dinámicas por defecto
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8087 \
    HOST=0.0.0.0

# Crear grupo y usuario sin privilegios (no-root)
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/false --create-home appuser

# Instalar dependencias compiladas desde la etapa builder
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copiar el código fuente asignando permisos al usuario no-root
COPY --chown=appuser:appgroup . .

# Asegurar que existan los directorios estáticos requeridos por FastAPI
RUN mkdir -p /app/app/static/admin /app/app/static/narrative/personajes && \
    chown -R appuser:appgroup /app

# Cambiar a usuario no-root por seguridad
USER appuser

EXPOSE 8087

# Iniciar Uvicorn leyendo dinámicamente HOST y PORT
CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8087}"]

