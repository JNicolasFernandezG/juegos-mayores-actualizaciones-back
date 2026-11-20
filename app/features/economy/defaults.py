"""Valores por defecto compartidos de la economía."""

from typing import Any, Dict, List, Tuple

from app.shared.economy_points import DEFAULT_PUNTOS_POR_CALIFICACION  # noqa: F401

_TIERS_ESCALA_BASE: Tuple[Tuple[str, int, int, str], ...] = (
    ("S", 100, 3, "¡Impecable!"),
    ("A", 90, 3, "¡Excelente!"),
    ("B", 75, 2, "¡Muy Bueno!"),
    ("C", 50, 1, "¡Buen Trabajo!"),
    ("D", 25, 1, "¡Completado!"),
)

_RANGOS_POR_JUEGO: Dict[str, Tuple[Tuple[int, str], ...]] = {
    "sudoku": (
        (180, "Menos de 03:00"),
        (300, "03:01 a 05:00"),
        (480, "05:01 a 08:00"),
        (720, "08:01 a 12:00"),
        (999999, "Más de 12:00"),
    ),
    "crucigrama": (
        (240, "Menos de 04:00"),
        (420, "04:01 a 07:00"),
        (600, "07:01 a 10:00"),
        (900, "10:01 a 15:00"),
        (999999, "Más de 15:00"),
    ),
    "sopa_letras": (
        (120, "Menos de 02:00"),
        (240, "02:01 a 04:00"),
        (360, "04:01 a 06:00"),
        (600, "06:01 a 10:00"),
        (999999, "Más de 10:00"),
    ),
}


def _construir_escala(rangos: Tuple[Tuple[int, str], ...]) -> List[Dict[str, Any]]:
    return [
        {
            "grade": grade,
            "tiempo_max_segundos": tiempo_max,
            "puntos": puntos,
            "estrellas": estrellas,
            "titulo": titulo,
            "descripcion": descripcion,
        }
        for (grade, puntos, estrellas, titulo), (tiempo_max, descripcion) in zip(
            _TIERS_ESCALA_BASE, rangos
        )
    ]


DEFAULT_ESCALAS_TIEMPO: Dict[str, List[Dict[str, Any]]] = {
    juego: _construir_escala(rangos) for juego, rangos in _RANGOS_POR_JUEGO.items()
}

DEFAULT_BONUS_RACHA: Dict[str, Any] = {
    "activo": False,
    "modo": "porcentaje",
    "tramos": [
        {"dias": 10, "valor": 10},
        {"dias": 15, "valor": 20},
        {"dias": 20, "valor": 30},
    ],
}

DEFAULT_PUNTOS_POR_JUEGO: Dict[str, int] = {
    "wordle": 50,
    "sopa_letras": 50,
    "sudoku": 60,
    "crucigrama": 70,
    "narrativo": 80,
}
