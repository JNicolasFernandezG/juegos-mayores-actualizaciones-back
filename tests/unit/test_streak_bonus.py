"""Resolución pura del bonus de puntos por racha."""

import pytest

from app.features.economy.schemas import BonusRachaConfig
from app.features.economy.streak_bonus import resolver_bonus_racha

pytestmark = pytest.mark.unit


def _config(**overrides) -> BonusRachaConfig:
    base = {
        "activo": True,
        "modo": "porcentaje",
        "tramos": [
            {"dias": 10, "valor": 10},
            {"dias": 15, "valor": 20},
            {"dias": 20, "valor": 30},
        ],
    }
    base.update(overrides)
    return BonusRachaConfig(**base)


def test_bonus_inactivo_no_aplica():
    config = _config(activo=False)
    assert resolver_bonus_racha(config, racha_dias=30, puntos_base=100).puntos == 0


@pytest.mark.parametrize(
    "racha,esperado,dias_tramo",
    [
        (0, 0, 0),
        (9, 0, 0),
        (10, 10, 10),
        (14, 10, 10),
        (15, 20, 15),
        (19, 20, 15),
        (20, 30, 20),
        (45, 30, 20),
    ],
)
def test_solo_aplica_el_tramo_mas_alto_alcanzado(racha, esperado, dias_tramo):
    resultado = resolver_bonus_racha(_config(), racha_dias=racha, puntos_base=100)
    assert resultado.puntos == esperado
    assert resultado.dias_tramo == dias_tramo


def test_porcentaje_redondea_hacia_abajo():
    resultado = resolver_bonus_racha(_config(), racha_dias=15, puntos_base=77)
    assert resultado.puntos == 15
    assert resultado.dias_tramo == 15


def test_modo_puntos_fijos_ignora_el_puntaje_base():
    config = _config(modo="puntos_fijos", tramos=[{"dias": 5, "valor": 25}])
    assert resolver_bonus_racha(config, racha_dias=5, puntos_base=100).puntos == 25
    assert resolver_bonus_racha(config, racha_dias=9, puntos_base=10).puntos == 25


def test_puntaje_base_cero_no_genera_bonus():
    assert resolver_bonus_racha(_config(), racha_dias=20, puntos_base=0).puntos == 0


def test_sin_tramos_no_genera_bonus():
    config = BonusRachaConfig(activo=False, modo="porcentaje", tramos=[])
    assert resolver_bonus_racha(config, racha_dias=20, puntos_base=100).puntos == 0


def test_tramos_desordenados_se_resuelven_por_dias():
    config = _config(
        tramos=[
            {"dias": 20, "valor": 30},
            {"dias": 10, "valor": 10},
            {"dias": 15, "valor": 20},
        ]
    )
    assert resolver_bonus_racha(config, racha_dias=16, puntos_base=100).puntos == 20
