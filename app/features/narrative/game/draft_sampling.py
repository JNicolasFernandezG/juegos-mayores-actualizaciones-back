"""
Sorteo del draft mensual ponderado por carta y armado de la oferta mensual.

Cada carta aporta `peso_draft_mensual` (por defecto 1.0). Un peso menor vuelve la
carta más rara; peso 0 la excluye salvo que no quede ninguna otra candidata.
"""

import random
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.features.narrative.constants import COLL_CARDS
from app.features.narrative.engine.condition_evaluator import evaluar_condiciones


def sortear_cartas_draft(
    candidatas: Sequence[str],
    cartas_docs_map: Optional[Dict[str, Any]] = None,
    cantidad: int = 3,
) -> List[str]:
    pendientes = list(dict.fromkeys(candidatas))
    if not pendientes:
        return []

    docs = cartas_docs_map or {}
    pesos: Dict[str, float] = {}
    for carta_id in pendientes:
        try:
            peso = float((docs.get(carta_id) or {}).get("peso_draft_mensual", 1.0))
        except (TypeError, ValueError):
            peso = 1.0
        pesos[carta_id] = max(0.0, peso)

    elegidas: List[str] = []
    while pendientes and len(elegidas) < cantidad:
        total = sum(pesos[carta_id] for carta_id in pendientes)
        if total <= 0:
            elegida = random.choice(pendientes)
        else:
            elegida = random.choices(pendientes, weights=[pesos[c] for c in pendientes], k=1)[0]
        elegidas.append(elegida)
        pendientes.remove(elegida)

    return elegidas


def nuevo_turno_actual(cartas_ofrecidas_ids: List[str]) -> Dict[str, Any]:
    """Construye la estructura inicial limpia del turno mensual."""
    return {
        "cartas_ofrecidas_ids": cartas_ofrecidas_ids,
        "carta_elegida_id": None,
        "evento_actual_id": None,
        "opcion_elegida_id": None,
        "resultado_obtenido_id": None,
        "conversacion_actual_id": None,
    }


async def preparar_draft_mensual(
    run: Dict[str, Any],
    pool_mensuales: Sequence[str],
    db: Any,
    *,
    sortear_fn: Optional[Callable[..., List[str]]] = None,
) -> List[str]:
    """Filtra cartas disponibles, evalúa condiciones de aparición y sortea las 3 del draft."""
    en_mano = set(run.get("cartas_en_mano", []))
    disponibles = [cid for cid in pool_mensuales if cid not in en_mano]
    if len(disponibles) < 3:
        disponibles = list(pool_mensuales)

    cartas_docs_map = {
        c["_id"]: c for c in await db[COLL_CARDS].find({"_id": {"$in": disponibles}}).to_list(None)
    }
    elegibles = [
        cid for cid in disponibles
        if evaluar_condiciones(cartas_docs_map.get(cid, {}).get("condiciones_aparicion", []), run)
    ]
    candidatas = (
        elegibles
        if len(elegibles) >= 3
        else (elegibles + [cid for cid in disponibles if cid not in elegibles])
    )
    sorteador = sortear_fn or sortear_cartas_draft
    return sorteador(candidatas, cartas_docs_map)
