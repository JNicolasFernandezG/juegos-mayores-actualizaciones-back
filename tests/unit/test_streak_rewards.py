"""Puntos diarios por día de racha."""

import pytest

from app.shared.streak_rewards import puntos_por_dia_de_racha, tramos_puntos_diarios


@pytest.mark.parametrize(
    "dia,esperado",
    [(0, 0), (1, 40), (14, 40), (15, 80), (19, 80), (20, 120), (24, 120), (25, 160), (100, 160)],
)
def test_puntos_por_dia(dia, esperado):
    assert puntos_por_dia_de_racha(dia) == esperado


def test_tramos_serializables():
    assert tramos_puntos_diarios() == [
        {"dias": 1, "puntos": 40},
        {"dias": 15, "puntos": 80},
        {"dias": 20, "puntos": 120},
        {"dias": 25, "puntos": 160},
    ]
