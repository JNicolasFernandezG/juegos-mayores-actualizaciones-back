"""Validación de máscaras, soluciones y consulta RAE para el panel admin de crucigrama."""

import concurrent.futures
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core.config import settings
from app.core.rae_client import get_masked_definition
from app.features.daily_challenges.crucigrama.generator import build_challenge_from_solution
from app.features.daily_challenges.crucigrama.published_templates import prefer_curated as _prefer_curated
from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    is_known_word,
    normalize_word,
)
from app.features.daily_challenges.crucigrama.validator import (
    validate_pattern,
    validate_structure,
)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _assert_future_date(date_str: str) -> None:
    if date_str < _today():
        raise HTTPException(
            status_code=400,
            detail=f"La fecha {date_str} ya pasó; elegí hoy o una fecha futura.",
        )


def _assert_structure(
    pattern: List[str],
    anchors: Dict[str, str],
    validate_structure_fn: Callable[[List[str], Dict[str, str]], Dict[str, Any]] = validate_structure,
) -> Dict[str, Any]:
    report = validate_structure_fn(pattern, anchors)
    if not report["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "La máscara no es válida.",
                "errors": report["errors"],
            },
        )
    return report


def _assert_solution_matches_pattern(pattern: List[str], solution: List[str]) -> None:
    if len(solution) != len(pattern):
        raise HTTPException(status_code=500, detail="La solución no coincide con la máscara.")
    for r, row in enumerate(pattern):
        if len(solution[r]) != len(row):
            raise HTTPException(status_code=500, detail="La solución no coincide con la máscara.")
        for c, ch in enumerate(row):
            es_bloque = solution[r][c] == "#"
            if (ch == "#") != es_bloque:
                raise HTTPException(
                    status_code=500,
                    detail=f"La solución no respeta los bloques de la máscara en ({r}, {c}).",
                )


def _normalize_solution_rows(pattern: List[str], solution: List[str]) -> List[str]:
    if not isinstance(solution, list) or len(solution) != len(pattern):
        raise HTTPException(
            status_code=400,
            detail="La solución no coincide con la máscara; volvé a resolverla antes de publicar.",
        )

    rows = len(pattern)
    cols = len(pattern[0]) if rows else 0
    grid: List[str] = []
    for r in range(rows):
        fila = solution[r]
        if not isinstance(fila, str) or len(fila) != cols:
            raise HTTPException(
                status_code=400,
                detail=f"La fila {r + 1} de la solución no tiene el ancho de la máscara.",
            )
        letras: List[str] = []
        for c in range(cols):
            if pattern[r][c] == "#":
                if fila[c] != "#":
                    raise HTTPException(
                        status_code=400,
                        detail=f"La solución no respeta el bloque de la máscara en ({r}, {c}).",
                    )
                letras.append("#")
                continue
            letra = normalize_word(fila[c])
            if len(letra) != 1 or not letra.isalpha():
                raise HTTPException(
                    status_code=400,
                    detail=f"La celda ({r}, {c}) de la solución no es una letra válida.",
                )
            letras.append(letra)
        grid.append("".join(letras))
    return grid


def _validate_solution_words(
    pattern: List[str],
    grid: List[str],
    anchors: Dict[str, str],
    banned_words: List[str],
) -> Dict[str, str]:
    slots, _ = _parse_template_slots(pattern)
    banned = {normalize_word(word) for word in (banned_words or [])}
    vistas = set()
    asignacion: Dict[str, str] = {}
    for slot in slots:
        word = "".join(grid[r][c] for r, c in slot["coords"])
        if not is_known_word(word):
            raise HTTPException(
                status_code=400,
                detail=f"La palabra '{word}' del slot '{slot['id']}' no está en el léxico del juego.",
            )
        if word in vistas:
            raise HTTPException(
                status_code=400,
                detail=f"La palabra '{word}' aparece más de una vez en la solución.",
            )
        if word in banned:
            raise HTTPException(
                status_code=400,
                detail=f"La palabra '{word}' está vetada y no puede publicarse.",
            )
        vistas.add(word)
        asignacion[slot["id"]] = word

    for slot_id, word in (anchors or {}).items():
        if asignacion.get(slot_id) != word:
            raise HTTPException(
                status_code=400,
                detail=f"La solución no respeta el ancla '{word}' del slot '{slot_id}'.",
            )
    return asignacion


def _validate_solution_grid(
    pattern: List[str],
    solution: List[str],
    anchors: Dict[str, str],
    banned_words: List[str],
) -> Tuple[List[str], Dict[str, str]]:
    """Valida una solución aprobada por el operador.

    Verifica bloques, letras válidas, léxico, ausencia de repeticiones,
    palabras vetadas y respeto por las anclas fijadas.
    """
    grid = _normalize_solution_rows(pattern, solution)
    asignacion = _validate_solution_words(pattern, grid, anchors, banned_words)
    return grid, asignacion


def validate_mask(
    payload: Any,
    global_banned_words: Optional[List[str]] = None,
    validate_pattern_fn: Callable[..., Dict[str, Any]] = validate_pattern,
    prefer_curated_fn: Callable[[str, Optional[bool]], bool] = _prefer_curated,
) -> Dict[str, Any]:
    """Valida estructura + solubilidad sin persistir nada.

    Los vetos globales se suman a los de la plantilla: el reporte devuelve ambos
    por separado para que el panel distinga cuáles puede quitar.
    """
    global_bans = sorted(
        {normalize_word(w) for w in (global_banned_words or []) if normalize_word(w)}
    )
    prefer_curated = prefer_curated_fn(payload.difficulty or "facil", payload.prefer_curated)
    report = validate_pattern_fn(
        payload.pattern,
        prefer_curated=prefer_curated,
        attempt_budgets=tuple(payload.attempt_budgets) if payload.attempt_budgets else None,
        anchors=payload.anchors,
        fixed_words=payload.fixed_words,
        seed=payload.seed,
        banned_words=[*payload.banned_words, *global_bans],
        engine="bitset",
    )
    excluidas = set(global_bans)
    report["banned_words"] = [
        word for word in report.get("banned_words", []) if word not in excluidas
    ]
    report["global_banned_words"] = global_bans
    report["prefer_curated"] = prefer_curated
    report["difficulty"] = payload.difficulty
    return report


def _solve_pattern_for_publish(
    pattern: List[str],
    anchors: Dict[str, str],
    prefer_curated: bool,
    seed: Optional[str],
    banned_validacion: List[str],
    validate_pattern_fn: Callable[..., Dict[str, Any]],
) -> List[str]:
    validation = validate_pattern_fn(
        pattern,
        prefer_curated=prefer_curated,
        anchors=anchors,
        seed=seed,
        banned_words=banned_validacion,
        engine="bitset",
    )
    if not validation["solvable"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "La máscara no tiene solución con los intentos disponibles; no se publicó.",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "attempts": validation["attempts"],
                "elapsed_ms": validation["elapsed_ms"],
            },
        )
    solution_grid = validation["solution"]
    _assert_solution_matches_pattern(pattern, solution_grid)
    return solution_grid


def resolve_publish_solution(
    doc: Dict[str, Any],
    payload: Any,
    global_bans: List[str],
    validate_structure_fn: Callable[[List[str], Dict[str, str]], Dict[str, Any]] = validate_structure,
    validate_pattern_fn: Callable[..., Dict[str, Any]] = validate_pattern,
    prefer_curated_fn: Callable[[str, Optional[bool]], bool] = _prefer_curated,
) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, Any]]:
    """Valida o resuelve la grilla y construye la configuración publicable."""
    pattern = doc.get("pattern") or []
    difficulty = doc.get("difficulty") or "facil"
    report = _assert_structure(pattern, doc.get("anchors") or {}, validate_structure_fn=validate_structure_fn)
    prefer_curated = prefer_curated_fn(difficulty, payload.prefer_curated)
    banned_words = (
        payload.banned_words
        if "banned_words" in payload.model_fields_set
        else (doc.get("banned_words") or [])
    )
    banned_validacion = sorted({normalize_word(word) for word in [*banned_words, *global_bans]})

    if payload.solution_grid:
        solution_grid, _ = _validate_solution_grid(
            pattern, payload.solution_grid, report["anchors"], banned_validacion
        )
    else:
        solution_grid = _solve_pattern_for_publish(
            pattern, report["anchors"], prefer_curated, payload.seed, banned_validacion, validate_pattern_fn
        )

    theme = doc.get("theme") or "Palabras Cruzadas"
    config = build_challenge_from_solution(
        theme, solution_grid, prefer_curated=prefer_curated, clue_overrides=doc.get("clue_overrides") or {}
    )
    return report, banned_words, solution_grid, config


def lookup_definition(
    word: str,
    get_masked_definition_fn: Callable[[str], Optional[str]] = get_masked_definition,
) -> Dict[str, Any]:
    """Definición RAE (con la palabra tapada) para una palabra del diseñador."""
    limpia = normalize_word(word)
    if not limpia or not limpia.isalpha() or not (2 <= len(limpia) <= 15):
        raise HTTPException(
            status_code=400, detail="La palabra debe tener entre 2 y 15 letras."
        )
    definition = get_masked_definition_fn(limpia)
    return {"word": limpia, "definition": definition, "found": bool(definition)}


def lookup_definitions(
    words: List[str],
    get_masked_definition_fn: Callable[[str], Optional[str]] = get_masked_definition,
) -> Dict[str, Any]:
    """Definiciones RAE en lote para autocompletar pistas."""
    unicas: List[str] = []
    for raw in words:
        word = normalize_word(raw)
        if word and word not in unicas:
            unicas.append(word)
    if not unicas:
        return {"definitions": {}, "missing": []}

    trabajadores = max(1, min(settings.RAE_MAX_CONCURRENCY, len(unicas)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=trabajadores) as executor:
        resultados = list(executor.map(get_masked_definition_fn, unicas))

    definitions = {w: d for w, d in zip(unicas, resultados) if d}
    missing = [w for w, d in zip(unicas, resultados) if not d]
    return {"definitions": definitions, "missing": missing}
