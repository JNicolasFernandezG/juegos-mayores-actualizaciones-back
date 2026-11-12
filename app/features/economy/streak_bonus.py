"""Boost de puntos por racha diaria al completar un desafío.

El cálculo es puro y determinístico: recibe la configuración vigente y los días de
racha del usuario, y devuelve el tramo aplicable. Solo se aplica el tramo de mayor
``dias`` alcanzado, nunca la suma de varios.
"""

from dataclasses import dataclass

from app.features.economy.schemas import BonusRachaConfig


@dataclass(frozen=True)
class BonusRachaAplicado:
    puntos: int
    dias_tramo: int

    @property
    def activo(self) -> bool:
        return self.puntos > 0


SIN_BONUS = BonusRachaAplicado(puntos=0, dias_tramo=0)


def resolver_bonus_racha(
    config: BonusRachaConfig,
    racha_dias: int,
    puntos_base: int,
) -> BonusRachaAplicado:
    """Calcula el boost del tramo más alto alcanzado por la racha actual."""
    if not config.activo or racha_dias <= 0 or puntos_base <= 0:
        return SIN_BONUS

    elegible = None
    for tramo in config.tramos:
        if tramo.dias <= racha_dias and (elegible is None or tramo.dias > elegible.dias):
            elegible = tramo

    if elegible is None:
        return SIN_BONUS

    if config.modo == "puntos_fijos":
        puntos = elegible.valor
    else:
        puntos = puntos_base * elegible.valor // 100

    if puntos <= 0:
        return SIN_BONUS
    return BonusRachaAplicado(puntos=puntos, dias_tramo=elegible.dias)
