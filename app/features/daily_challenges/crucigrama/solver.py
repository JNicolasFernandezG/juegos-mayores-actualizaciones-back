"""
solver.py
Motor de resolución de Crucigramas mediante Backtracking (CSP) agnóstico al tamaño de grilla.

Características:
- Índice de palabras en memoria para búsqueda de candidatos O(1) por (longitud, posición, letra).
- Heurística MRV (Minimum Remaining Values) y poda hacia adelante (Forward Checking).
- Prioridad de candidatos parametrizable: pistas curadas (fácil) o caché RAE (difícil).
- Presupuesto de nodos opcional como red de seguridad para patrones sobre-restringidos.
"""

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.core.rae_client import _load_definitions_cache
from app.features.daily_challenges.crucigrama.clues import CURATED_CLUES

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DICTIONARY_PATH = DATA_DIR / "acentos_todas_palabras.json"

MIN_WORD_LEN = 3
MAX_WORD_LEN = 10

# Estructuras en memoria para búsqueda ultra-rápida de cruces
_WORDS_BY_LEN: Dict[int, List[str]] = {}
_LETTER_POS_INDEX: Dict[Tuple[int, int, str], Set[str]] = {}
_IS_INITIALIZED: bool = False


def _init_word_index() -> None:
    """Inicializa el índice de palabras en memoria para búsqueda de candidatos O(1)."""
    global _WORDS_BY_LEN, _LETTER_POS_INDEX, _IS_INITIALIZED
    if _IS_INITIALIZED:
        return

    _WORDS_BY_LEN = {l: [] for l in range(MIN_WORD_LEN, MAX_WORD_LEN + 1)}
    _LETTER_POS_INDEX = {}

    if not DICTIONARY_PATH.exists():
        logger.warning(f"[CRUCIGRAMA] No se encontró el diccionario en {DICTIONARY_PATH}.")
        _IS_INITIALIZED = True
        return

    try:
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            raw_dict = json.load(f)

        for w in raw_dict.keys():
            if MIN_WORD_LEN <= len(w) <= MAX_WORD_LEN and w.isalpha():
                w_upper = w.upper()
                _WORDS_BY_LEN[len(w)].append(w_upper)
                for pos, ch in enumerate(w_upper):
                    _LETTER_POS_INDEX.setdefault((len(w), pos, ch), set()).add(w_upper)

        logger.info(f"[CRUCIGRAMA] Diccionario indexado: {sum(len(v) for v in _WORDS_BY_LEN.values())} palabras.")
    except Exception as e:
        logger.error(f"[CRUCIGRAMA] Error inicializando índice de palabras: {e}")

    _IS_INITIALIZED = True


def _parse_template_slots(grid_pattern: List[str]) -> Tuple[List[Dict], Dict[str, List[Tuple[int, str, int]]]]:
    """
    Identifica todos los slots horizontales y verticales en la plantilla
    y precalcula el mapa de intersecciones entre ellos.
    """
    R = len(grid_pattern)
    C = len(grid_pattern[0]) if R else 0
    slots: List[Dict] = []

    # 1. Slots horizontales
    for r in range(R):
        c = 0
        while c < C:
            if grid_pattern[r][c] != "#":
                start_c = c
                coords = []
                while c < C and grid_pattern[r][c] != "#":
                    coords.append((r, c))
                    c += 1
                if len(coords) > 1:
                    slots.append({
                        "id": f"H_{r}_{start_c}",
                        "dir": "H",
                        "r": r,
                        "c": start_c,
                        "len": len(coords),
                        "coords": coords
                    })
            else:
                c += 1

    # 2. Slots verticales
    for c in range(C):
        r = 0
        while r < R:
            if grid_pattern[r][c] != "#":
                start_r = r
                coords = []
                while r < R and grid_pattern[r][c] != "#":
                    coords.append((r, c))
                    r += 1
                if len(coords) > 1:
                    slots.append({
                        "id": f"V_{start_r}_{c}",
                        "dir": "V",
                        "r": start_r,
                        "c": c,
                        "len": len(coords),
                        "coords": coords
                    })
            else:
                r += 1

    # 3. Intersecciones (cruce de casillas)
    intersections: Dict[str, List[Tuple[int, str, int]]] = {s["id"]: [] for s in slots}
    for i, s1 in enumerate(slots):
        for j, s2 in enumerate(slots):
            if i == j or s1["dir"] == s2["dir"]:
                continue
            for p1, c1 in enumerate(s1["coords"]):
                for p2, c2 in enumerate(s2["coords"]):
                    if c1 == c2:
                        intersections[s1["id"]].append((p1, s2["id"], p2))

    return slots, intersections


def _order_candidates(
    cand_list: List[str],
    cached_defs: Dict[str, str],
    rng: random.Random,
    prefer_curated: bool,
) -> List[str]:
    """Ordena candidatos: fácil prioriza pistas curadas; difícil prioriza caché RAE."""
    if prefer_curated:
        curated = [w for w in cand_list if w in CURATED_CLUES]
        cached = [w for w in cand_list if w not in CURATED_CLUES and (w in cached_defs or w.lower() in cached_defs)]
        other = [w for w in cand_list if w not in CURATED_CLUES and not (w in cached_defs or w.lower() in cached_defs)]
        rng.shuffle(curated)
        rng.shuffle(cached)
        rng.shuffle(other)
        return curated + cached + other

    cached = [w for w in cand_list if w in cached_defs or w.lower() in cached_defs]
    other = [w for w in cand_list if not (w in cached_defs or w.lower() in cached_defs)]
    rng.shuffle(cached)
    rng.shuffle(other)
    return cached + other


def _solve_crucigrama_backtracking(
    slots: List[Dict],
    intersections: Dict[str, List[Tuple[int, str, int]]],
    rng: random.Random,
    prefer_curated: bool = True,
    max_nodes: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """
    Resuelve el crucigrama usando Backtracking con poda de restricciones (Forward Checking)
    y heurística MRV (slots con más cruces evaluados primero).
    """
    _init_word_index()
    if not _WORDS_BY_LEN:
        return None

    cached_defs = _load_definitions_cache()

    # Ordenar slots por cantidad de intersecciones (MRV / Degree Heuristic)
    sorted_slots = sorted(slots, key=lambda s: len(intersections[s["id"]]), reverse=True)

    nodes = [0]

    def backtrack(idx: int, assignment: Dict[str, str], used: Set[str]) -> Optional[Dict[str, str]]:
        if max_nodes is not None and nodes[0] >= max_nodes:
            return None
        nodes[0] += 1

        if idx == len(sorted_slots):
            return assignment

        slot = sorted_slots[idx]
        s_id = slot["id"]
        s_len = slot["len"]

        # Restricciones impuestas por slots ya asignados
        constraints = []
        for my_pos, other_id, other_pos in intersections[s_id]:
            if other_id in assignment:
                constraints.append((my_pos, assignment[other_id][other_pos]))

        # Obtener candidatos válidos
        if constraints:
            cands = None
            for pos, ch in constraints:
                s_set = _LETTER_POS_INDEX.get((s_len, pos, ch), set())
                cands = s_set if cands is None else cands & s_set
            cand_list = [w for w in (cands or []) if w not in used]
        else:
            cand_list = [w for w in _WORDS_BY_LEN.get(s_len, []) if w not in used]

        if not cand_list:
            return None

        ordered_cands = _order_candidates(cand_list, cached_defs, rng, prefer_curated)

        # Poda: probar hasta 150 candidatos por rama
        for w in ordered_cands[:150]:
            assignment[s_id] = w
            used.add(w)
            res = backtrack(idx + 1, assignment, used)
            if res is not None:
                return res
            del assignment[s_id]
            used.remove(w)

        return None

    return backtrack(0, {}, set())
