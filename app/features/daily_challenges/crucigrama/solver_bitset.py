"""
solver_bitset.py
Motor de resolución para máscaras densas: arco-consistencia AC-3 con dominios
representados como enteros de bits (un bit por palabra del léxico) y selección
MRV. Donde el backtracking con forward checking agota su presupuesto, la
propagación completa poda el tablero en decenas de nodos.

Misma API que `_solve_crucigrama_backtracking`: anclas por slot, vetos,
unicidad de palabras y semilla determinista.
"""

import random
import time
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from app.core.rae_client import _load_definitions_cache
from app.features.daily_challenges.crucigrama import solver as base_solver

_WORD_LISTS: Dict[int, List[str]] = {}
_WORD_INDEX: Dict[int, Dict[str, int]] = {}
_POS_MASKS: Dict[int, List[Dict[str, int]]] = {}
_INDEX_READY = False


def _init_index() -> None:
    """Construye una vez por proceso el índice de palabras y máscaras por letra."""
    global _WORD_LISTS, _WORD_INDEX, _POS_MASKS, _INDEX_READY
    if _INDEX_READY:
        return

    base_solver._init_word_index()
    word_lists: Dict[int, List[str]] = {}
    word_index: Dict[int, Dict[str, int]] = {}
    pos_masks: Dict[int, List[Dict[str, int]]] = {}

    for length in range(base_solver.MIN_WORD_LEN, base_solver.MAX_WORD_LEN + 1):
        words = sorted(base_solver._WORDS_BY_LEN.get(length, []))
        word_lists[length] = words
        word_index[length] = {word: i for i, word in enumerate(words)}
        positions: List[Dict[str, int]] = []
        for pos in range(length):
            by_letter: Dict[str, int] = {}
            for i, word in enumerate(words):
                letter = word[pos]
                by_letter[letter] = by_letter.get(letter, 0) | (1 << i)
            positions.append(by_letter)
        pos_masks[length] = positions

    _WORD_LISTS, _WORD_INDEX, _POS_MASKS = word_lists, word_index, pos_masks
    _INDEX_READY = True


def _ban_masks(banned: Set[str]) -> Dict[int, int]:
    masks = {length: 0 for length in _WORD_LISTS}
    for word in banned:
        index = _WORD_INDEX.get(len(word), {}).get(word)
        if index is not None:
            masks[len(word)] |= 1 << index
    return masks


def solve_with_bitsets(
    slots: List[Dict],
    intersections: Dict[str, List[Tuple[int, str, int]]],
    rng: random.Random,
    prefer_curated: bool = True,
    max_nodes: Optional[int] = None,
    max_seconds: Optional[float] = None,
    preassigned: Optional[Dict[str, str]] = None,
    banned_words: Optional[Set[str]] = None,
) -> Optional[Dict[str, str]]:
    """
    Resuelve el crucigrama con AC-3 + MRV.

    `preassigned` fija anclas por slot_id y `banned_words` excluye palabras del
    pool. Ambos se aplican como dominios iniciales, así la propagación los
    respeta desde el primer nodo. Devuelve None si agota `max_nodes` o
    `max_seconds` sin solución.
    """
    _init_index()
    if not _WORD_LISTS:
        return None

    cached_defs = _load_definitions_cache()
    anchors = base_solver.normalize_preassigned(preassigned or {}, slots, intersections)
    banned = {
        base_solver.normalize_word(word)
        for word in (banned_words or set())
        if base_solver.normalize_word(word)
    }

    fijadas_vetadas = [word for word in anchors.values() if word in banned]
    if fijadas_vetadas:
        raise ValueError(
            f"La palabra '{fijadas_vetadas[0]}' está fijada y vetada al mismo tiempo."
        )

    slot_by_id = {slot["id"]: slot for slot in slots}
    degree = {slot["id"]: len(intersections[slot["id"]]) for slot in slots}
    ban_by_len = _ban_masks(banned)
    base_domains = {
        length: ((1 << len(words)) - 1) & ~ban_by_len[length]
        for length, words in _WORD_LISTS.items()
    }
    domains = {slot["id"]: base_domains[slot["len"]] for slot in slots}

    for slot_id, word in anchors.items():
        length = slot_by_id[slot_id]["len"]
        bit = 1 << _WORD_INDEX[length][word]
        domains[slot_id] = bit
        for other in slots:
            if other["id"] != slot_id and other["len"] == length:
                domains[other["id"]] &= ~bit

    def propagate(dom: Dict[str, int]) -> bool:
        """AC-3: recorta cada dominio a las letras soportadas por sus vecinos."""
        queue = deque(slot["id"] for slot in slots)
        while queue:
            slot_id = queue.popleft()
            slot = slot_by_id[slot_id]
            for pos, other_id, other_pos in intersections[slot_id]:
                other = slot_by_id[other_id]
                other_dom = dom[other_id]
                if not other_dom:
                    return False
                allowed = 0
                for letter, letter_mask in _POS_MASKS[other["len"]][other_pos].items():
                    if other_dom & letter_mask:
                        allowed |= _POS_MASKS[slot["len"]][pos].get(letter, 0)
                new_dom = dom[slot_id] & allowed
                if new_dom != dom[slot_id]:
                    if not new_dom:
                        return False
                    dom[slot_id] = new_dom
                    for _, neighbor_id, _ in intersections[slot_id]:
                        if neighbor_id != other_id:
                            queue.append(neighbor_id)
        return True

    if not propagate(domains):
        return None

    nodes = 0
    deadline = time.perf_counter() + max_seconds if max_seconds else None

    def domain_words(mask: int, length: int) -> List[str]:
        words = _WORD_LISTS[length]
        if mask == base_domains[length]:
            return words
        result: List[str] = []
        index = 0
        while mask:
            if mask & 1:
                result.append(words[index])
            mask >>= 1
            index += 1
        return result

    def backtrack(
        assignment: Dict[str, str], dom: Dict[str, int]
    ) -> Optional[Dict[str, str]]:
        nonlocal nodes
        if max_nodes is not None and nodes >= max_nodes:
            return None
        if deadline is not None and time.perf_counter() > deadline:
            return None
        nodes += 1

        if len(assignment) == len(slots):
            return dict(assignment)

        best_slot: Optional[Dict] = None
        best_size: Optional[int] = None
        for slot in slots:
            if slot["id"] in assignment:
                continue
            size = dom[slot["id"]].bit_count()
            if size == 0:
                return None
            if (
                best_size is None
                or size < best_size
                or (
                    size == best_size
                    and degree[slot["id"]] > degree[best_slot["id"]]
                )
            ):
                best_slot, best_size = slot, size

        slot = best_slot
        length = slot["len"]
        ordered = base_solver._order_candidates(
            domain_words(dom[slot["id"]], length), cached_defs, rng, prefer_curated
        )
        for word in ordered:
            bit = 1 << _WORD_INDEX[length][word]
            next_dom = dict(dom)
            next_dom[slot["id"]] = bit
            for other in slots:
                if (
                    other["len"] == length
                    and other["id"] != slot["id"]
                    and other["id"] not in assignment
                ):
                    next_dom[other["id"]] &= ~bit
            if not propagate(next_dom):
                continue
            assignment[slot["id"]] = word
            result = backtrack(assignment, next_dom)
            if result is not None:
                return result
            del assignment[slot["id"]]
        return None

    return backtrack(dict(anchors), domains)
