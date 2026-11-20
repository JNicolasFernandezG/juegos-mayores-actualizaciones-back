"""
solver.py
Motor de resolución de Crucigramas mediante Backtracking (CSP) agnóstico al tamaño de grilla.

Características:
- Índice de palabras en memoria para búsqueda de candidatos O(1) por (longitud, posición, letra).
- Heurística MRV (Minimum Remaining Values) y poda hacia adelante (Forward Checking).
- Prioridad de candidatos parametrizable: pistas curadas (fácil) o caché RAE (difícil).
- Presupuesto de nodos opcional como red de seguridad para patrones sobre-restringidos.
"""

import random
from typing import Dict, List, Optional, Set, Tuple

from app.core.rae_client import _load_definitions_cache
from app.features.daily_challenges.crucigrama.clues import CURATED_CLUES
from app.features.daily_challenges.crucigrama.lexicon import (  # noqa: F401
    DATA_DIR,
    DICTIONARY_PATH,
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    _ACCENT_MAP,
    _LETTER_POS_INDEX,
    _WORDS_BY_LEN,
    _WORDS_SET,
    _init_word_index,
    _normalize_word,
    _parse_template_slots,
    build_solution_grid,
    is_known_word,
    normalize_banned,
    normalize_preassigned,
    normalize_word,
    prepare_anchors_and_bans,
    query_candidates,
)


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


def _slot_constraints(
    slot_id: str,
    assignment: Dict[str, str],
    intersections: Dict[str, List[Tuple[int, str, int]]],
) -> List[Tuple[int, str]]:
    return [
        (my_pos, assignment[other_id][other_pos])
        for my_pos, other_id, other_pos in intersections[slot_id]
        if other_id in assignment
    ]


def _solve_crucigrama_backtracking(
    slots: List[Dict],
    intersections: Dict[str, List[Tuple[int, str, int]]],
    rng: random.Random,
    prefer_curated: bool = True,
    max_nodes: Optional[int] = None,
    preassigned: Optional[Dict[str, str]] = None,
    banned_words: Optional[Set[str]] = None,
) -> Optional[Dict[str, str]]:
    """Resuelve el crucigrama con Backtracking, Forward Checking y heurística MRV."""
    _init_word_index()
    if not _WORDS_BY_LEN:
        return None

    cached_defs = _load_definitions_cache()
    anchors, banned = prepare_anchors_and_bans(preassigned, banned_words, slots, intersections)
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
        if s_id in anchors:
            return backtrack(idx + 1, assignment, used)

        constraints = _slot_constraints(s_id, assignment, intersections)
        cand_list = query_candidates(slot["len"], constraints, used, banned)
        if not cand_list:
            return None

        for w in _order_candidates(cand_list, cached_defs, rng, prefer_curated)[:150]:
            assignment[s_id] = w
            used.add(w)
            res = backtrack(idx + 1, assignment, used)
            if res is not None:
                return res
            del assignment[s_id]
            used.remove(w)
        return None

    return backtrack(0, dict(anchors), set(anchors.values()))
