import random

from app.features.narrative.game.draft_sampling import sortear_cartas_draft


def test_sorteo_devuelve_tres_sin_reemplazo():
    candidatas = ["a", "b", "c", "d", "e"]
    elegidas = sortear_cartas_draft(candidatas, {}, cantidad=3)
    assert len(elegidas) == 3
    assert len(set(elegidas)) == 3


def test_sorteo_respeta_cantidad_menor_al_pool():
    assert sorted(sortear_cartas_draft(["a", "b"], {}, cantidad=3)) == ["a", "b"]


def test_peso_cero_no_sale_si_hay_otras_con_peso():
    docs = {"normal": {"peso_draft_mensual": 1.0}, "rara": {"peso_draft_mensual": 0.0}}
    random.seed(1234)
    for _ in range(200):
        assert "rara" not in sortear_cartas_draft(["normal", "rara"], docs, cantidad=1)


def test_peso_bajo_aparece_menos_que_el_normal():
    docs = {
        "normal_a": {"peso_draft_mensual": 1.0},
        "normal_b": {"peso_draft_mensual": 1.0},
        "rara": {"peso_draft_mensual": 0.1},
    }
    random.seed(99)
    apariciones_rara = 0
    apariciones_normal = 0
    for _ in range(2000):
        elegidas = sortear_cartas_draft(["normal_a", "normal_b", "rara"], docs, cantidad=1)
        if elegidas[0] == "rara":
            apariciones_rara += 1
        else:
            apariciones_normal += 1
    assert apariciones_rara < apariciones_normal
    assert apariciones_rara > 0


def test_todos_los_pesos_en_cero_sigue_sorteando():
    docs = {"a": {"peso_draft_mensual": 0}, "b": {"peso_draft_mensual": 0}, "c": {"peso_draft_mensual": 0}}
    elegidas = sortear_cartas_draft(["a", "b", "c"], docs, cantidad=3)
    assert sorted(elegidas) == ["a", "b", "c"]


def test_peso_invalido_cae_a_uno():
    docs = {"a": {"peso_draft_mensual": "no-numero"}, "b": {"peso_draft_mensual": 1.0}}
    elegidas = sortear_cartas_draft(["a", "b"], docs, cantidad=1)
    assert elegidas[0] in ("a", "b")
