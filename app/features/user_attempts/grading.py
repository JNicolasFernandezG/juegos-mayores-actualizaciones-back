"""Cálculo de calificación, puntaje y estrellas de intentos de juego."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.shared.economy_points import DEFAULT_PUNTOS_POR_CALIFICACION

_TIMED_GAMES = ("sudoku", "crucigrama", "sopa_letras")


def _tier_value(tier: Any, name: str, default: Any) -> Any:
    if isinstance(tier, dict):
        return tier.get(name, default)
    return getattr(tier, name, default)


def _parse_errors(game_data: Optional[Dict[str, Any]]) -> int:
    data = game_data or {}
    raw = data.get("errors", data.get("mistakes", data.get("fallos", 0)))
    if raw is None or raw == "":
        return 0
    if isinstance(raw, bool):
        raise HTTPException(
            status_code=400,
            detail="'game_data.errors' debe ser un número entero.",
        )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="'game_data.errors' debe ser un número entero.",
        )
    if value < 0:
        raise HTTPException(
            status_code=400,
            detail="'game_data.errors' no puede ser negativo.",
        )
    return value


def _grade_from_time_scales(
    time_taken_seconds: int,
    escalas_tiempo: Optional[List[Any]],
) -> Optional[Tuple[str, int, int]]:
    if not escalas_tiempo:
        return None
    escalas_ordenadas = sorted(
        escalas_tiempo,
        key=lambda item: _tier_value(item, "tiempo_max_segundos", 999999),
    )
    matched_tier = next(
        (
            tier
            for tier in escalas_ordenadas
            if time_taken_seconds <= _tier_value(tier, "tiempo_max_segundos", 999999)
        ),
        escalas_ordenadas[-1],
    )
    return (
        _tier_value(matched_tier, "grade", "C"),
        _tier_value(matched_tier, "puntos", 50),
        _tier_value(matched_tier, "estrellas", 1),
    )


def _resolve_score_and_stars(
    grade: str,
    config_pts: Dict[str, int],
    provided_score: Optional[int],
    provided_stars: Optional[int],
    default_stars: int,
) -> Tuple[str, int, int]:
    fallback = provided_score if (provided_score is not None and provided_score > 0) else 50
    score = config_pts.get(grade, fallback)
    if provided_stars is not None and provided_stars > 0:
        stars = min(3, max(1, provided_stars))
    else:
        stars = default_stars
    return (grade, score, stars)


def _grade_wordle(attempts: int, _remaining: int, _errors: int) -> Optional[Tuple[str, int]]:
    # Wordle tiene 6 intentos máximos.
    if attempts <= 2:
        return ("S", 3)
    if attempts <= 4:
        return ("B", 2)
    if attempts <= 6:
        return ("C", 1)
    return None


def _grade_sudoku(_attempts: int, remaining_attempts: int, errors: int) -> Tuple[str, int]:
    # Sudoku: los errores mandan; 0 vidas restantes nunca es S.
    if errors == 0 and remaining_attempts >= 3:
        return ("S", 3)
    if errors <= 1 or remaining_attempts == 2:
        return ("B", 2)
    return ("C", 1)


def _grade_by_errors(_attempts: int, _remaining: int, errors: int) -> Tuple[str, int]:
    # Crucigrama y sopa de letras: errores al verificar / seleccionar.
    if errors == 0:
        return ("S", 3)
    if errors <= 2:
        return ("B", 2)
    return ("C", 1)


def _grade_generic(attempts: int, remaining_attempts: int, _errors: int) -> Tuple[str, int]:
    if remaining_attempts >= 3 or attempts <= 2:
        return ("S", 3)
    if remaining_attempts >= 1 or attempts <= 4:
        return ("B", 2)
    return ("C", 1)


_GAME_GRADERS: Dict[str, Callable[[int, int, int], Optional[Tuple[str, int]]]] = {
    "wordle": _grade_wordle,
    "sudoku": _grade_sudoku,
    "crucigrama": _grade_by_errors,
    "sopa_letras": _grade_by_errors,
}


def _grade_completed_attempt(
    gid: str,
    attempts: int,
    remaining_attempts: int,
    provided_grade: Optional[str],
    provided_score: Optional[int],
    provided_stars: Optional[int],
    config_pts: Dict[str, int],
    game_data: Optional[dict],
    time_taken_seconds: Optional[int],
    escalas_tiempo: Optional[List[Any]],
) -> Tuple[str, int, int]:
    # 1. Calificación por Tiempo (juegos cronometrados: sudoku, crucigrama, sopa_letras)
    if gid in _TIMED_GAMES and time_taken_seconds is not None and time_taken_seconds >= 0:
        timed_result = _grade_from_time_scales(time_taken_seconds, escalas_tiempo)
        if timed_result is not None:
            return timed_result

    # 2. Si el frontend envía una calificación por letra explícita
    if provided_grade and provided_grade.upper().strip() in config_pts:
        grade = provided_grade.upper().strip()
        default_stars = 3 if grade in ("S", "A") else (2 if grade == "B" else 1)
        return _resolve_score_and_stars(
            grade, config_pts, provided_score, provided_stars, default_stars
        )

    # 3. Si no vino calificación explícita, evaluar por juego y vidas/errores
    errors = _parse_errors(game_data)
    grader = _GAME_GRADERS.get(gid, _grade_generic)
    outcome = grader(attempts, remaining_attempts, errors)
    if outcome is None:
        return ("F", 0, 0)

    grade, default_stars = outcome
    return _resolve_score_and_stars(
        grade, config_pts, provided_score, provided_stars, default_stars
    )


def calculate_grade_and_score(
    game_id: str,
    status: str,
    attempts: int,
    remaining_attempts: int,
    provided_grade: Optional[str] = None,
    provided_score: Optional[int] = None,
    provided_stars: Optional[int] = None,
    puntos_por_calificacion: Optional[Dict[str, int]] = None,
    game_data: Optional[dict] = None,
    time_taken_seconds: Optional[int] = None,
    escalas_tiempo: Optional[List[Any]] = None,
) -> Tuple[str, int, int]:
    """Calcula (grade, score, stars) en base al desempeño o configuración."""
    status_clean = (status or "").lower().strip()
    config_pts = puntos_por_calificacion or DEFAULT_PUNTOS_POR_CALIFICACION

    # Si la partida falló o se agotaron los intentos/vidas
    if status_clean in ("failed", "lost"):
        return ("F", 0, 0)

    # Si es solo un guardado intermedio
    if status_clean not in ("completed", "won"):
        return (provided_grade or "C", 0, 0)

    return _grade_completed_attempt(
        (game_id or "").lower().strip(),
        attempts,
        remaining_attempts,
        provided_grade,
        provided_score,
        provided_stars,
        config_pts,
        game_data,
        time_taken_seconds,
        escalas_tiempo,
    )
