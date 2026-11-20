"""
Expande el catálogo narrativo V2 (`corte_medieval`) sin pisar contenido existente.

Inserta, con `$setOnInsert`:
- los 24 eventos adicionales (12 propios `_v2d` + 12 importados `_v2c`);
- las 10 cartas nuevas;
- los 5 personajes nuevos.

Los eventos también se siembran solos al arrancar el backend
(`seed_narrative_v2_graphs.py`); este script permite aplicarlos sin reiniciar y
cubre cartas y personajes, que no se siembran por diseño.

Por defecto corre en seco. Para escribir:
    python -m app.scripts.expand_narrative_catalog --apply --expect-db <base>
"""

import argparse
import asyncio
import sys
from typing import Any, Dict, List

from app.core.config import settings
from app.core.database import close_mongo_connection, get_database
from app.features.narrative.constants import COLL_CARDS, COLL_CHARACTERS, COLL_V2_EVENTS
from app.scripts.narrative_catalog_extra import (
    construir_cartas,
    construir_eventos_extra,
    construir_personajes,
)


def _uri_segura(url: str) -> str:
    if "@" not in url:
        return url
    pre, post = url.split("@", 1)
    return f"{pre.split('://')[0]}://****:****@{post}"


async def _insertar_si_falta(db: Any, coleccion: str, docs: List[Dict[str, Any]], aplicar: bool) -> Dict[str, int]:
    existentes = {
        doc["_id"]
        for doc in await db[coleccion].find({"_id": {"$in": [d["_id"] for d in docs]}}, {"_id": 1}).to_list(None)
    }
    nuevos = [d for d in docs if d["_id"] not in existentes]
    if aplicar:
        for doc in nuevos:
            await db[coleccion].update_one({"_id": doc["_id"]}, {"$setOnInsert": doc}, upsert=True)
    return {"total": len(docs), "existentes": len(existentes), "insertados": 0 if not aplicar else len(nuevos)}


async def expandir(*, aplicar: bool, expect_db: str | None, permitir_test: bool) -> int:
    db = get_database()
    db_name = db.name
    uri = settings.mongodb_connection_url
    print(f"Base: {db_name} | URI: {_uri_segura(uri)}")
    print("Modo:", "APLICAR CAMBIOS" if aplicar else "DRY-RUN (sin escrituras)")

    if "test" in db_name.lower() and not permitir_test:
        print("Rechazado: la base parece de tests. Usá --allow-test-db si es intencional.", file=sys.stderr)
        return 2
    if aplicar and expect_db != db_name:
        print(f"Rechazado: --apply exige --expect-db {db_name!r} (recibido: {expect_db!r}).", file=sys.stderr)
        return 2

    eventos = [ev.model_dump(by_alias=True) for ev in construir_eventos_extra()]
    resumen = {
        "eventos": await _insertar_si_falta(db, COLL_V2_EVENTS, eventos, aplicar),
        "cartas": await _insertar_si_falta(db, COLL_CARDS, construir_cartas(), aplicar),
        "personajes": await _insertar_si_falta(db, COLL_CHARACTERS, construir_personajes(), aplicar),
    }
    for nombre, datos in resumen.items():
        print(f"{nombre}: {datos['total']} en catálogo de expansión, {datos['existentes']} ya estaban, {datos['insertados']} insertados")

    print(
        "Totales en base:",
        "eventos", await db[COLL_V2_EVENTS].count_documents({"universo_id": "corte_medieval"}),
        "| cartas", await db[COLL_CARDS].count_documents({"universo_id": "corte_medieval"}),
        "| personajes", await db[COLL_CHARACTERS].count_documents({"universo_id": "corte_medieval"}),
    )
    return 0


async def _main(args: argparse.Namespace) -> int:
    try:
        return await expandir(aplicar=args.apply, expect_db=args.expect_db, permitir_test=args.allow_test_db)
    finally:
        await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Escribe el contenido faltante (por defecto solo simula).")
    parser.add_argument("--expect-db", metavar="NOMBRE", help="Obligatorio con --apply: nombre exacto de la base a modificar.")
    parser.add_argument("--allow-test-db", action="store_true", help="Permite una base cuyo nombre contenga 'test'.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
