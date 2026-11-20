"""
generator.py
Orquestador del Crucigrama con dos dificultades:

- facil: tablero 7x7 con plantillas simétricas + backtracking CSP y pistas curadas.
- dificil: tablero 11x11 generado por crecimiento con definiciones RAE.
"""

import concurrent.futures
import logging
import random
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.core.config import settings
from app.core.rae_client import fetch_rae_definition, fetch_rae_definitions_batch
from app.features.daily_challenges.crucigrama.clues import CURATED_CLUES
from app.features.daily_challenges.crucigrama.growth import generate_growth_board
from app.features.daily_challenges.crucigrama.lexicon import (
    _parse_template_slots, build_solution_grid, normalize_banned,
)
from app.features.daily_challenges.crucigrama.solver import _solve_crucigrama_backtracking
from app.features.daily_challenges.crucigrama.templates_facil import CRUCIGRAMA_TEMPLATES

logger = logging.getLogger(__name__)
DIFF_FACIL, DIFF_DIFICIL, DIFICIL_SIZE = "facil", "dificil", 11


def _fetch_clue(word: str) -> Optional[str]:
    return fetch_rae_definition(word)


_DEFAULT_FETCH_CLUE = _fetch_clue
_DEFAULT_FETCH_RAE = fetch_rae_definition


def _extract_grid_word(
    grid_raw: List[str], r: int, c: int, dr: int, dc: int,
    prefix: str, direction: str, num: int, ptr_grid: List[List[Optional[int]]],
) -> Dict[str, Any]:
    rows, cols = len(grid_raw), len(grid_raw[0])
    chars, coords = [], []
    rr, cc = r, c
    while rr < rows and cc < cols and grid_raw[rr][cc] != "#":
        chars.append(grid_raw[rr][cc])
        coords.append([rr, cc])
        ptr_grid[rr][cc] = num
        rr += dr
        cc += dc
    word_str = "".join(chars)
    return {
        "id": f"{prefix}{num}", "number": num, "direction": direction,
        "word": word_str, "length": len(word_str), "row": r, "col": c,
        "coords": coords, "clue": CURATED_CLUES.get(word_str, f"Palabra de {len(word_str)} letras."),
    }


def _enrich_clues(
    all_words: List[Dict[str, Any]], overrides: Dict[str, str], prefer_curated: bool
) -> None:
    rae_needed = [
        item["word"] for item in all_words
        if item["word"] not in overrides and not (prefer_curated and item["word"] in CURATED_CLUES)
    ]
    rae_defs: Dict[str, Optional[str]] = {}
    if rae_needed:
        if _fetch_clue is _DEFAULT_FETCH_CLUE and fetch_rae_definition is _DEFAULT_FETCH_RAE:
            rae_defs = fetch_rae_definitions_batch(rae_needed)
        else:
            unique = list(dict.fromkeys(rae_needed))
            workers = max(1, min(settings.RAE_MAX_CONCURRENCY, len(unique)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                rae_defs = dict(zip(unique, executor.map(_fetch_clue, unique)))

    for item in all_words:
        w = item["word"]
        raw = (
            overrides.get(w)
            or (CURATED_CLUES[w] if prefer_curated and w in CURATED_CLUES else None)
            or rae_defs.get(w)
            or f"Palabra de {len(w)} letras que comienza con '{w[0]}' y termina en '{w[-1]}'."
        )
        item["clue"] = re.sub(r"^definici[oó]n\s*[:\-]?\s*", "", raw, flags=re.IGNORECASE).strip()


def _build_cells_matrix(
    grid_raw: List[str],
    cell_numbers: List[List[Optional[int]]],
    cell_across: List[List[Optional[int]]],
    cell_down: List[List[Optional[int]]],
) -> List[List[Dict[str, Any]]]:
    return [
        [
            {
                "row": r, "col": c, "is_block": (ch == "#"),
                "letter": "" if ch == "#" else ch, "number": cell_numbers[r][c],
                "across_num": cell_across[r][c], "down_num": cell_down[r][c],
            }
            for c, ch in enumerate(row)
        ]
        for r, row in enumerate(grid_raw)
    ]


def _parse_and_build_challenge(
    theme: str, grid_raw: List[str], prefer_curated: bool = True,
    clue_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Analiza una grilla resuelta, asigna números y enriquece pistas con la RAE."""
    rows, cols = len(grid_raw), len(grid_raw[0]) if grid_raw else 0
    grid_raw = [row.ljust(cols, "#")[:cols] for row in grid_raw]
    num = 1
    across_words, down_words = [], []
    cell_numbers = [[None] * cols for _ in range(rows)]
    cell_across = [[None] * cols for _ in range(rows)]
    cell_down = [[None] * cols for _ in range(rows)]

    for r in range(rows):
        for c in range(cols):
            if grid_raw[r][c] == "#":
                continue
            is_a = (c == 0 or grid_raw[r][c - 1] == "#") and (c + 1 < cols and grid_raw[r][c + 1] != "#")
            is_d = (r == 0 or grid_raw[r - 1][c] == "#") and (r + 1 < rows and grid_raw[r + 1][c] != "#")
            if not (is_a or is_d):
                continue
            assigned_num = num
            cell_numbers[r][c] = num
            num += 1
            if is_a:
                across_words.append(_extract_grid_word(grid_raw, r, c, 0, 1, "H", "horizontal", assigned_num, cell_across))
            if is_d:
                down_words.append(_extract_grid_word(grid_raw, r, c, 1, 0, "V", "vertical", assigned_num, cell_down))

    all_words = across_words + down_words
    overrides = {
        str(k).strip().upper(): str(v).strip()
        for k, v in (clue_overrides or {}).items()
        if str(v or "").strip()
    }
    _enrich_clues(all_words, overrides, prefer_curated)
    cells = _build_cells_matrix(grid_raw, cell_numbers, cell_across, cell_down)
    return {
        "theme": theme, "grid_size": rows, "cells": cells,
        "words": all_words, "total_words": len(all_words),
    }


def build_challenge_from_solution(
    theme: str, solution_grid: List[str], prefer_curated: bool = False,
    clue_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Construye el contrato completo del desafío a partir de una grilla resuelta."""
    return _parse_and_build_challenge(
        theme, solution_grid, prefer_curated=prefer_curated, clue_overrides=clue_overrides
    )


def _generate_facil(
    date_str: str, rng: random.Random, banned: Set[str] = frozenset()
) -> Tuple[str, List[str]]:
    seed_val = int(date_str.replace("-", ""))
    tmpl_data = CRUCIGRAMA_TEMPLATES[seed_val % len(CRUCIGRAMA_TEMPLATES)]
    theme = tmpl_data.get("theme", "Palabras Cruzadas")
    pattern = tmpl_data["pattern"]
    slots, intersections = _parse_template_slots(pattern)
    solution = _solve_crucigrama_backtracking(
        slots, intersections, rng, prefer_curated=True, banned_words=banned
    )
    final_grid = build_solution_grid(pattern, slots, solution) if solution else None
    if final_grid is None:
        logger.warning(f"[CRUCIGRAMA] Backtracking sin solución para {date_str} (facil). Usando tablero curado de respaldo.")
        final_grid = tmpl_data["fallback_grid"]
    return theme, final_grid


def _generate_dificil(
    date_str: str, rng: random.Random, banned: Set[str] = frozenset()
) -> Tuple[str, List[str]]:
    result = generate_growth_board(DIFICIL_SIZE, rng, min_words=15, max_words=28, banned_words=banned)
    if result is None:
        raise RuntimeError("No se pudo generar el crucigrama difícil (índice de palabras vacío).")
    final_grid, words = result
    if len(words) < 15:
        logger.warning(f"[CRUCIGRAMA] Difícil {date_str}: solo {len(words)} palabras (objetivo 15).")
    return "Palabras Cruzadas", final_grid


def generate_crucigrama_challenge_for_date(
    date_str: str, difficulty: str = DIFF_FACIL, banned_words: Optional[Iterable[str]] = None
) -> Dict[str, Any]:
    """Genera la configuración determinista del Crucigrama para una fecha y dificultad."""
    diff = (difficulty or DIFF_FACIL).lower().strip()
    rng = random.Random(f"crucigrama_{date_str}_{diff}")
    banned = normalize_banned(banned_words)
    if diff == DIFF_DIFICIL:
        theme, final_grid = _generate_dificil(date_str, rng, banned)
        challenge = _parse_and_build_challenge(theme, final_grid, prefer_curated=False)
    else:
        theme, final_grid = _generate_facil(date_str, rng, banned)
        challenge = _parse_and_build_challenge(theme, final_grid, prefer_curated=True)

    infractoras = sorted({w["word"] for w in challenge.get("words", [])} & banned)
    if infractoras:
        logger.warning(
            f"[CRUCIGRAMA] {date_str} ({diff}): tablero de respaldo con palabras vetadas: {', '.join(infractoras)}."
        )
    challenge["date"] = date_str
    return challenge
