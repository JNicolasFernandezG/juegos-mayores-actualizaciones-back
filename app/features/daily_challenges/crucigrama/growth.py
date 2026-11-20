"""
growth.py
Generador de crucigramas por crecimiento: construye primero la solución.

Invariante: toda corrida horizontal/vertical de longitud >= 2 es una palabra
colocada (válida en el diccionario). Determinista a partir de `rng`.
"""

import random
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from app.features.daily_challenges.crucigrama.growth_grid import (  # noqa: F401
    DIR_H,
    DIR_V,
    _can_place,
    _place,
    _slot_coords,
    _struct_ok,
)
from app.features.daily_challenges.crucigrama.lexicon import (
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    _WORDS_BY_LEN,
    _init_word_index,
    normalize_banned,
    query_candidates,
)

# Tope de palabras de 3 letras por tablero (el resto se reserva a palabras más largas).
MAX_THREE_LETTER = 4


def _pick_word(
    length: int, used: Set[str], rng: random.Random, banned: FrozenSet[str] = frozenset()
) -> Optional[str]:
    pool = _WORDS_BY_LEN.get(length, [])
    if not pool:
        return None
    for _ in range(100):
        w = pool[rng.randrange(len(pool))]
        if w not in used and w not in banned:
            return w
    return None


def _find_word_through(
    grid: List[List[Optional[str]]],
    n: int,
    new_dir: str,
    r: int,
    c: int,
    used: Set[str],
    rng: random.Random,
    allow_three: bool = True,
    banned: FrozenSet[str] = frozenset(),
) -> Optional[Tuple[str, int, int, str]]:
    """Busca una palabra perpendicular a la celda (r, c) que cruce por esa letra."""
    # Preferir palabras de 4-11 letras (barajadas para variedad) y dejar las de
    # 3 letras como último recurso, para no llenar el tablero de palabras cortas.
    lengths = list(range(4, MAX_WORD_LEN + 1))
    rng.shuffle(lengths)
    if allow_three:
        lengths.append(3)

    for length in lengths:
        positions = list(range(length))
        rng.shuffle(positions)
        for pos in positions:
            start, fixed = (r - pos, c) if new_dir == DIR_V else (c - pos, r)
            if not _struct_ok(grid, n, new_dir, start, fixed, length):
                continue
            fixed_positions = [
                (i, grid[rr][cc])
                for i, (rr, cc) in enumerate(_slot_coords(new_dir, start, fixed, length))
                if grid[rr][cc] is not None
            ]
            avail = query_candidates(length, fixed_positions, used, banned)
            if not avail:
                continue
            rng.shuffle(avail)
            return (new_dir, start, fixed, avail[0])

    return None


def _try_grow(
    grid: List[List[Optional[str]]],
    n: int,
    words: List[Dict],
    used: Set[str],
    rng: random.Random,
    max_three: int = MAX_THREE_LETTER,
    banned: FrozenSet[str] = frozenset(),
) -> bool:
    allow_three = sum(1 for w in words if len(w["word"]) == 3) < max_three
    attempts = [(wi, ci) for wi, w in enumerate(words) for ci in range(len(w["coords"]))]
    rng.shuffle(attempts)

    for wi, ci in attempts:
        r, c = words[wi]["coords"][ci]
        new_dir = DIR_V if words[wi]["dir"] == DIR_H else DIR_H
        res = _find_word_through(
            grid, n, new_dir, r, c, used, rng, allow_three, banned=banned
        )
        if res:
            direction, start, fixed, word = res
            _place(grid, direction, start, fixed, word, words, used)
            return True
    return False


def _run_growth_attempt(
    n: int, rng: random.Random, max_words: int, banned: FrozenSet[str]
) -> Optional[Tuple[List[str], List[Dict]]]:
    seed_lengths = [6, 7, 8, 9]
    grid: List[List[Optional[str]]] = [[None] * n for _ in range(n)]
    words: List[Dict] = []
    used: Set[str] = set()

    sl = seed_lengths[rng.randrange(len(seed_lengths))]
    seed_word = _pick_word(sl, used, rng, banned=banned)
    if not seed_word:
        return None
    row, col = n // 2, (n - sl) // 2
    if not _can_place(grid, n, DIR_H, col, row, seed_word):
        return None
    _place(grid, DIR_H, col, row, seed_word, words, used)

    for _step in range(max_words * 3):
        if len(words) >= max_words or not _try_grow(grid, n, words, used, rng, banned=banned):
            break

    rows = ["".join(ch if ch else "#" for ch in grid[r]) for r in range(n)]
    return rows, words


def generate_growth_board(
    n: int,
    rng: random.Random,
    min_words: int = 15,
    max_words: int = 28,
    banned_words: Optional[Iterable[str]] = None,
) -> Optional[Tuple[List[str], List[Dict]]]:
    """
    Genera un tablero n x n por crecimiento.

    Devuelve (filas_con_bloques, palabras) de la primera tentativa que alcanza
    `min_words`; si ninguna lo logra, devuelve la mejor tentativa encontrada.
    `banned_words` excluye palabras del pool en todas las tentativas.
    """
    _init_word_index()
    if not _WORDS_BY_LEN:
        return None

    banned = frozenset(normalize_banned(banned_words))
    best: Optional[Tuple[List[str], List[Dict]]] = None

    for _attempt in range(40):
        candidate = _run_growth_attempt(n, rng, max_words, banned)
        if candidate is None:
            continue
        if len(candidate[1]) >= min_words:
            return candidate
        if best is None or len(candidate[1]) > len(best[1]):
            best = candidate

    return best
