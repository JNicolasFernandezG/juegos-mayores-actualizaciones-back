"""
validator.py
Validación de plantillas de crucigrama para el diseñador administrativo.

Capa 1 - estructura: tamaño, caracteres, rachas de 3 a 10 letras, cobertura de
                     celdas, cantidad mínima de palabras y tope recomendado de
                     palabras de 3 letras.
Capa 2 - solubilidad: reintentos deterministas del solver con presupuesto de
                     nodos creciente, para no descartar un tablero por mala
                     suerte del primer intento.

El informe es serializable y está pensado para el panel de administración.
"""

import hashlib
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from app.features.daily_challenges.crucigrama.solver import (
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    _parse_template_slots,
    _solve_crucigrama_backtracking,
    normalize_preassigned,
    normalize_word,
)
from app.features.daily_challenges.crucigrama.solver_bitset import solve_with_bitsets

SIZES = (7, 11)
MIN_WORDS_BY_SIZE = {7: 5, 11: 12}
MAX_THREE_LETTER = 6

# Seis intentos con presupuesto creciente: en el experimento, cinco semillas a
# 200k nodos resolvieron todas las máscaras realistas.
ATTEMPT_BUDGETS = (150_000, 150_000, 300_000, 300_000, 600_000, 600_000)

# El motor AC-3 resuelve máscaras normales en decenas de nodos; el límite duro
# es de tiempo porque cada nodo propaga dominios completos.
BITSET_ATTEMPT_SECONDS = (10.0, 20.0)


def _runs(pattern: List[str]) -> Tuple[List[int], List[int]]:
    R, C = len(pattern), len(pattern[0])
    horizontales: List[int] = []
    verticales: List[int] = []
    for r in range(R):
        c = 0
        while c < C:
            if pattern[r][c] == ".":
                s = c
                while c < C and pattern[r][c] == ".":
                    c += 1
                horizontales.append(c - s)
            else:
                c += 1
    for c in range(C):
        r = 0
        while r < R:
            if pattern[r][c] == ".":
                s = r
                while r < R and pattern[r][c] == ".":
                    r += 1
                verticales.append(r - s)
            else:
                r += 1
    return horizontales, verticales


def _is_symmetric(pattern: List[str]) -> bool:
    R, C = len(pattern), len(pattern[0])
    return all(
        pattern[r][c] == pattern[R - 1 - r][C - 1 - c]
        for r in range(R)
        for c in range(C)
    )


def _structural_report(pattern: Any) -> Tuple[List[str], List[str], Dict[str, Any]]:
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {
        "words": 0,
        "three_letter_words": 0,
        "slot_lengths": {},
    }

    if not isinstance(pattern, list) or not pattern:
        return ["El patrón debe ser una lista de filas no vacía."], warnings, stats
    if any(not isinstance(row, str) for row in pattern):
        return ["Cada fila del patrón debe ser un string."], warnings, stats

    largos = {len(row) for row in pattern}
    if len(largos) != 1:
        return ["Todas las filas deben tener el mismo largo."], warnings, stats
    C = largos.pop()
    R = len(pattern)
    if C == 0:
        return ["El patrón no puede tener filas vacías."], warnings, stats
    if R != C:
        errors.append(f"El tablero debe ser cuadrado (recibido {R}x{C}).")
    if R not in SIZES:
        errors.append(f"Tamaño no soportado: {R}x{C}. Permitidos: {list(SIZES)}.")

    invalidos = set("".join(pattern)) - {".", "#"}
    if invalidos:
        errors.append(f"Caracteres inválidos: {sorted(invalidos)}. Solo se admite '.' y '#'.")

    horizontales, verticales = _runs(pattern)
    largos_racha = horizontales + verticales
    if any(largo == 2 for largo in largos_racha):
        errors.append("Hay palabras de 2 letras; el mínimo es 3.")
    if any(largo > MAX_WORD_LEN for largo in largos_racha):
        errors.append(f"Hay palabras de más de {MAX_WORD_LEN} letras.")

    slots, _ = _parse_template_slots(pattern)
    slot_lengths: Dict[int, int] = {}
    for slot in slots:
        slot_lengths[slot["len"]] = slot_lengths.get(slot["len"], 0) + 1
    stats["words"] = len(slots)
    stats["three_letter_words"] = slot_lengths.get(3, 0)
    stats["slot_lengths"] = dict(sorted(slot_lengths.items()))

    minimo = MIN_WORDS_BY_SIZE.get(R, 12)
    if len(slots) < minimo:
        errors.append(f"Se esperaban al menos {minimo} palabras; hay {len(slots)}.")
    if slot_lengths.get(3, 0) > MAX_THREE_LETTER:
        warnings.append(
            f"{slot_lengths.get(3, 0)} palabras de 3 letras (recomendado {MAX_THREE_LETTER} o menos)."
        )

    cubiertas = set()
    for slot in slots:
        cubiertas.update(slot["coords"])
    letras = {
        (r, c) for r in range(R) for c in range(C) if pattern[r][c] == "."
    }
    sin_palabra = letras - cubiertas
    if sin_palabra:
        errors.append(
            f"{len(sin_palabra)} celdas de letra aisladas: no forman parte de ninguna palabra."
        )

    if not _is_symmetric(pattern):
        warnings.append("El tablero no es simétrico (rotación de 180°).")

    return errors, warnings, stats


def _solution_grid(
    pattern: List[str], slots: List[Dict[str, Any]], assignment: Dict[str, str]
) -> Optional[List[str]]:
    R, C = len(pattern), len(pattern[0])
    grid = [["#" if pattern[r][c] == "#" else "" for c in range(C)] for r in range(R)]
    for slot in slots:
        palabra = assignment.get(slot["id"])
        if palabra is None:
            return None
        for (r, c), ch in zip(slot["coords"], palabra):
            grid[r][c] = ch
    if any(grid[r][c] == "" for r in range(R) for c in range(C)):
        return None
    return ["".join(row) for row in grid]


def _slots_public(slots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Vista serializable de los slots para que el panel pueda ofrecer anclas."""
    return [
        {
            "id": s["id"],
            "direction": s["dir"],
            "row": s["r"],
            "col": s["c"],
            "length": s["len"],
            "crossings": 0,
        }
        for s in slots
    ]


def validate_structure(
    pattern: Any,
    anchors: Optional[Dict[str, str]] = None,
    fixed_words: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Validación estructural (sin solver): tamaño, caracteres, rachas, cobertura,
    mínimos y consistencia de las anclas. Devuelve el mismo informe base que
    `validate_pattern` con `solvable=False`.

    `anchors` son las palabras persistentes del diseñador; `fixed_words` son
    fijaciones temporales (por ejemplo, al reemplazar una palabra de la
    solución). Ambas se validan juntas contra cruces y léxico.
    """
    errors, warnings, stats = _structural_report(pattern)

    report: Dict[str, Any] = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        **stats,
        "slots": [],
        "anchors": {},
        "fixed_words": {},
        "banned_words": [],
        "seed": None,
        "engine": None,
        "solvable": False,
        "solution": None,
        "attempts": 0,
    }

    if errors:
        return report

    slots, intersections = _parse_template_slots(pattern)
    public_slots = _slots_public(slots)
    crossing_count = {s["id"]: len(intersections[s["id"]]) for s in slots}
    for slot in public_slots:
        slot["crossings"] = crossing_count.get(slot["id"], 0)
    report["slots"] = public_slots

    merged_raw: Dict[str, str] = dict(anchors or {})
    en_conflicto = []
    for slot_id, word in (fixed_words or {}).items():
        if slot_id in merged_raw and normalize_word(merged_raw[slot_id]) != normalize_word(word):
            en_conflicto.append(slot_id)
        merged_raw[slot_id] = word
    if en_conflicto:
        report["valid"] = False
        report["errors"].append(
            f"El slot '{en_conflicto[0]}' tiene un ancla y una palabra fijada distintas."
        )

    try:
        normalizadas = normalize_preassigned(merged_raw, slots, intersections)
        report["anchors"] = {
            slot_id: word for slot_id, word in normalizadas.items() if slot_id in (anchors or {})
        }
        report["fixed_words"] = {
            slot_id: word
            for slot_id, word in normalizadas.items()
            if slot_id in (fixed_words or {})
        }
    except ValueError as exc:
        report["valid"] = False
        report["errors"].append(str(exc))

    return report


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
    """
    Valida estructura y solubilidad de un patrón.

    `anchors` fija palabras por slot_id (máximo recomendado: 2 anclas en slots
    centrales); `fixed_words` fija palabras temporales para reemplazos.
    `banned_words` excluye palabras del pool de candidatos.
    `seed` cambia el orden de exploración: misma máscara + misma seed + mismos
    vetos produce la misma solución; cambiando la seed cambia la solución.
    `engine="bitset"` usa AC-3 + MRV (máscaras densas del panel admin);
    `attempt_budgets` solo aplica al motor de backtracking.

    Devuelve un informe serializable con `valid`, `solvable`, `solution`
    (lista de filas resueltas), `slots`, `anchors`, `fixed_words`,
    `banned_words`, `engine` y métricas de intentos.
    """
    started = time.perf_counter()
    report = validate_structure(pattern, anchors, fixed_words)

    banned = sorted({normalize_word(word) for word in (banned_words or []) if normalize_word(word)})
    report["banned_words"] = banned
    report["seed"] = seed
    report["engine"] = engine
    fijadas = {**report["anchors"], **report["fixed_words"]}

    en_conflicto = sorted(set(fijadas.values()) & set(banned))
    if en_conflicto:
        report["valid"] = False
        report["errors"].append(
            f"La palabra '{en_conflicto[0]}' está fijada y vetada al mismo tiempo."
        )

    if not report["valid"]:
        report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return report

    slots, intersections = _parse_template_slots(pattern)
    digest_src = "|".join(pattern)
    if fijadas:
        digest_src += "||" + "|".join(f"{k}={v}" for k, v in sorted(fijadas.items()))
    if banned:
        digest_src += "||banned=" + ",".join(banned)
    if seed:
        digest_src += f"||seed={seed}"
    digest = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:12]
    budgets = attempt_budgets or ATTEMPT_BUDGETS

    assignment = None
    intentos = 0
    if engine == "bitset":
        for i, max_seconds in enumerate(BITSET_ATTEMPT_SECONDS):
            intentos = i + 1
            rng = random.Random(f"{digest}:{i}")
            assignment = solve_with_bitsets(
                slots,
                intersections,
                rng,
                prefer_curated=prefer_curated,
                max_seconds=max_seconds,
                preassigned=fijadas,
                banned_words=set(banned),
            )
            if assignment is not None:
                break
    else:
        for i, budget in enumerate(budgets):
            intentos = i + 1
            rng = random.Random(f"{digest}:{i}")
            assignment = _solve_crucigrama_backtracking(
                slots,
                intersections,
                rng,
                prefer_curated=prefer_curated,
                max_nodes=budget,
                preassigned=fijadas,
                banned_words=set(banned),
            )
            if assignment is not None:
                break

    report["attempts"] = intentos
    if assignment is not None:
        grid = _solution_grid(pattern, slots, assignment)
        if grid is None:
            report["valid"] = False
            report["errors"].append("El solver devolvió una solución incompleta.")
        else:
            report["solvable"] = True
            report["solution"] = grid
            report["solution_words"] = dict(assignment)
    else:
        if fijadas:
            report["warnings"].append(
                "No se encontró solución con las palabras fijadas. "
                "Probá quitando o cambiando una de las anclas o reemplazos."
            )

    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return report
