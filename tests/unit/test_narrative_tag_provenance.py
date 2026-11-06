import pytest

from app.features.narrative.engine.tag_state import (
    personajes_activos,
    quitar_origen,
    quitar_tag,
    registrar_tags,
    sincronizar_personajes,
)


def test_registrar_tags_activa_y_registra_procedencia():
    run = {"tags_activos": [], "tags_origen": {}}

    registrar_tags(run, "card_a", ["fe", "religion"])
    registrar_tags(run, "pj_x", ["religion", "moral"])

    assert sorted(run["tags_activos"]) == ["fe", "moral", "religion"]
    assert run["tags_origen"]["card_a"] == ["fe", "religion"]
    assert run["tags_origen"]["pj_x"] == ["religion", "moral"]


def test_quitar_tag_es_global_y_limpia_procedencia():
    run = {
        "tags_activos": ["fe", "religion"],
        "tags_origen": {"card_a": ["fe", "religion"], "pj_x": ["religion"]},
    }

    quitar_tag(run, "religion")

    assert run["tags_activos"] == ["fe"]
    assert run["tags_origen"]["card_a"] == ["fe"]
    assert run["tags_origen"]["pj_x"] == []


def test_quitar_origen_conserva_tags_que_otra_fuente_aporta():
    run = {
        "tags_activos": ["fe", "religion", "militar"],
        "tags_origen": {
            "pj_obispo": ["fe", "religion"],
            "card_bendicion": ["religion"],
            "pj_marcus": ["militar"],
        },
    }

    quitar_origen(run, "pj_obispo")

    assert sorted(run["tags_activos"]) == ["militar", "religion"]
    assert "pj_obispo" not in run["tags_origen"]


def test_personajes_activos_prefiere_afinidad():
    assert personajes_activos({"afinidad": {"pj_a": 50}, "corte_activa": ["pj_b"]}) == ["pj_a"]
    assert personajes_activos({"corte_activa": ["pj_b"]}) == ["pj_b"]


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _limit):
        return self._docs


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, _projection=None):
        ids = set(query["_id"]["$in"])
        return _FakeCursor([d for d in self._docs if d["_id"] in ids])


class _FakeDB:
    def __init__(self, docs):
        self._collection = _FakeCollection(docs)

    def __getitem__(self, _name):
        return self._collection


@pytest.mark.asyncio
async def test_sincronizar_personajes_activa_tags_estaticos_una_vez():
    db = _FakeDB([
        {"_id": "pj_obispo_tomas", "tags": ["fe", "religion"]},
        {"_id": "pj_fantasma", "tags": ["sombras"]},
    ])
    run = {"afinidad": {"pj_obispo_tomas": 50, "pj_inexistente": 50}, "tags_activos": [], "tags_origen": {}}

    await sincronizar_personajes(run, personajes_activos(run), db)

    assert sorted(run["tags_activos"]) == ["fe", "religion"]
    assert run["tags_origen"]["pj_obispo_tomas"] == ["fe", "religion"]
    assert run["tags_origen"]["pj_inexistente"] == []

    # Segunda pasada: no duplica ni vuelve a consultar
    await sincronizar_personajes(run, personajes_activos(run), db)
    assert run["tags_activos"].count("fe") == 1
