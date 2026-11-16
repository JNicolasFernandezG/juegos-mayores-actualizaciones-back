"""Puntos diarios por racha de ingresos.

Función pura y sin dependencias para poder reutilizarla desde cualquier módulo.
Cada día de racha entrega una cantidad fija de puntos según el tramo alcanzado.
La racha se reinicia en el día 1 apenas se deja pasar un día sin ingresar
(ver ``app.shared.streak``).
"""

from typing import List, Tuple

# (día de racha desde el cual aplica, puntos por día)
TRAMOS_PUNTOS_DIARIOS: List[Tuple[int, int]] = [
    (1, 40),    # días 1 a 14
    (15, 80),   # días 15 a 19
    (20, 120),  # días 20 a 24
    (25, 160),  # día 25 en adelante
]


def puntos_por_dia_de_racha(dia_racha: int) -> int:
    """Puntos que se ganan por ingresar en el día ``dia_racha`` de la racha."""
    if dia_racha <= 0:
        return 0
    puntos = 0
    for desde, valor in TRAMOS_PUNTOS_DIARIOS:
        if dia_racha >= desde:
            puntos = valor
    return puntos


def tramos_puntos_diarios() -> List[dict]:
    """Tramos serializables para que el cliente los muestre sin duplicar la regla."""
    return [{"dias": desde, "puntos": valor} for desde, valor in TRAMOS_PUNTOS_DIARIOS]
