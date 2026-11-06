"""
Contenido de prueba (solo dev): reclutamiento y destierro de personaje.

- card_embajada_obispo: carta de draft de peso bajo que recluta a pj_obispo_tomas.
- card_edicto_destierro: carta que da de baja a pj_obispo_tomas y limpia lo que aportaba.

Idempotente y no destructivo: inserta solo si la carta no existe y agrega las cartas
al pool mensual del desafío indicado sin quitar ninguna otra.

Uso:
    python -m testing_lab.seed_reclutamiento_live --date 2026-11-06
"""

import argparse
import asyncio
import sys

from app.core.database import connect_to_mongo, get_database
from app.features.narrative.constants import COLL_CARDS, COLL_CHALLENGES

UNIVERSO_ID = "corte_medieval"
PERSONAJE = "pj_obispo_tomas"

CARTAS = [
    {
        "_id": "card_embajada_obispo",
        "universo_id": UNIVERSO_ID,
        "categoria": "personaje",
        "nombre": "Embajada del Obispo",
        "descripcion": (
            "El Obispo Tomás solicita audiencia en la corte. Aceptarlo suma su consejo "
            "espiritual, sus contactos eclesiásticos y sus efectos mensuales."
        ),
        "imagen": "/assets/narrative/cartas/default.webp",
        "tags": [],
        "condiciones_aparicion": [],
        "efectos": [
            {
                "id": "efecto_reclutar_obispo",
                "frecuencia_id": "al_obtener",
                "condiciones": [],
                "acciones": [
                    {
                        "accion_id": "mutar_estado_entidad",
                        "parametros": {
                            "entidad": "personaje",
                            "operacion": "alta",
                            "id_entidad": PERSONAJE,
                        },
                    }
                ],
            }
        ],
        "peso_draft_mensual": 0.15,
    },
    {
        "_id": "card_edicto_destierro",
        "universo_id": UNIVERSO_ID,
        "categoria": "item",
        "nombre": "Edicto de Destierro",
        "descripcion": (
            "Destierra al Obispo Tomás: abandona la corte y se retiran sus modificadores "
            "pasivos y los tags que solo él aportaba."
        ),
        "imagen": "/assets/narrative/cartas/default.webp",
        "tags": [],
        "condiciones_aparicion": [
            {
                "tipo": "tiene_personaje",
                "personaje_id": PERSONAJE,
            }
        ],
        "efectos": [
            {
                "id": "efecto_desterrar_obispo",
                "frecuencia_id": "al_obtener",
                "condiciones": [],
                "acciones": [
                    {
                        "accion_id": "mutar_estado_entidad",
                        "parametros": {
                            "entidad": "personaje",
                            "operacion": "baja",
                            "id_entidad": PERSONAJE,
                        },
                    }
                ],
            }
        ],
        "peso_draft_mensual": 0.5,
    },
]


async def sembrar(date: str) -> int:
    db = get_database()
    insertadas = 0

    for carta in CARTAS:
        existente = await db[COLL_CARDS].find_one({"_id": carta["_id"]})
        if existente:
            print(f"[omitida] {carta['_id']} ya existe")
            continue
        await db[COLL_CARDS].insert_one(dict(carta))
        insertadas += 1
        print(f"[insertada] {carta['_id']} (peso draft {carta['peso_draft_mensual']})")

    challenge = await db[COLL_CHALLENGES].find_one({"game_id": "narrativo", "date": date})
    if not challenge:
        print(f"[error] no existe desafío narrativo para {date}")
        return 1

    pool = list((challenge.get("config") or {}).get("pool_cartas_mensuales_ids") or [])
    nuevas = [c["_id"] for c in CARTAS if c["_id"] not in pool]
    if nuevas:
        pool.extend(nuevas)
        await db[COLL_CHALLENGES].update_one(
            {"_id": challenge["_id"]},
            {"$set": {"config.pool_cartas_mensuales_ids": pool}},
        )
        print(f"[pool] agregadas al desafío {date}: {nuevas}")
    else:
        print(f"[pool] el desafío {date} ya contiene las cartas de prueba")

    print(f"Total insertadas: {insertadas}")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    await connect_to_mongo()
    return await sembrar(args.date)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
