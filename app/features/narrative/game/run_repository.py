"""
run_repository.py
Persistencia de `narrative_runs` con control optimista de versión.

Cada escritura incrementa `version` y exige que la copia en memoria siga siendo la vigente.
Las partidas antiguas sin `version` se tratan como versión 0.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_RUNS,
    COLL_RUNS_ARCHIVE,
)
from app.features.narrative.game.identity import filtro_run

CONFLICTO_DETALLE = (
    "La partida fue modificada por otra petición. "
    "Recargá el estado actual antes de continuar."
)


class RunAlreadyExistsError(Exception):
    """Otra petición creó la misma generación de run antes de esta inserción."""

    def __init__(self, run_id: str):
        super().__init__(f"La partida '{run_id}' ya existe.")
        self.run_id = run_id


def _filtro_version(run: Dict[str, Any]) -> Dict[str, Any]:
    version = int(run.get("version") or 0)
    filtro: Dict[str, Any] = {"_id": run["_id"]}
    if version:
        filtro["version"] = version
    else:
        filtro["$or"] = [{"version": 0}, {"version": {"$exists": False}}]
    return filtro


def _proyectar(run: Dict[str, Any], campos: Optional[Iterable[str]]) -> Dict[str, Any]:
    if campos is None:
        return {k: v for k, v in run.items() if k not in ("_id", "version")}
    return {k: run[k] for k in campos if k in run}


async def crear_run(run: Dict[str, Any]) -> None:
    """Inserta una generación nueva; nunca reemplaza a la ganadora de una carrera."""
    run["version"] = 0
    run.setdefault("generation", 1)
    db = get_database()
    try:
        await db[COLL_RUNS].insert_one(run)
    except DuplicateKeyError as exc:
        raise RunAlreadyExistsError(run["_id"]) from exc


async def archivar_run(run: Dict[str, Any], expected_version: Optional[int] = None) -> None:
    """Mueve una generación a archivo y solo entonces libera su slot activo."""
    version = int(run.get("version") or 0)
    if expected_version is not None and version != expected_version:
        raise HTTPException(status_code=409, detail=CONFLICTO_DETALLE)

    db = get_database()
    archivado = dict(run)
    archivado.setdefault("generation", 1)
    archivado["archived_at"] = datetime.now(timezone.utc).isoformat()
    await db[COLL_RUNS_ARCHIVE].replace_one({"_id": run["_id"]}, archivado, upsert=True)

    resultado = await db[COLL_RUNS].delete_one(_filtro_version(run))
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=409, detail=CONFLICTO_DETALLE)


async def persistir_run(
    run: Dict[str, Any],
    campos: Optional[Iterable[str]] = None
) -> None:
    """Guarda la partida y sube la versión; 409 si otra escritura se adelantó."""
    db = get_database()
    version_actual = int(run.get("version") or 0)
    cambios = _proyectar(run, campos)
    if "version" in cambios:
        cambios.pop("version")

    resultado = await db[COLL_RUNS].update_one(
        _filtro_version(run),
        {"$set": cambios, "$inc": {"version": 1}},
    )
    if resultado.matched_count == 0:
        raise HTTPException(status_code=409, detail=CONFLICTO_DETALLE)

    run["version"] = version_actual + 1


async def obtener_run_activo(run_id: str) -> Optional[Dict[str, Any]]:
    return await get_database()[COLL_RUNS].find_one({"_id": run_id})


async def obtener_run_activo_o_404(
    user_id: int,
    date: str,
    *,
    db=None,
    detail: str = "Partida no encontrada.",
) -> Dict[str, Any]:
    """Recupera la partida activa del usuario para la fecha o lanza HTTP 404."""
    database = db if db is not None else get_database()
    run = await database[COLL_RUNS].find_one(filtro_run(user_id, date))
    if not run:
        raise HTTPException(status_code=404, detail=detail)
    return run


async def obtener_run_por_id(run_id: str) -> Optional[Dict[str, Any]]:
    """Lectura de recuperación: activo primero, archivo después."""
    run = await obtener_run_activo(run_id)
    if run is not None:
        return run
    return await get_database()[COLL_RUNS_ARCHIVE].find_one({"_id": run_id})
