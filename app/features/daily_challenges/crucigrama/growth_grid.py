"""Primitivas geométricas y de colocación para el generador por crecimiento."""

from typing import Dict, List, Optional, Set, Tuple

DIR_H = "H"
DIR_V = "V"


def _slot_coords(
    direction: str, start: int, fixed: int, length: int
) -> List[Tuple[int, int]]:
    """Devuelve las coordenadas (fila, columna) de un slot en el tablero."""
    if direction == DIR_H:
        return [(fixed, start + i) for i in range(length)]
    return [(start + i, fixed) for i in range(length)]


def _has_adjacent(
    grid: List[List[Optional[str]]], n: int, r: int, c: int, dr: int, dc: int
) -> bool:
    for sign in (-1, 1):
        nr, nc = r + sign * dr, c + sign * dc
        if 0 <= nr < n and 0 <= nc < n and grid[nr][nc] is not None:
            return True
    return False


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
    """
    end = start + length - 1
    if start < 0 or end >= n:
        return False

    dr, dc = (0, 1) if direction == DIR_H else (1, 0)
    pr, pc = (1, 0) if direction == DIR_H else (0, 1)
    coords = _slot_coords(direction, start, fixed, length)
    r0, c0 = coords[0]
    r1, c1 = coords[-1]
    if (start > 0 and grid[r0 - dr][c0 - dc] is not None) or (
        end < n - 1 and grid[r1 + dr][c1 + dc] is not None
    ):
        return False

    for r, c in coords:
        adj_dr, adj_dc = (pr, pc) if grid[r][c] is None else (dr, dc)
        if _has_adjacent(grid, n, r, c, adj_dr, adj_dc):
            return False
    return True


def _can_place(
    grid: List[List[Optional[str]]],
    n: int,
    direction: str,
    start: int,
    fixed: int,
    word: str,
) -> bool:
    """Verifica si `word` puede colocarse sin romper el invariante."""
    if not _struct_ok(grid, n, direction, start, fixed, len(word)):
        return False
    return all(
        grid[r][c] is None or grid[r][c] == ch
        for (r, c), ch in zip(_slot_coords(direction, start, fixed, len(word)), word)
    )


def _place(
    grid: List[List[Optional[str]]],
    direction: str,
    start: int,
    fixed: int,
    word: str,
    words: List[Dict],
    used: Set[str],
) -> None:
    coords = _slot_coords(direction, start, fixed, len(word))
    for (r, c), ch in zip(coords, word):
        grid[r][c] = ch
    words.append({
        "dir": direction,
        "row": fixed if direction == DIR_H else start,
        "col": start if direction == DIR_H else fixed,
        "word": word,
        "coords": coords,
    })
    used.add(word)
