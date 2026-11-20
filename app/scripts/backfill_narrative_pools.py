"""
Backfill y refresh de los mazos de eventos narrativos.

Rellena `config.pool_eventos_disponibles_ids` en los `daily_challenges` de
narrativo generados antes de la integración, replicando la secuencia
determinista del generador actual: misma semilla diaria, mismas extracciones
de personajes/cartas y catálogo ordenado por `_id`. Solo escribe ese campo:
no toca el resto del challenge, ni las runs activas o archivadas.

Con `--refresh-outdated` recalcula también los desafíos que ya declaran un mazo
pero quedaron desactualizados respecto del catálogo vigente (por ejemplo, al
sumar eventos nuevos): conserva la misma semilla diaria y solo reescribe los
que cambian.

Por defecto corre en seco. Para escribir hay que pasar `--apply` y `--expect-db`
con el nombre exacto de la base, de modo que no se pueda apuntar al entorno
equivocado por accidente.

Uso:
    python -m app.scripts.backfill_narrative_pools
    python -m app.scripts.backfill_narrative_pools --apply --expect-db mayores_actualizaciones_dev
    python -m app.scripts.backfill_narrative_pools --refresh-outdated
    python -m app.scripts.backfill_narrative_pools --refresh-outdated --apply --expect-db mayores_actualizaciones_dev
"""

import argparse
import asyncio
import random
import sys
from collections import defaultdict
from datetime import date as date_cls, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.database import close_mongo_connection, get_database
from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CHALLENGES,
    COLL_CHARACTERS,
    COLL_V2_EVENTS,
)
from app.features.narrative.game.event_cycle import seleccionar_ciclo_eventos_diario

GAME_ID = "narrativo"
POOL_FIELD = "config.pool_eventos_disponibles_ids"


def _rango_fechas(desde: Optional[str], hasta: Optional[str]) -> Optional[Dict[str, str]]:
    if not desde and not hasta:
        return None
    rango: Dict[str, str] = {}
    if desde:
        rango["$gte"] = desde
    if hasta:
        rango["$lte"] = hasta
    return rango


def falta_pool_query(*, desde: Optional[str] = None, hasta: Optional[str] = None) -> Dict[str, Any]:
    """Desafíos de narrativo sin mazo anunciado (campo ausente, nulo o vacío)."""
    query: Dict[str, Any] = {
        "game_id": GAME_ID,
        "$or": [
            {POOL_FIELD: {"$exists": False}},
            {POOL_FIELD: None},
            {POOL_FIELD: []},
        ],
    }
    rango = _rango_fechas(desde, hasta)
    if rango:
        query["date"] = rango
    return query


def refresh_pool_query(*, desde: Optional[str] = None, hasta: Optional[str] = None) -> Dict[str, Any]:
    """Desafíos que ya declaran un mazo, para recalcularlo con el catálogo actual."""
    query: Dict[str, Any] = {"game_id": GAME_ID, POOL_FIELD: {"$exists": True, "$ne": None}}
    rango = _rango_fechas(desde, hasta)
    if rango:
        query["date"] = rango
    return query


def pool_requiere_actualizacion(actual: Any, calculado: Any) -> bool:
    return list(actual or []) != list(calculado or [])


def calcular_pool_del_dia(
    universo_id: str,
    date_str: str,
    pj_ids: List[Any],
    carta_ids: List[Any],
    eventos: List[Dict[str, Any]],
) -> List[str]:
    """
    Replica `generar_mes_narrativo`: las dos extracciones previas consumen el RNG
    aunque su resultado no se use acá, porque el mazo depende de ese estado.
    """
    rng = random.Random(f"narrativo_{universo_id}_{date_str}")
    rng.sample(pj_ids, 5)
    rng.sample(carta_ids, 5)
    return seleccionar_ciclo_eventos_diario(eventos, rng)


def _date_str(valor: Any) -> Optional[str]:
    if isinstance(valor, str) and valor:
        return valor[:10]
    if isinstance(valor, (datetime, date_cls)):
        return valor.strftime("%Y-%m-%d")
    return None


def _uri_segura(url: str) -> str:
    if "@" not in url:
        return url
    pre, post = url.split("@", 1)
    return f"{pre.split('://')[0]}://****:****@{post}"


def _host_de(url: str) -> str:
    try:
        return urlsplit(url).netloc.rsplit("@", 1)[-1] or "?"
    except ValueError:
        return "?"


async def _cargar_catalogo(db: Any, universo_id: str) -> Tuple[List[Any], List[Any], List[Dict[str, Any]]]:
    """Mismo orden y filtros que el generador, para que la semilla caiga igual."""
    pjs = await db[COLL_CHARACTERS].find({"universo_id": universo_id}).sort("_id", 1).to_list(None)
    cartas = await db[COLL_CARDS].find({"universo_id": universo_id}).sort("_id", 1).to_list(None)
    eventos = await db[COLL_V2_EVENTS].find({"universo_id": universo_id}).sort("_id", 1).to_list(None)
    return pjs, cartas, eventos


async def backfill(
    *,
    aplicar: bool,
    expect_db: Optional[str],
    desde: Optional[str],
    hasta: Optional[str],
    permitir_test: bool,
    muestras: int,
    refrescar: bool = False,
) -> int:
    db = get_database()
    db_name = db.name
    uri = settings.mongodb_connection_url

    print(f"Base: {db_name} | Host: {_host_de(uri)} | URI: {_uri_segura(uri)}")
    modo = "REFRESH" if refrescar else "BACKFILL"
    print(f"Modo: {modo} |", "APLICAR CAMBIOS" if aplicar else "DRY-RUN (sin escrituras)")

    if "test" in db_name.lower() and not permitir_test:
        print("Rechazado: la base parece de tests. Usá --allow-test-db si es intencional.", file=sys.stderr)
        return 2
    if aplicar and expect_db != db_name:
        print(
            f"Rechazado: --apply exige --expect-db {db_name!r} (recibido: {expect_db!r}).",
            file=sys.stderr,
        )
        return 2

    consulta = refresh_pool_query(desde=desde, hasta=hasta) if refrescar else falta_pool_query(desde=desde, hasta=hasta)
    pendientes = (
        await db[COLL_CHALLENGES]
        .find(consulta, {"date": 1, "config": 1, "universo_id": 1})
        .sort("date", 1)
        .to_list(None)
    )
    if refrescar:
        print(f"Desafíos con mazo a recalcular: {len(pendientes)}")
    else:
        print(f"Desafíos sin mazo: {len(pendientes)}")

    por_universo: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    sin_universo = 0
    sin_fecha = 0
    for doc in pendientes:
        cfg = doc.get("config") or {}
        universo_id = cfg.get("universo_id") or doc.get("universo_id")
        if not universo_id:
            sin_universo += 1
            continue
        if not _date_str(doc.get("date")):
            sin_fecha += 1
            continue
        por_universo[str(universo_id)].append(doc)

    if sin_universo or sin_fecha:
        print(f"Omitidos por datos incompletos: sin universo={sin_universo}, sin fecha válida={sin_fecha}")

    planificados = 0
    escritos = 0
    ya_tenian = 0
    sin_cambios = 0
    vacios = 0
    errores = 0

    for universo_id, docs in sorted(por_universo.items()):
        pjs, cartas, eventos = await _cargar_catalogo(db, universo_id)
        if len(pjs) < 5 or len(cartas) < 5:
            print(
                f"[{universo_id}] omitido: {len(pjs)} personajes y {len(cartas)} cartas "
                f"(el generador exige 5 de cada uno); afecta a {len(docs)} desafíos"
            )
            continue
        if not eventos:
            print(f"[{universo_id}] omitido: sin eventos V2; afecta a {len(docs)} desafíos")
            continue

        pj_ids = [p["_id"] for p in pjs]
        carta_ids = [c["_id"] for c in cartas]
        print(f"[{universo_id}] {len(docs)} desafíos, {len(eventos)} eventos en catálogo")

        for doc in docs:
            date_str = _date_str(doc.get("date"))
            actual = (doc.get("config") or {}).get("pool_eventos_disponibles_ids")
            if not refrescar and actual:
                ya_tenian += 1
                continue

            pool = calcular_pool_del_dia(universo_id, date_str, pj_ids, carta_ids, eventos)
            planificados += 1

            if not pool:
                vacios += 1
                print(f"  {date_str}: mazo vacío, se omite")
                continue
            if refrescar and not pool_requiere_actualizacion(actual, pool):
                sin_cambios += 1
                continue
            if planificados <= muestras:
                print(f"  {date_str}: {len(pool)} eventos")

            if not aplicar:
                continue

            try:
                if refrescar:
                    filtro: Dict[str, Any] = {"_id": doc["_id"], POOL_FIELD: actual}
                else:
                    filtro = {
                        "_id": doc["_id"],
                        "$or": [
                            {POOL_FIELD: {"$exists": False}},
                            {POOL_FIELD: None},
                            {POOL_FIELD: []},
                        ],
                    }
                res = await db[COLL_CHALLENGES].update_one(filtro, {"$set": {POOL_FIELD: pool}})
                if res.modified_count:
                    escritos += 1
                elif refrescar:
                    sin_cambios += 1
                else:
                    ya_tenian += 1
            except Exception as exc:  # noqa: BLE001 - el resumen debe seguir ante un doc roto
                errores += 1
                print(f"  {date_str}: error al escribir ({exc})", file=sys.stderr)

    restantes = await db[COLL_CHALLENGES].count_documents(falta_pool_query(desde=desde, hasta=hasta))
    print("--- Resumen ---")
    print(f"Mazos calculados: {planificados}")
    if refrescar:
        print(f"Actualizados: {escritos} | sin cambios: {sin_cambios} | errores: {errores}")
    elif aplicar:
        print(f"Escritos: {escritos} | ya tenían mazo (carrera): {ya_tenian} | errores: {errores}")
    print(f"Mazos vacíos omitidos: {vacios}")
    print(f"Desafíos que siguen sin mazo: {restantes}")
    return 1 if errores else 0


async def _main(args: argparse.Namespace) -> int:
    try:
        return await backfill(
            aplicar=args.apply,
            expect_db=args.expect_db,
            desde=args.from_date,
            hasta=args.to_date,
            permitir_test=args.allow_test_db,
            muestras=args.show,
            refrescar=args.refresh_outdated,
        )
    finally:
        await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Escribe los mazos calculados (por defecto solo simula).")
    parser.add_argument("--expect-db", metavar="NOMBRE", help="Obligatorio con --apply: nombre exacto de la base a modificar.")
    parser.add_argument("--from-date", metavar="YYYY-MM-DD", help="Solo desafíos desde esta fecha.")
    parser.add_argument("--to-date", metavar="YYYY-MM-DD", help="Solo desafíos hasta esta fecha.")
    parser.add_argument("--allow-test-db", action="store_true", help="Permite una base cuyo nombre contenga 'test'.")
    parser.add_argument(
        "--refresh-outdated",
        action="store_true",
        help="Recalcula también los desafíos que ya tienen mazo y solo reescribe los que cambian.",
    )
    parser.add_argument("--show", type=int, default=5, metavar="N", help="Cuántos mazos de ejemplo mostrar (default 5).")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
