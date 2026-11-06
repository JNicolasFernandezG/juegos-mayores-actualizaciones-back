"""Pesos efectivos de los desenlaces V2 con modificadores condicionales (paridad con V1)."""

import random

import pytest

from app.features.narrative.game.motor_v2.graph_engine import GraphTraversalEngine
from app.features.narrative.schemas.v2_graph_schemas import DesenlaceNodoSchema

pytestmark = pytest.mark.unit


def _desenlace(nodo: str, peso: float, condicion: dict | None = None, delta: float = 0.0) -> DesenlaceNodoSchema:
    mods = []
    if condicion is not None:
        mods = [{"condicion": condicion, "delta_peso": delta, "explicacion": "+por tag"}]
    return DesenlaceNodoSchema(nodo=nodo, peso=peso, modificadores_probabilidad=mods)


_RUN_CON_DEFENSA = {"tags_activos": ["defensa"], "afinidad": {}, "recursos": {"oro": 10}}


def test_sin_modificadores_el_peso_es_estatico():
    pesos = GraphTraversalEngine._pesos_desenlaces(
        [_desenlace("a", 60.0), _desenlace("b", 40.0)], _RUN_CON_DEFENSA
    )
    assert pesos == [60.0, 40.0]


def test_modificador_suma_solo_cuando_cumple_la_condicion():
    condicion = {"tipo": "tiene_tag", "tag": "defensa"}
    desenlaces = [
        _desenlace("a", 60.0, condicion, 30.0),
        _desenlace("b", 40.0),
    ]

    cumple = GraphTraversalEngine._pesos_desenlaces(desenlaces, _RUN_CON_DEFENSA)
    no_cumple = GraphTraversalEngine._pesos_desenlaces(desenlaces, {"tags_activos": []})

    assert cumple == [90.0, 40.0]
    assert no_cumple == [60.0, 40.0]


def test_un_modificador_que_anula_el_peso_deja_el_desenlace_fuera_del_sorteo():
    """V2 ya garantizaba peso 0 = no se sortea; los modificadores no cambian esa regla."""
    desenlaces = [
        _desenlace("a", 50.0, {"tipo": "tiene_tag", "tag": "defensa"}, -500.0),
        _desenlace("b", 50.0),
    ]

    pesos = GraphTraversalEngine._pesos_desenlaces(desenlaces, _RUN_CON_DEFENSA)

    assert pesos == [0.0, 50.0]


def test_el_sorteo_reparte_distinto_cumpliendo_o_no_el_modificador():
    desenlaces = [
        _desenlace("a", 10.0, {"tipo": "tiene_tag", "tag": "defensa"}, 90.0),
        _desenlace("b", 10.0),
    ]
    nodos = [d.nodo for d in desenlaces]

    random.seed(1234)
    con_defensa = random.choices(
        nodos, weights=GraphTraversalEngine._pesos_desenlaces(desenlaces, _RUN_CON_DEFENSA), k=400
    ).count("a")

    random.seed(1234)
    sin_defensa = random.choices(
        nodos, weights=GraphTraversalEngine._pesos_desenlaces(desenlaces, {"tags_activos": []}), k=400
    ).count("a")

    assert con_defensa > sin_defensa * 1.5, "el modificador condicionado debe inclinar el sorteo"
