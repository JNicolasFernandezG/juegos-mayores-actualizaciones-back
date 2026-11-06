"""
Sorteo del draft mensual ponderado por carta.

Cada carta aporta `peso_draft_mensual` (por defecto 1.0). Un peso menor vuelve la
carta más rara; peso 0 la excluye salvo que no quede ninguna otra candidata.
El sorteo es sin reemplazo: se extraen posiciones sucesivas descartando lo elegido.
"""

import random
from typing import Any, Dict, List, Optional, Sequence


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
