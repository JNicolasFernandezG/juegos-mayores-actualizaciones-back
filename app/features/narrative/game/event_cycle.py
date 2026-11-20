"""
event_cycle.py
Inferencia temática/climática de grafos V2, selección del mazo diario de eventos y
proyección de `eventos_del_dia` para la muestra estratégica de Etapa 0.
"""

import random
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from app.features.narrative.constants import COLL_V2_EVENTS

_RECURSOS_LABELS: Dict[str, str] = {
    "pueblo": "Pueblo",
    "fe": "Fe",
    "ejercito": "Ejército",
    "oro": "Oro",
    "nobleza": "Nobleza",
}
_TAGS_CATEGORIA_LABELS: Dict[str, str] = {
    **_RECURSOS_LABELS,
    "militar": "Militar",
    "comercio": "Comercio",
    "diplomacia": "Diplomacia",
    "noble": "Nobleza",
    "ciencia": "Ciencia",
    "alquimia": "Ciencia",
    "intriga": "Intriga",
}
_TONOS_VALIDOS = ("positivo", "negativo", "neutro")


def _iter_nodos(evt: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    nodos = evt.get("nodos") or {}
    items = nodos.values() if isinstance(nodos, dict) else nodos
    return (n for n in items if isinstance(n, dict))


def _normalizar_categoria(valor: Any) -> str:
    """Lleva la categoría a un vocabulario legible y compartido (Pueblo, Fe, Ejército, Oro...)."""
    limpio = str(valor or "").strip()
    if not limpio:
        return ""
    clave = limpio.lower()
    return _TAGS_CATEGORIA_LABELS.get(clave) or _RECURSOS_LABELS.get(clave) or limpio


def inferir_categoria_evento(
    evt: Dict[str, Any], recursos_nombres: Optional[Dict[str, str]] = None
) -> str:
    """Deriva la categoría temática del evento (explícita, por tags o impacto principal)."""
    explicita = _normalizar_categoria(evt.get("categoria_evento") or evt.get("categoria"))
    if explicita:
        return explicita

    nombres_rec = {k.lower(): v for k, v in (recursos_nombres or {}).items()}
    for tag in evt.get("tags_tematicos") or []:
        clave = str(tag or "").strip().lower()
        if clave in _TAGS_CATEGORIA_LABELS:
            return _TAGS_CATEGORIA_LABELS[clave]
        if clave in nombres_rec:
            return nombres_rec[clave]

    pesos: Dict[str, int] = {}
    for nodo in _iter_nodos(evt):
        if not nodo.get("es_final"):
            continue
        for imp in nodo.get("impactos_recursos") or []:
            if isinstance(imp, dict) and imp.get("recurso"):
                rec = str(imp["recurso"]).strip().lower()
                pesos[rec] = pesos.get(rec, 0) + abs(int(imp.get("delta", 0)))

    if pesos:
        top_key = max(pesos, key=lambda k: (pesos[k], k))
        return _RECURSOS_LABELS.get(top_key) or nombres_rec.get(top_key) or top_key.capitalize()
    return "Reino"


def inferir_tono_evento(evt: Dict[str, Any]) -> Literal["positivo", "negativo", "neutro"]:
    """
    Deriva la polaridad climática del grafo.

    El tono explícito del evento manda. Si falta, se respeta el `tipo_desenlace`
    declarado por el autor (mayoría estricta entre los finales). Sólo cuando ningún
    final declara tipo se usa el signo de sus impactos, y se exige que *todos* los
    finales coincidan: los finales mixtos describen un evento con riesgo y recompensa,
    no una suma de magnitudes de caminos alternativos (lo que volvía positivo a casi
    cualquier evento).
    """
    explicito = str(evt.get("tono") or "").strip().lower()
    if explicito in _TONOS_VALIDOS:
        return explicito  # type: ignore[return-value]

    tipos: List[str] = []
    signos: List[int] = []
    for nodo in _iter_nodos(evt):
        if not nodo.get("es_final"):
            continue
        balance = 0
        tipo_raw = nodo.get("tipo_desenlace")
        tipo = str(getattr(tipo_raw, "value", tipo_raw) or "").strip().lower()
        if tipo in _TONOS_VALIDOS:
            tipos.append(tipo)
        if tipo == "positivo":
            balance += 20
        elif tipo == "negativo":
            balance -= 20
        for campo in ("impactos_recursos", "impactos_afinidad"):
            balance += sum(int(imp.get("delta", 0)) for imp in (nodo.get(campo) or []) if isinstance(imp, dict))
        signos.append((balance > 0) - (balance < 0))

    if tipos:
        positivos = tipos.count("positivo")
        negativos = tipos.count("negativo")
        neutros = tipos.count("neutro")
        if positivos > negativos and positivos > neutros:
            return "positivo"
        if negativos > positivos and negativos > neutros:
            return "negativo"
        return "neutro"

    if not signos:
        return "neutro"
    if all(s > 0 for s in signos):
        return "positivo"
    if all(s < 0 for s in signos):
        return "negativo"
    return "neutro"


def resumir_evento_para_ciclo(
    evt: Dict[str, Any], recursos_nombres: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Proyecta un evento V2 en el resumen seguro (sin spoilers) para Etapa 0."""
    desc = str(evt.get("descripcion") or "").strip()
    if not desc:
        nodos = evt.get("nodos") or {}
        raiz_id = evt.get("nodo_raiz")
        raiz = nodos.get(raiz_id) if isinstance(nodos, dict) else next((n for n in _iter_nodos(evt) if n.get("id") == raiz_id), None)
        desc = str((raiz or {}).get("texto") or "").strip()

    categoria = inferir_categoria_evento(evt, recursos_nombres)
    return {
        "id": str(evt.get("_id") or evt.get("id") or ""),
        "titulo": str(evt.get("titulo") or ""),
        "descripcion": desc,
        "categoria": categoria,
        "categoria_evento": categoria,
        "tono": inferir_tono_evento(evt),
    }


def _agregar_prerrequisitos(elegidos_ids: List[str], by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    vistos = set(elegidos_ids)
    resultado = list(elegidos_ids)
    cola = list(elegidos_ids)
    while cola:
        cur_id = cola.pop(0)
        for req_id in (by_id.get(cur_id) or {}).get("requisitos_eventos_previos") or []:
            if req_id in by_id and req_id not in vistos:
                vistos.add(req_id)
                resultado.append(req_id)
                cola.append(req_id)
    return resultado


def seleccionar_ciclo_eventos_diario(
    eventos: List[Dict[str, Any]], rng: random.Random, *, tamano: int = 12
) -> List[str]:
    """Sortea un subconjunto diario con perfil temático o climático variado preservando arcos."""
    if len(eventos) <= 6:
        return [str(e["_id"]) for e in eventos]

    meta: List[Tuple[str, str, str]] = [
        (str(e["_id"]), inferir_categoria_evento(e), inferir_tono_evento(e)) for e in eventos
    ]
    by_id = {str(e["_id"]): e for e in eventos}
    objetivo = min(len(eventos), max(8, tamano))

    por_cat: Dict[str, List[str]] = {}
    for eid, cat, _ in meta:
        por_cat.setdefault(cat, []).append(eid)
    cats_multi = [c for c, ids in por_cat.items() if len(ids) >= 2]
    modo = rng.choice(["categoria", "categoria", "soleado", "tormentoso", "balanceado"])

    elegidos: List[str] = []
    if modo in ("soleado", "tormentoso", "balanceado") and len(cats_multi) >= 2:
        c1, c2 = rng.sample(cats_multi, 2)
        g1, g2 = list(por_cat[c1]), list(por_cat[c2])
        rng.shuffle(g1)
        rng.shuffle(g2)
        par = min(3, len(g1), len(g2))
        elegidos.extend(g1[:par] + g2[:par])
        tono_obj = "positivo" if modo == "soleado" else ("negativo" if modo == "tormentoso" else None)
        extras = [e for e in meta if e[0] not in elegidos and e[1] not in (c1, c2)]
        if tono_obj:
            extras.sort(key=lambda item: (0 if item[2] == tono_obj else 1, rng.random()))
        else:
            rng.shuffle(extras)
        elegidos.extend(item[0] for item in extras[: max(0, objetivo - len(elegidos))])
    else:
        cat_foco = rng.choice(list(por_cat.keys()))
        foco_ids = list(por_cat[cat_foco])
        resto_ids = [eid for eid, cat, _ in meta if cat != cat_foco]
        rng.shuffle(foco_ids)
        rng.shuffle(resto_ids)
        elegidos = (foco_ids[: max(3, objetivo // 3 + 1)] + resto_ids)[:objetivo]

    return _agregar_prerrequisitos(elegidos, by_id)


async def cargar_eventos_del_dia_setup(
    db: Any,
    cfg: Dict[str, Any],
    universo_doc: Optional[Dict[str, Any]],
    *,
    pool_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Carga y proyecta `eventos_del_dia` del desafío actual para Etapa 0.

    `pool_ids` permite anunciar el mazo fijado en la run activa; una lista vacía
    replica el fallback al universo que usa el sampler cuando la run no tiene pool.
    """
    recursos_nombres = {
        r["clave"]: r.get("nombre", r["clave"].capitalize())
        for r in (universo_doc or {}).get("recursos", [])
        if isinstance(r, dict) and "clave" in r
    }
    fuente_ids = pool_ids if pool_ids is not None else (cfg.get("pool_eventos_disponibles_ids") or [])
    ids_pool = [str(eid) for eid in fuente_ids if eid]
    docs: List[Dict[str, Any]] = []
    if ids_pool:
        encontrados = await db[COLL_V2_EVENTS].find({"_id": {"$in": ids_pool}}).to_list(None)
        orden = {eid: idx for idx, eid in enumerate(ids_pool)}
        docs = sorted(encontrados, key=lambda d: orden.get(str(d.get("_id")), len(ids_pool)))
    if not docs and cfg.get("universo_id"):
        docs = await db[COLL_V2_EVENTS].find({"universo_id": cfg["universo_id"]}).to_list(None)
    return [resumir_evento_para_ciclo(e, recursos_nombres) for e in docs]
