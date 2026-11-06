"""
seed_narrative_tags.py
Siembra no destructiva de los catálogos narrativos base: tags de universo y acciones del motor.

Política:
- Por defecto inserta solo documentos faltantes ($setOnInsert): nunca reemplaza un
  documento existente, por lo que no pisa ediciones hechas desde el panel.
- `force=True` reescribe los documentos canónicos; es una operación manual explícita.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.database import get_database
from app.features.narrative.constants import COLL_ACTIONS, COLL_TAGS

logger = logging.getLogger(__name__)

UNIVERSO_ID = "corte_medieval"

TAGS_INICIALES = [
    {
        "_id": "militar",
        "universo_id": UNIVERSO_ID,
        "nombre": "Militar",
        "descripcion": "Relacionado con la fuerza armada, legiones y capacidad bélica.",
        "color": "#ef4444",  # red-500
        "categoria": "militar",
        "icono": "shield"
    },
    {
        "_id": "combate",
        "universo_id": UNIVERSO_ID,
        "nombre": "Combate",
        "descripcion": "Enfrentamiento directo en el campo de batalla.",
        "color": "#dc2626",  # red-600
        "categoria": "militar",
        "icono": "swords"
    },
    {
        "_id": "disciplina_militar",
        "universo_id": UNIVERSO_ID,
        "nombre": "Disciplina Militar",
        "descripcion": "Régimen estricto de adiestramiento y cohesión de tropa.",
        "color": "#b91c1c",  # red-700
        "categoria": "militar",
        "icono": "shield-check"
    },
    {
        "_id": "defensa",
        "universo_id": UNIVERSO_ID,
        "nombre": "Defensa",
        "descripcion": "Fortificaciones, murallas y tácticas de resistencia.",
        "color": "#f87171",  # red-400
        "categoria": "militar",
        "icono": "shield"
    },
    {
        "_id": "logistica_militar",
        "universo_id": UNIVERSO_ID,
        "nombre": "Logística Militar",
        "descripcion": "Cadenas de suministro para campamentos y tropas.",
        "color": "#f97316",  # orange-500
        "categoria": "militar",
        "icono": "truck"
    },
    {
        "_id": "mercenarios",
        "universo_id": UNIVERSO_ID,
        "nombre": "Mercenarios",
        "descripcion": "Tropas contratadas a sueldo sin lealtad jurada.",
        "color": "#ea580c",  # orange-600
        "categoria": "militar",
        "icono": "coins"
    },
    {
        "_id": "orden",
        "universo_id": UNIVERSO_ID,
        "nombre": "Orden Público",
        "descripcion": "Estabilidad civil, guardias urbanos y cumplimiento de la ley.",
        "color": "#3b82f6",  # blue-500
        "categoria": "politica",
        "icono": "scale"
    },
    {
        "_id": "diplomacia",
        "universo_id": UNIVERSO_ID,
        "nombre": "Diplomacia",
        "descripcion": "Negociación de tratados, alianzas y embajadas.",
        "color": "#60a5fa",  # blue-400
        "categoria": "politica",
        "icono": "handshake"
    },
    {
        "_id": "autoridad",
        "universo_id": UNIVERSO_ID,
        "nombre": "Autoridad",
        "descripcion": "Prestigio de mando directo ante la nobleza y súbditos.",
        "color": "#2563eb",  # blue-600
        "categoria": "politica",
        "icono": "crown"
    },
    {
        "_id": "sello_real",
        "universo_id": UNIVERSO_ID,
        "nombre": "Sello Real",
        "descripcion": "Edictos y mandatos firmados con la estampa de la corona.",
        "color": "#1d4ed8",  # blue-700
        "categoria": "politica",
        "icono": "file-check"
    },
    {
        "_id": "noble",
        "universo_id": UNIVERSO_ID,
        "nombre": "Nobleza",
        "descripcion": "Vínculos con familias aristocráticas y señores feudales.",
        "color": "#8b5cf6",  # purple-500
        "categoria": "social",
        "icono": "award"
    },
    {
        "_id": "comercio",
        "universo_id": UNIVERSO_ID,
        "nombre": "Comercio",
        "descripcion": "Rutas mercantiles, ferias y gremios de artesanos.",
        "color": "#eab308",  # yellow-500
        "categoria": "economia",
        "icono": "coins"
    },
    {
        "_id": "economia",
        "universo_id": UNIVERSO_ID,
        "nombre": "Economía",
        "descripcion": "Administración del tesoro, tributos y arcas reales.",
        "color": "#ca8a04",  # yellow-600
        "categoria": "economia",
        "icono": "banknote"
    },
    {
        "_id": "comida",
        "universo_id": UNIVERSO_ID,
        "nombre": "Comida y Grano",
        "descripcion": "Cosechas, graneros reales y reservas alimenticias.",
        "color": "#84cc16",  # lime-500
        "categoria": "recursos",
        "icono": "wheat"
    },
    {
        "_id": "abastecimiento",
        "universo_id": UNIVERSO_ID,
        "nombre": "Abastecimiento",
        "descripcion": "Flujo de víveres e insumos a plazas fuertes.",
        "color": "#65a30d",  # lime-600
        "categoria": "recursos",
        "icono": "package"
    },
    {
        "_id": "transporte",
        "universo_id": UNIVERSO_ID,
        "nombre": "Transporte y Caminos",
        "descripcion": "Caravanas, caminos reales y mantenimiento vial.",
        "color": "#a8a29e",  # stone-400
        "categoria": "recursos",
        "icono": "compass"
    },
    {
        "_id": "fe",
        "universo_id": UNIVERSO_ID,
        "nombre": "Fe",
        "descripcion": "Devoción religiosa popular eclesiástica.",
        "color": "#06b6d4",  # cyan-500
        "categoria": "religion",
        "icono": "sun"
    },
    {
        "_id": "religion",
        "universo_id": UNIVERSO_ID,
        "nombre": "Religión",
        "descripcion": "Institución del clero, templos y abadías.",
        "color": "#0891b2",  # cyan-600
        "categoria": "religion",
        "icono": "cross"
    },
    {
        "_id": "sagrado",
        "universo_id": UNIVERSO_ID,
        "nombre": "Sagrado",
        "descripcion": "Reliquias y bendiciones sacramentales.",
        "color": "#22d3ee",  # cyan-400
        "categoria": "religion",
        "icono": "sparkles"
    },
    {
        "_id": "salud",
        "universo_id": UNIVERSO_ID,
        "nombre": "Salud",
        "descripcion": "Vitalidad, prevención y atención a enfermos.",
        "color": "#10b981",  # emerald-500
        "categoria": "salud",
        "icono": "heart"
    },
    {
        "_id": "salud_reino",
        "universo_id": UNIVERSO_ID,
        "nombre": "Salud del Reino",
        "descripcion": "Salubridad pública y control de pestes.",
        "color": "#059669",  # emerald-600
        "categoria": "salud",
        "icono": "activity"
    },
    {
        "_id": "alquimia",
        "universo_id": UNIVERSO_ID,
        "nombre": "Alquimia",
        "descripcion": "Elixires, destilaciones y secretos botánicos.",
        "color": "#14b8a6",  # teal-500
        "categoria": "ciencia",
        "icono": "flask-conical"
    },
    {
        "_id": "remedios_alquimia",
        "universo_id": UNIVERSO_ID,
        "nombre": "Remedios Alquímicos",
        "descripcion": "Pociones y ungüentos medicinales avanzados.",
        "color": "#0d9488",  # teal-600
        "categoria": "ciencia",
        "icono": "flask-round"
    },
    {
        "_id": "ciencia",
        "universo_id": UNIVERSO_ID,
        "nombre": "Ciencia y Sabiduría",
        "descripcion": "Tratados académicos, cartografía y erudición.",
        "color": "#6366f1",  # indigo-500
        "categoria": "ciencia",
        "icono": "book-open"
    },
    {
        "_id": "intriga",
        "universo_id": UNIVERSO_ID,
        "nombre": "Intriga",
        "descripcion": "Conspiraciones, pactos secretos y rumores cortesanos.",
        "color": "#a855f7",  # purple-500
        "categoria": "espionaje",
        "icono": "eye-off"
    },
    {
        "_id": "espionaje",
        "universo_id": UNIVERSO_ID,
        "nombre": "Espionaje",
        "descripcion": "Vigilancia, agentes infiltrados y contrainteligencia.",
        "color": "#9333ea",  # purple-600
        "categoria": "espionaje",
        "icono": "user-secret"
    },
    {
        "_id": "red_espias",
        "universo_id": UNIVERSO_ID,
        "nombre": "Red de Espías",
        "descripcion": "Organización encubierta de informantes en plazas y tabernas.",
        "color": "#7e22ce",  # purple-700
        "categoria": "espionaje",
        "icono": "network"
    },
    {
        "_id": "sombras",
        "universo_id": UNIVERSO_ID,
        "nombre": "Sombras",
        "descripcion": "Operaciones nocturnas y asesinatos sigilosos.",
        "color": "#475569",  # slate-600
        "categoria": "espionaje",
        "icono": "moon"
    },
    {
        "_id": "informacion",
        "universo_id": UNIVERSO_ID,
        "nombre": "Información",
        "descripcion": "Noticias tempranas de fronteras y despachos cifrados.",
        "color": "#64748b",  # slate-500
        "categoria": "espionaje",
        "icono": "mail"
    },
    {
        "_id": "moral",
        "universo_id": UNIVERSO_ID,
        "nombre": "Moral del Pueblo",
        "descripcion": "Ánimo, esperanza y lealtad popular a la corona.",
        "color": "#f59e0b",  # amber-500
        "categoria": "social",
        "icono": "smile"
    },
    {
        "_id": "paz",
        "universo_id": UNIVERSO_ID,
        "nombre": "Paz",
        "descripcion": "Ausencia de revueltas, tregua y concordia.",
        "color": "#10b981",  # emerald-500
        "categoria": "social",
        "icono": "feather"
    },
    {
        "_id": "fiesta",
        "universo_id": UNIVERSO_ID,
        "nombre": "Fiesta y Festejos",
        "descripcion": "Celebraciones cortesanas, torneos y banquetes.",
        "color": "#ec4899",  # pink-500
        "categoria": "social",
        "icono": "party-popper"
    }
]

def _acciones_iniciales(universo_id: str) -> List[Dict[str, Any]]:
    from app.features.narrative.admin.actions_crud_service import CATALOGO_PRIMITIVAS

    ahora = datetime.now(timezone.utc).isoformat()
    return [
        {
            "_id": item["primitiva"],
            "universo_id": universo_id,
            "nombre": item["nombre"],
            "descripcion": item.get("descripcion", ""),
            "primitiva": item["primitiva"],
            "permitido_en": item.get("permitido_en", ["carta", "personaje"]),
            "activo": True,
            "version": 1,
            "updated_at": ahora,
        }
        for item in CATALOGO_PRIMITIVAS
    ]


async def _sembrar(coleccion: str, documentos: List[Dict[str, Any]], force: bool) -> Dict[str, int]:
    db = get_database()
    col = db[coleccion]
    resumen = {"insertados": 0, "actualizados": 0, "omitidos": 0}

    for doc in documentos:
        cuerpo = {k: v for k, v in doc.items() if k != "_id"}
        if force:
            res = await col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        else:
            res = await col.update_one({"_id": doc["_id"]}, {"$setOnInsert": cuerpo}, upsert=True)

        if res.upserted_id:
            resumen["insertados"] += 1
        elif force:
            resumen["actualizados"] += 1
        else:
            resumen["omitidos"] += 1

    logger.info(
        "Seed %s: %d insertados, %d actualizados, %d existentes",
        coleccion, resumen["insertados"], resumen["actualizados"], resumen["omitidos"],
    )
    return resumen


async def seed_narrative_tags(universo_id: str = UNIVERSO_ID, force: bool = False) -> Dict[str, int]:
    documentos = [t for t in TAGS_INICIALES if t["universo_id"] == universo_id]
    return await _sembrar(COLL_TAGS, documentos, force)


async def seed_narrative_actions(universo_id: str = UNIVERSO_ID, force: bool = False) -> Dict[str, int]:
    return await _sembrar(COLL_ACTIONS, _acciones_iniciales(universo_id), force)


async def seed_narrative_catalogs(universo_id: str = UNIVERSO_ID, force: bool = False) -> Dict[str, Dict[str, int]]:
    return {
        "tags": await seed_narrative_tags(universo_id, force),
        "acciones": await seed_narrative_actions(universo_id, force),
    }


if __name__ == "__main__":
    import sys

    evitar_sobrescritura = "--force" not in sys.argv
    asyncio.run(seed_narrative_catalogs(force=not evitar_sobrescritura))
