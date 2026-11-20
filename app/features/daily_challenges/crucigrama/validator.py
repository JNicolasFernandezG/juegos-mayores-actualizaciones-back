"""
validator.py
Validación de plantillas de crucigrama para el diseñador administrativo.

Capa 1 - estructura (en structure_validator.py): tamaño, caracteres, rachas de
         3 a 11 letras, cobertura, cantidad mínima de palabras y anclas.
Capa 2 - solubilidad: reintentos deterministas del solver con presupuesto creciente.
"""

import hashlib
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from app.features.daily_challenges.crucigrama.lexicon import (
    build_solution_grid,
    normalize_banned,
    prepare_anchors_and_bans,
)
from app.features.daily_challenges.crucigrama.solver import _solve_crucigrama_backtracking
from app.features.daily_challenges.crucigrama.solver_bitset import solve_with_bitsets
from app.features.daily_challenges.crucigrama.structure_validator import (  # noqa: F401
    MAX_THREE_LETTER,
    MIN_WORDS_BY_SIZE,
    SIZES,
    _is_symmetric,
    _slots_public,
    _structural_report,
    _validate_structure_with_slots,
    validate_structure,
)

# Seis intentos con presupuesto creciente: cinco semillas a 200k resolvieron todas las máscaras.
ATTEMPT_BUDGETS = (150_000, 150_000, 300_000, 300_000, 600_000, 600_000)

# El motor AC-3 resuelve máscaras normales en decenas de nodos; límite duro de tiempo.
BITSET_ATTEMPT_SECONDS = (10.0, 20.0)

_solution_grid = build_solution_grid


def _pattern_digest(
    pattern: List[str],
    fijadas: Dict[str, str],
    banned: List[str],
    seed: Optional[str],
) -> str:
    digest_src = "|".join(pattern)
    if fijadas:
        digest_src += "||" + "|".join(f"{k}={v}" for k, v in sorted(fijadas.items()))
    if banned:
        digest_src += "||banned=" + ",".join(banned)
    if seed:
        digest_src += f"||seed={seed}"
    return hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:12]


def _run_solver_attempts(
    slots: List[Dict],
    intersections: Dict[str, List[Tuple[int, str, int]]],
    digest: str,
    engine: str,
    prefer_curated: bool,
    budgets: Tuple[int, ...],
    fijadas: Dict[str, str],
    banned: List[str],
) -> Tuple[Optional[Dict[str, str]], int]:
    banned_set = set(banned)
    assignment = None
    attempts = 0
    schedule: Tuple[Any, ...] = BITSET_ATTEMPT_SECONDS if engine == "bitset" else budgets
    for i, limit in enumerate(schedule):
        attempts = i + 1
        rng = random.Random(f"{digest}:{i}")
        if engine == "bitset":
            assignment = solve_with_bitsets(
                slots, intersections, rng, prefer_curated=prefer_curated,
                max_seconds=limit, preassigned=fijadas, banned_words=banned_set,
            )
        else:
            assignment = _solve_crucigrama_backtracking(
                slots, intersections, rng, prefer_curated=prefer_curated,
                max_nodes=limit, preassigned=fijadas, banned_words=banned_set,
            )
        if assignment is not None:
            break
    return assignment, attempts


def validate_pattern(
    pattern: Any,
    prefer_curated: bool = False,
    attempt_budgets: Optional[Tuple[int, ...]] = None,
    anchors: Optional[Dict[str, str]] = None,
    fixed_words: Optional[Dict[str, str]] = None,
    seed: Optional[str] = None,
    banned_words: Optional[List[str]] = None,
    engine: str = "backtracking",
) -> Dict[str, Any]:
    """Valida estructura y solubilidad de un patrón para el panel administrativo."""
    started = time.perf_counter()
    report, parsed = _validate_structure_with_slots(pattern, anchors, fixed_words)
    banned = sorted(normalize_banned(banned_words))
    report.update({"banned_words": banned, "seed": seed, "engine": engine})
    fijadas = {**report["anchors"], **report["fixed_words"]}

    try:
        prepare_anchors_and_bans(fijadas, banned, [], {}, already_normalized=True)
    except ValueError as exc:
        report["valid"] = False
        report["errors"].append(str(exc))

    if not report["valid"] or parsed is None:
        report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return report

    slots, intersections = parsed
    digest = _pattern_digest(pattern, fijadas, banned, seed)
    assignment, attempts = _run_solver_attempts(
        slots, intersections, digest, engine, prefer_curated,
        attempt_budgets or ATTEMPT_BUDGETS, fijadas, banned,
    )
    report["attempts"] = attempts
    if assignment is not None:
        grid = build_solution_grid(pattern, slots, assignment)
        if grid is None:
            report["valid"] = False
            report["errors"].append("El solver devolvió una solución incompleta.")
        else:
            report.update({"solvable": True, "solution": grid, "solution_words": dict(assignment)})
    elif fijadas:
        report["warnings"].append(
            "No se encontró solución con las palabras fijadas. "
            "Probá quitando o cambiando una de las anclas o reemplazos."
        )

    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return report
