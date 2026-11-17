"""Ciclo de vida (startup/shutdown), siembra inicial y tareas periódicas en segundo plano."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.features.daily_challenges.service import ensure_current_and_next_month_generated
from app.scripts.seed_challenges import seed_wordle_challenges
from app.scripts.seed_sopa_letras import seed_sopa_letras_challenges
from app.scripts.seed_sudoku import seed_sudoku_challenges

logger = logging.getLogger("AppMain")


async def _generar_desafios_si_falta(autogen_lock: asyncio.Lock) -> None:
    # Serializa arranque y ciclo periódico: dos corridas superpuestas multiplican las ráfagas a la RAE.
    async with autogen_lock:
        await ensure_current_and_next_month_generated()


async def _seed_static_challenges() -> None:
    if not settings.SEED_STATIC_CHALLENGES:
        return
    try:
        await seed_wordle_challenges()
        await seed_sopa_letras_challenges()
        await seed_sudoku_challenges()
    except Exception as e_static:
        logger.warning(f"Aviso durante la siembra estática de desafíos: {e_static}")


async def _seed_narrative_universe() -> None:
    try:
        from app.features.narrative.constants import COLL_CARDS, COLL_CHARACTERS, COLL_SETTINGS

        db = get_database()
        # El arranque solo asegura el universo base. Personajes y cartas los
        # opera el admin: sembrarlos en cada deploy pisaba la carga real.
        if await db[COLL_SETTINGS].count_documents({"_id": "corte_medieval"}) == 0:
            from app.scripts.seed_narrative import seed_universo_narrativo

            await seed_universo_narrativo()
        else:
            # V1 está retirado: un universo heredado con motor v1 dejaría la
            # partida sin endpoints de grafo. Solo corregimos el universo base.
            motor = await db[COLL_SETTINGS].update_many(
                {"_id": "corte_medieval", "motor": {"$nin": ["v2"]}},
                {"$set": {"motor": "v2"}},
            )
            reciclaje = await db[COLL_SETTINGS].update_many(
                {"_id": "corte_medieval", "reciclaje_eventos_v2": {"$exists": False}},
                {"$set": {"reciclaje_eventos_v2": True}},
            )
            if motor.modified_count or reciclaje.modified_count:
                logger.info("[NARRATIVE SEED] Universo base migrado a motor v2.")

        faltantes = [
            nombre
            for nombre, coleccion in (("personajes", COLL_CHARACTERS), ("cartas", COLL_CARDS))
            if await db[coleccion].count_documents({}) == 0
        ]
        if faltantes:
            logger.warning(
                "[NARRATIVE SEED] Catálogo sin %s. Cargalo desde /admin o corré "
                "python -m app.scripts.seed_narrative en una base vacía.",
                " ni ".join(faltantes),
            )
    except Exception as e_seed:
        logger.warning(f"Aviso durante la siembra del universo narrativo: {e_seed}")


async def _seed_narrative_v2_graphs(app: FastAPI) -> None:
    try:
        from app.features.narrative.constants import COLL_V2_EVENTS
        from app.scripts.seed_narrative_v2_graphs import seed_v2_graphs

        db = get_database()
        # Insert-only ($setOnInsert por _id): cada arranque restaura los grafos
        # que falten y nunca pisa ediciones del admin.
        await seed_v2_graphs()
        total_eventos_v2 = await db[COLL_V2_EVENTS].count_documents({})
        if total_eventos_v2 == 0:
            logger.warning("[NARRATIVE V2 SEED] La base quedó sin eventos V2 tras la siembra.")
        else:
            logger.info(f"[NARRATIVE V2 SEED] Eventos V2 disponibles: {total_eventos_v2}")
        app.state.seed_v2_status = f"ok: {total_eventos_v2} eventos"
    except Exception as e_seed_v2:
        logger.warning(f"Aviso durante la siembra de grafos V2: {e_seed_v2}")
        app.state.seed_v2_status = f"error: {type(e_seed_v2).__name__}: {e_seed_v2}"


async def _seed_post_graph_catalogs() -> None:
    try:
        from app.scripts.seed_narrative_tags import seed_narrative_catalogs

        resumen_catalogos = await seed_narrative_catalogs()
        logger.info(f"Catálogos narrativos verificados: {resumen_catalogos}")
    except Exception as e_cat:
        logger.warning(f"Aviso durante la siembra del catálogo de tags/acciones: {e_cat}")

    try:
        # Solo con la colección vacía: el admin puede editar, ordenar o borrar sin que el arranque lo revierta.
        from app.features.profile.consejos import asegurar_consejos_default

        sembrados = await asegurar_consejos_default()
        if sembrados:
            logger.info(f"[PERFIL SEED] Consejos base sembrados: {sembrados}")
    except Exception as e_consejos:
        logger.warning(f"Aviso durante la siembra de consejos del perfil: {e_consejos}")

    try:
        from app.features.narrative.admin.challenge_service import sembrar_finalizaciones_default

        await sembrar_finalizaciones_default()
    except Exception as e_fin:
        logger.warning(f"Aviso al sembrar finalizaciones por defecto: {e_fin}")


async def _run_initial_seeds(app: FastAPI, autogen_lock: asyncio.Lock) -> None:
    try:
        await _seed_static_challenges()
        await _seed_narrative_universe()
        await _seed_narrative_v2_graphs(app)
        # Los desafíos narrativos se arman con los pools de grafos: generarlos
        # después del seed evita sobrescribir el mes con pools vacíos.
        await _generar_desafios_si_falta(autogen_lock)
        await _seed_post_graph_catalogs()
    except Exception as e:
        logger.warning(f"Aviso durante la siembra inicial en segundo plano: {e}")


async def _background_seeds(app: FastAPI, autogen_lock: asyncio.Lock) -> None:
    await _run_initial_seeds(app, autogen_lock)
    while True:
        try:
            await asyncio.sleep(43200)
            await _generar_desafios_si_falta(autogen_lock)
        except Exception as e_loop:
            logger.warning(f"Error en ciclo periódico de desafíos: {e_loop}")


async def _ledger_reconciler() -> None:
    from app.shared.ledger import reconcile_pending_ledger

    while True:
        try:
            await reconcile_pending_ledger()
        except Exception as e_ledger:
            logger.warning(f"Error al reconciliar asientos del ledger: {e_ledger}")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: conecta a MongoDB y lanza semillas y reconciliador en segundo plano."""
    logger.info("Iniciando aplicación Mayores Actualizaciones (FastAPI)...")
    await connect_to_mongo()
    autogen_lock = asyncio.Lock()
    app.state.seed_v2_status = "pendiente"

    asyncio.create_task(_background_seeds(app, autogen_lock))
    asyncio.create_task(_ledger_reconciler())

    logger.info(f"Servidor listo en el puerto {settings.PORT}.")
    yield
    logger.info("Deteniendo aplicación y cerrando conexiones...")
    await close_mongo_connection()
