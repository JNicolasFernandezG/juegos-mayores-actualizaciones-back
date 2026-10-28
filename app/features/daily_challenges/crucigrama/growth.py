"""
growth.py
Generador de crucigramas por crecimiento: construye primero la solución.

En lugar de fijar una plantilla de bloques y rellenarla con backtracking, coloca
palabras del diccionario que se cruzan entre sí. Las celdas sin letra terminan
como bloques ('#'), por lo que el tablero resultante es solucionable por
construcción (no depende de que un solver lo valide).

Invariante: toda corrida horizontal/vertical de longitud >= 2 es una palabra
colocada (válida en el diccionario). Se mantiene al colocar cada palabra:
- sus celdas nuevas no pueden tocar letras en el eje perpendicular (evita
  corridas de 2 letras no deseadas);
- sus extremos no pueden tocar letras en el mismo eje (evita fusiones).

Determinista: todo el azar sale de `rng`, y los conjuntos del índice se iteran
ordenados antes de barajar para no depender del orden de hashing de Python.
"""

import random
from typing import Dict, List, Optional, Set, Tuple

from app.features.daily_challenges.crucigrama import solver as _solver

MIN_WORD_LEN = _solver.MIN_WORD_LEN
MAX_WORD_LEN = _solver.MAX_WORD_LEN

DIR_H = "H"
DIR_V = "V"

# Tope de palabras de 3 letras por tablero (el resto se reserva a palabras más largas).
MAX_THREE_LETTER = 4


def _can_place(
    grid: List[List[Optional[str]]],
    n: int,
    direction: str,
    start: int,
    fixed: int,
    word: str,
) -> bool:
    """
    Verifica si `word` puede colocarse sin romper el invariante.

    direction H: fila = fixed, columna inicial = start.
    direction V: columna = fixed, fila inicial = start.
    """
    length = len(word)
    end = start + length - 1

    if start < 0 or end >= n:
        return False

    for i, ch in enumerate(word):
        if direction == DIR_H:
            r, c = fixed, start + i
        else:
            r, c = start + i, fixed

        cur = grid[r][c]
        if cur is None:
            # Celdas nuevas: no pueden tocar letras en el eje perpendicular.
            if direction == DIR_H:
                if r > 0 and grid[r - 1][c] is not None:
                    return False
                if r < n - 1 and grid[r + 1][c] is not None:
                    return False
            else:
                if c > 0 and grid[r][c - 1] is not None:
                    return False
                if c < n - 1 and grid[r][c + 1] is not None:
                    return False
        else:
            # Celda ocupada: debe coincidir y no pertenecer ya a una palabra
            # del mismo eje (un cruce válido solo atraviesa una del otro eje).
            if cur != ch:
                return False
            if direction == DIR_H:
                if c > 0 and grid[r][c - 1] is not None:
                    return False
                if c < n - 1 and grid[r][c + 1] is not None:
                    return False
            else:
                if r > 0 and grid[r - 1][c] is not None:
                    return False
                if r < n - 1 and grid[r + 1][c] is not None:
                    return False

    # Extremos del eje: no deben tocar letras (evita fusionar con palabras vecinas).
    if direction == DIR_H:
        if start > 0 and grid[fixed][start - 1] is not None:
            return False
        if end < n - 1 and grid[fixed][end + 1] is not None:
            return False
    else:
        if start > 0 and grid[start - 1][fixed] is not None:
            return False
        if end < n - 1 and grid[end + 1][fixed] is not None:
            return False

    return True


def _place(
    grid: List[List[Optional[str]]],
    direction: str,
    start: int,
    fixed: int,
    word: str,
    words: List[Dict],
    used: Set[str],
) -> None:
    coords: List[Tuple[int, int]] = []
    for i, ch in enumerate(word):
        if direction == DIR_H:
            r, c = fixed, start + i
        else:
            r, c = start + i, fixed
        grid[r][c] = ch
        coords.append((r, c))

    words.append({
        "dir": direction,
        "row": fixed if direction == DIR_H else start,
        "col": start if direction == DIR_H else fixed,
        "word": word,
        "coords": coords,
    })
    used.add(word)


def _pick_word(length: int, used: Set[str], rng: random.Random) -> Optional[str]:
    pool = _solver._WORDS_BY_LEN.get(length, [])
    if not pool:
        return None
    for _ in range(100):
        w = pool[rng.randrange(len(pool))]
        if w not in used:
            return w
    return None


def _struct_ok(
    grid: List[List[Optional[str]]],
    n: int,
    direction: str,
    start: int,
    fixed: int,
    length: int,
) -> bool:
    """
    Verifica la viabilidad estructural (independiente de la palabra concreta)
    de un slot de `length` casillas en `direction` a partir de `start`/`fixed`.

    Comprueba: límites, extremos sin letras adyacentes (evita fusiones) y que las
    celdas libres del slot no toquen letras en el eje perpendicular, y que las
    celdas ya ocupadas no pertenezcan a una palabra del mismo eje.
    """
    end = start + length - 1
    if start < 0 or end >= n:
        return False

    # Extremos del eje: no deben tocar letras.
    if direction == DIR_H:
        if start > 0 and grid[fixed][start - 1] is not None:
            return False
        if end < n - 1 and grid[fixed][end + 1] is not None:
            return False
    else:
        if start > 0 and grid[start - 1][fixed] is not None:
            return False
        if end < n - 1 and grid[end + 1][fixed] is not None:
            return False

    for i in range(length):
        if direction == DIR_H:
            r, c = fixed, start + i
        else:
            r, c = start + i, fixed

        cur = grid[r][c]
        if cur is None:
            if direction == DIR_H:
                if r > 0 and grid[r - 1][c] is not None:
                    return False
                if r < n - 1 and grid[r + 1][c] is not None:
                    return False
            else:
                if c > 0 and grid[r][c - 1] is not None:
                    return False
                if c < n - 1 and grid[r][c + 1] is not None:
                    return False
        else:
            # Celda ocupada: no debe pertenecer ya a una palabra del mismo eje.
            if direction == DIR_H:
                if c > 0 and grid[r][c - 1] is not None:
                    return False
                if c < n - 1 and grid[r][c + 1] is not None:
                    return False
            else:
                if r > 0 and grid[r - 1][c] is not None:
                    return False
                if r < n - 1 and grid[r + 1][c] is not None:
                    return False

    return True


def _find_word_through(
    grid: List[List[Optional[str]]],
    n: int,
    new_dir: str,
    r: int,
    c: int,
    used: Set[str],
    rng: random.Random,
    allow_three: bool = True,
) -> Optional[Tuple[str, int, int, str]]:
    """
    Busca una palabra perpendicular a la celda (r, c) que cruce por esa letra.

    Para cada (longitud, posición de cruce) estructuralmente viable, recoge las
    letras ya fijadas a lo largo del slot (el cruce principal más cualquier otro
    cruce con palabras existentes) y hace la intersección de los índices por
    (longitud, posición, letra) para obtener candidatos válidos sin probar uno a uno.
    """
    # Preferir palabras de 4-10 letras (barajadas para variedad) y dejar las de
    # 3 letras como último recurso, para no llenar el tablero de palabras cortas.
    lengths = list(range(4, MAX_WORD_LEN + 1))
    rng.shuffle(lengths)
    if allow_three:
        lengths.append(3)

    for L in lengths:
        positions = list(range(L))
        rng.shuffle(positions)
        for p in positions:
            if new_dir == DIR_V:
                start = r - p
                fixed = c
            else:
                start = c - p
                fixed = r

            if not _struct_ok(grid, n, new_dir, start, fixed, L):
                continue

            # Letras fijadas a lo largo del slot (cruce principal + cruces extra).
            fixed_positions: List[Tuple[int, str]] = []
            for i in range(L):
                if new_dir == DIR_V:
                    cell = grid[start + i][fixed]
                else:
                    cell = grid[fixed][start + i]
                if cell is not None:
                    fixed_positions.append((i, cell))

            cands = None
            for (pos, ch) in fixed_positions:
                s = _solver._LETTER_POS_INDEX.get((L, pos, ch))
                if not s:
                    cands = None
                    break
                cands = s if cands is None else cands & s

            if not cands:
                continue

            avail = sorted(cands - used)
            rng.shuffle(avail)
            if avail:
                return (new_dir, start, fixed, avail[0])

    return None


def _try_grow(
    grid: List[List[Optional[str]]],
    n: int,
    words: List[Dict],
    used: Set[str],
    rng: random.Random,
    max_three: int = MAX_THREE_LETTER,
) -> bool:
    three_count = sum(1 for w in words if len(w["word"]) == 3)
    allow_three = three_count < max_three

    attempts = []
    for wi, w in enumerate(words):
        for ci in range(len(w["coords"])):
            attempts.append((wi, ci))
    rng.shuffle(attempts)

    for wi, ci in attempts:
        r, c = words[wi]["coords"][ci]
        new_dir = DIR_V if words[wi]["dir"] == DIR_H else DIR_H
        res = _find_word_through(grid, n, new_dir, r, c, used, rng, allow_three)
        if res:
            direction, start, fixed, word = res
            _place(grid, direction, start, fixed, word, words, used)
            return True
    return False


def generate_growth_board(
    n: int,
    rng: random.Random,
    min_words: int = 15,
    max_words: int = 28,
) -> Optional[Tuple[List[str], List[Dict]]]:
    """
    Genera un tablero n x n por crecimiento.

    Devuelve (filas_con_bloques, palabras) de la primera tentativa que alcanza
    `min_words`; si ninguna lo logra, devuelve la mejor tentativa encontrada.
    """
    _solver._init_word_index()
    if not _solver._WORDS_BY_LEN:
        return None

    seed_lengths = [6, 7, 8, 9]
    best: Optional[Tuple[List[str], List[Dict]]] = None

    for _attempt in range(40):
        grid = [[None] * n for _ in range(n)]
        words: List[Dict] = []
        used: Set[str] = set()

        sl = seed_lengths[rng.randrange(len(seed_lengths))]
        seed_word = _pick_word(sl, used, rng)
        if not seed_word:
            continue
        row = n // 2
        col = (n - sl) // 2
        if not _can_place(grid, n, DIR_H, col, row, seed_word):
            continue
        _place(grid, DIR_H, col, row, seed_word, words, used)

        for _step in range(max_words * 3):
            if len(words) >= max_words:
                break
            if not _try_grow(grid, n, words, used, rng):
                break

        rows = ["".join(ch if ch else "#" for ch in grid[r]) for r in range(n)]
        if len(words) >= min_words:
            return rows, words
        if best is None or len(words) > len(best[1]):
            best = (rows, words)

    return best
