import random

from app.features.narrative.game.event_cycle import seleccionar_ciclo_eventos_diario
from app.scripts.backfill_narrative_pools import (
    calcular_pool_del_dia,
    falta_pool_query,
    pool_requiere_actualizacion,
    refresh_pool_query,
)


def _evento(eid: str, categoria: str) -> dict:
    return {"_id": eid, "categoria": categoria, "tono": "positivo", "nodos": {}}


def _catalogo_eventos() -> list:
    categorias = ["Pueblo", "Fe", "Ejército", "Oro", "Nobleza"]
    return [_evento(f"ev_{i:02d}", categorias[i % len(categorias)]) for i in range(15)]


def test_replica_la_secuencia_del_generador():
    eventos = _catalogo_eventos()
    pj_ids = [f"pj_{i}" for i in range(8)]
    carta_ids = [f"carta_{i}" for i in range(8)]
    universo_id, date_str = "corte_medieval", "2026-12-05"

    esperado_rng = random.Random(f"narrativo_{universo_id}_{date_str}")
    esperado_rng.sample(pj_ids, 5)
    esperado_rng.sample(carta_ids, 5)
    esperado = seleccionar_ciclo_eventos_diario(eventos, esperado_rng)

    obtenido = calcular_pool_del_dia(universo_id, date_str, pj_ids, carta_ids, eventos)
    assert obtenido == esperado
    assert 8 <= len(obtenido) <= len(eventos)


def test_es_determinista_entre_corridas():
    eventos = _catalogo_eventos()
    pj_ids = [f"pj_{i}" for i in range(5)]
    carta_ids = [f"carta_{i}" for i in range(5)]

    primera = calcular_pool_del_dia("corte_medieval", "2026-12-09", pj_ids, carta_ids, eventos)
    segunda = calcular_pool_del_dia("corte_medieval", "2026-12-09", pj_ids, carta_ids, eventos)
    assert primera == segunda


def test_query_solo_toca_narrativo_sin_pool_y_respeta_fechas():
    query = falta_pool_query(desde="2026-12-01", hasta="2026-12-31")
    assert query["game_id"] == "narrativo"
    assert query["date"] == {"$gte": "2026-12-01", "$lte": "2026-12-31"}
    assert {"config.pool_eventos_disponibles_ids": []} in query["$or"]
    assert "date" not in falta_pool_query()


def test_refresh_query_exige_pool_presente_y_respeta_fechas():
    query = refresh_pool_query(desde="2026-01-01")
    assert query["game_id"] == "narrativo"
    assert query["config.pool_eventos_disponibles_ids"] == {"$exists": True, "$ne": None}
    assert query["date"] == {"$gte": "2026-01-01"}
    assert "date" not in refresh_pool_query()


def test_pool_requiere_actualizacion_compara_listas_y_trata_none_como_vacio():
    assert not pool_requiere_actualizacion(["ev_1", "ev_2"], ["ev_1", "ev_2"])
    assert pool_requiere_actualizacion(["ev_1"], ["ev_1", "ev_2"])
    assert pool_requiere_actualizacion(["ev_2", "ev_1"], ["ev_1", "ev_2"])
    assert not pool_requiere_actualizacion(None, [])
    assert not pool_requiere_actualizacion([], None)
    assert pool_requiere_actualizacion(None, ["ev_1"])
