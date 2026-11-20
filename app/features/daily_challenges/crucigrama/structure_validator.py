"""
structure_validator.py
Capa 1 de validación de plantillas de crucigrama: estructura geométrica,
cobertura de celdas, simetría y validación de palabras ancla/fijas.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.features.daily_challenges.crucigrama.lexicon import (
    MAX_WORD_LEN,
    _parse_template_slots,
    normalize_preassigned,
    normalize_word,
)

SIZES = (7, 11)
MIN_WORDS_BY_SIZE = {7: 5, 11: 12}
MAX_THREE_LETTER = 6


def _is_symmetric(pattern: List[str]) -> bool:
    rows = len(pattern)
    cols = len(pattern[0])
    return all(
        pattern[r][c] == pattern[rows - 1 - r][cols - 1 - c]
        for r in range(rows)
        for c in range(cols)
    )


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


def _validate_basic_shape(pattern: Any) -> Tuple[Optional[str], int, int]:
    if not isinstance(pattern, list) or not pattern:
        return "El patrón debe ser una lista de filas no vacía.", 0, 0
    if any(not isinstance(row, str) for row in pattern):
        return "Cada fila del patrón debe ser un string.", 0, 0
    lengths = {len(row) for row in pattern}
    if len(lengths) != 1:
        return "Todas las filas deben tener el mismo largo.", 0, 0
    cols = lengths.pop()
    if cols == 0:
        return "El patrón no puede tener filas vacías.", 0, 0
    return None, len(pattern), cols


def _collect_slot_metrics(
    pattern: List[str], rows: int, cols: int, errors: List[str], warnings: List[str]
) -> Tuple[Dict[str, Any], Tuple[List[Dict], Dict]]:
    slots, intersections = _parse_template_slots(pattern)
    slot_lengths: Dict[int, int] = {}
    for slot in slots:
        slot_lengths[slot["len"]] = slot_lengths.get(slot["len"], 0) + 1
    if any(length == 2 for length in slot_lengths):
        errors.append("Hay palabras de 2 letras; el mínimo es 3.")
    if any(length > MAX_WORD_LEN for length in slot_lengths):
        errors.append(f"Hay palabras de más de {MAX_WORD_LEN} letras.")

    three_count = slot_lengths.get(3, 0)
    stats: Dict[str, Any] = {
        "words": len(slots),
        "three_letter_words": three_count,
        "slot_lengths": dict(sorted(slot_lengths.items())),
    }
    minimo = MIN_WORDS_BY_SIZE.get(rows, 12)
    if len(slots) < minimo:
        errors.append(f"Se esperaban al menos {minimo} palabras; hay {len(slots)}.")
    if three_count > MAX_THREE_LETTER:
        warnings.append(f"{three_count} palabras de 3 letras (recomendado {MAX_THREE_LETTER} o menos).")

    covered = {coord for slot in slots for coord in slot["coords"]}
    letters = {(r, c) for r in range(rows) for c in range(cols) if pattern[r][c] == "."}
    isolated = letters - covered
    if isolated:
        errors.append(f"{len(isolated)} celdas de letra aisladas: no forman parte de ninguna palabra.")
    return stats, (slots, intersections)


def _analyze_structure(
    pattern: Any,
) -> Tuple[List[str], List[str], Dict[str, Any], Optional[Tuple[List[Dict], Dict]]]:
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {"words": 0, "three_letter_words": 0, "slot_lengths": {}}

    shape_error, rows, cols = _validate_basic_shape(pattern)
    if shape_error:
        return [shape_error], warnings, stats, None
    if rows != cols:
        errors.append(f"El tablero debe ser cuadrado (recibido {rows}x{cols}).")
    if rows not in SIZES:
        errors.append(f"Tamaño no soportado: {rows}x{cols}. Permitidos: {list(SIZES)}.")
    invalid = set("".join(pattern)) - {".", "#"}
    if invalid:
        errors.append(f"Caracteres inválidos: {sorted(invalid)}. Solo se admite '.' y '#'.")

    stats, parsed = _collect_slot_metrics(pattern, rows, cols, errors, warnings)
    if not _is_symmetric(pattern):
        warnings.append("El tablero no es simétrico (rotación de 180°).")
    return errors, warnings, stats, parsed


def _structural_report(pattern: Any) -> Tuple[List[str], List[str], Dict[str, Any]]:
    errors, warnings, stats, _ = _analyze_structure(pattern)
    return errors, warnings, stats


def _validate_structure_with_slots(
    pattern: Any,
    anchors: Optional[Dict[str, str]] = None,
    fixed_words: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Any], Optional[Tuple[List[Dict], Dict]]]:
    errors, warnings, stats, parsed = _analyze_structure(pattern)
    report: Dict[str, Any] = {
        "valid": not errors, "errors": errors, "warnings": warnings, **stats,
        "slots": [], "anchors": {}, "fixed_words": {}, "banned_words": [],
        "seed": None, "engine": None, "solvable": False, "solution": None, "attempts": 0,
    }
    if errors or parsed is None:
        return report, None

    slots, intersections = parsed
    public_slots = _slots_public(slots)
    for slot in public_slots:
        slot["crossings"] = len(intersections.get(slot["id"], ()))
    report["slots"] = public_slots

    merged_raw: Dict[str, str] = dict(anchors or {})
    conflicts = []
    for slot_id, word in (fixed_words or {}).items():
        if slot_id in merged_raw and normalize_word(merged_raw[slot_id]) != normalize_word(word):
            conflicts.append(slot_id)
        merged_raw[slot_id] = word
    if conflicts:
        report["valid"] = False
        report["errors"].append(
            f"El slot '{conflicts[0]}' tiene un ancla y una palabra fijada distintas."
        )

    try:
        normalized = normalize_preassigned(merged_raw, slots, intersections)
        report["anchors"] = {k: v for k, v in normalized.items() if k in (anchors or {})}
        report["fixed_words"] = {k: v for k, v in normalized.items() if k in (fixed_words or {})}
    except ValueError as exc:
        report["valid"] = False
        report["errors"].append(str(exc))

    return report, parsed


def validate_structure(
    pattern: Any,
    anchors: Optional[Dict[str, str]] = None,
    fixed_words: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Validación estructural (sin solver): tamaño, caracteres, rachas, cobertura,
    mínimos y consistencia de las anclas.
    """
    report, _ = _validate_structure_with_slots(pattern, anchors, fixed_words)
    return report
