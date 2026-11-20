import random
import pytest

from app.features.narrative.game.event_cycle import (
    cargar_eventos_del_dia_setup,
    inferir_categoria_evento,
    inferir_tono_evento,
    resumir_evento_para_ciclo,
    seleccionar_ciclo_eventos_diario,
)


def _evento(eid: str, *, tags=None, delta_recurso=None, tipo_desenlace=None, categoria=None, tono=None, req_prev=None):
    recurso, delta = delta_recurso or ("pueblo", -5)
    return {
        "_id": eid,
        "titulo": f"Titulo {eid}",
        "categoria": categoria,
        "tono": tono,
        "tags_tematicos": tags or [],
        "requisitos_eventos_previos": req_prev or [],
        "nodo_raiz": "inicio",
        "nodos": {
            "inicio": {"id": "inicio", "texto": f"Texto raiz {eid}", "es_final": False},
            "fin": {
                "id": "fin",
                "texto": "Fin",
                "es_final": True,
                "tipo_desenlace": tipo_desenlace,
                "impactos_recursos": [{"recurso": recurso, "delta": delta}],
            },
        },
    }


def test_inferencia_categoria_y_tono_desde_grafo():
    ev = _evento("e1", tags=["fe"], delta_recurso=("fe", 15), tipo_desenlace="positivo")
    res = resumir_evento_para_ciclo(ev, {"fe": "Fe"})
    assert res["categoria"] == "Fe"
    assert res["categoria_evento"] == "Fe"
    assert res["tono"] == "positivo"
    assert res["descripcion"] == "Texto raiz e1"

    ev_manual = _evento("e2", categoria="Diplomacia", tono="negativo", delta_recurso=("oro", 10))
    assert inferir_categoria_evento(ev_manual) == "Diplomacia"
    assert inferir_tono_evento(ev_manual) == "negativo"


def test_inferencia_categoria_por_impacto_dominante_sin_tags():
    ev = _evento("e_oro", tags=[], delta_recurso=("oro", -20))
    assert inferir_categoria_evento(ev) == "Oro"
    assert inferir_tono_evento(ev) == "negativo"


def test_categoria_canonica_aunque_el_universo_use_otro_nombre():
    ev = _evento("e_pueblo", tags=[], delta_recurso=("pueblo", 20))
    # El universo puede mostrar "Apoyo Popular", pero la categoría anunciada es la canónica.
    assert inferir_categoria_evento(ev, {"pueblo": "Apoyo Popular"}) == "Pueblo"

    explicito = _evento("e_explicito", categoria="pueblo")
    assert inferir_categoria_evento(explicito) == "Pueblo"


def test_tono_mixto_queda_neutro_y_explicito_manda():
    ev = _evento("e_mixto", delta_recurso=("pueblo", 30))
    ev["nodos"]["fin_negativo"] = {
        "id": "fin_negativo",
        "texto": "Fin",
        "es_final": True,
        "impactos_recursos": [{"recurso": "pueblo", "delta": -30}],
    }
    assert inferir_tono_evento(ev) == "neutro"

    ev["tono"] = "negativo"
    assert inferir_tono_evento(ev) == "negativo"

    # El tipo_desenlace declarado por el autor manda sobre el signo de los deltas.
    ev_tipado = _evento("e_tipado", delta_recurso=("pueblo", -30), tipo_desenlace="positivo")
    assert inferir_tono_evento(ev_tipado) == "positivo"


def test_seleccionar_ciclo_diario_varia_y_preserva_prerrequisitos():
    eventos = [
        _evento(f"p{i}", tags=["pueblo"], delta_recurso=("pueblo", 10 if i % 2 == 0 else -10))
        for i in range(5)
    ] + [
        _evento(f"f{i}", tags=["fe"], delta_recurso=("fe", -15 if i < 3 else 15))
        for i in range(5)
    ] + [
        _evento("o1", tags=["oro"], delta_recurso=("oro", 15), req_prev=["p0"]),
        _evento("e1", tags=["ejercito"], delta_recurso=("ejercito", -10)),
    ]

    titulos_simulados = set()
    for day in range(1, 20):
        rng = random.Random(f"narrativo_corte_medieval_2026-11-{day:02d}")
        ids = seleccionar_ciclo_eventos_diario(eventos, rng)
        assert len(ids) >= 8
        if "o1" in ids:
            assert "p0" in ids
        by_id = {e["_id"]: resumir_evento_para_ciclo(e) for e in eventos}
        cats = {}
        pos = neg = 0
        for eid in ids:
            item = by_id[eid]
            cats[item["categoria"]] = cats.get(item["categoria"], 0) + 1
            if item["tono"] == "positivo":
                pos += 1
            elif item["tono"] == "negativo":
                neg += 1
        top = sorted(cats.items(), key=lambda kv: -kv[1])
        if top[0][1] > (top[1][1] if len(top) > 1 else 0):
            titulos_simulados.add(f"Ciclo de {top[0][0]}")
        elif pos > neg:
            titulos_simulados.add("Ciclo soleado")
        elif neg > pos:
            titulos_simulados.add("Ciclo tormentoso")
        else:
            titulos_simulados.add("Ciclo balanceado")

    assert len(titulos_simulados) >= 3


@pytest.mark.asyncio
async def test_cargar_eventos_del_dia_setup_respeta_orden_y_fallback():
    ev_a = _evento("ev_a", tags=["pueblo"])
    ev_b = _evento("ev_b", tags=["fe"], delta_recurso=("fe", 10))

    class _Cursor:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, _):
            return self._docs

    class _Coll:
        def __init__(self, docs):
            self.docs = docs

        def find(self, query):
            if "_id" in query:
                ids = set(query["_id"]["$in"])
                return _Cursor([d for d in self.docs if d["_id"] in ids])
            return _Cursor([d for d in self.docs if d.get("universo_id", "u1") == query.get("universo_id", "u1")])

    db = {"narrative_v2_events": _Coll([ev_b, ev_a])}
    res = await cargar_eventos_del_dia_setup(
        db,
        {"universo_id": "u1", "pool_eventos_disponibles_ids": ["ev_a", "ev_b"]},
        {"recursos": [{"clave": "pueblo", "nombre": "Pueblo"}, {"clave": "fe", "nombre": "Fe"}]},
    )
    assert [r["id"] for r in res] == ["ev_a", "ev_b"]
    assert res[0]["categoria"] == "Pueblo"

    # El pool de la run activa manda sobre el pool del challenge.
    res_run = await cargar_eventos_del_dia_setup(
        db,
        {"universo_id": "u1", "pool_eventos_disponibles_ids": ["ev_a"]},
        {"recursos": [{"clave": "pueblo", "nombre": "Apoyo Popular"}]},
        pool_ids=["ev_b"],
    )
    assert [r["id"] for r in res_run] == ["ev_b"]
