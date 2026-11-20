"""Validación del contenido extra del catálogo narrativo V2 (eventos, cartas, personajes)."""

from app.features.narrative.validation.graph_validator import validar_grafo
from app.scripts.narrative_catalog_extra import (
    CARTAS_NUEVAS,
    EVENTOS_NUEVOS,
    PERSONAJES_NUEVOS,
    construir_cartas,
    construir_eventos_extra,
    construir_personajes,
)

CATEGORIAS_CANONICAS = {
    "Pueblo",
    "Fe",
    "Ejército",
    "Oro",
    "Nobleza",
    "Militar",
    "Comercio",
    "Diplomacia",
    "Ciencia",
    "Intriga",
}
IDS_SEED = {
    "evt_cometa_caido_v2",
    "evt_secta_cometa_v2",
    "evt_peste_marismas_v2",
    "evt_embargo_gremios_v2",
    "evt_motin_guarnicion_v2",
    "evt_sequia_gran_v2",
    "evt_pretendiente_trono_v2",
}


def test_eventos_extra_cubren_los_dos_lotes_sin_colisiones():
    eventos = construir_eventos_extra()
    ids = [ev.id for ev in eventos]

    assert len(eventos) == 24
    assert len(set(ids)) == len(ids)
    assert not (set(ids) & IDS_SEED)
    assert len([i for i in ids if i.endswith("_v2d")]) == len(EVENTOS_NUEVOS) == 12


def test_eventos_extra_son_grafos_validos():
    for ev in construir_eventos_extra():
        resultado = validar_grafo(ev.model_dump(by_alias=True), tipo="evento")
        assert resultado.valido, f"{ev.id}: {[h.mensaje for h in resultado.errores]}"


def test_eventos_extra_declaran_categoria_canonica_y_tono():
    for ev in construir_eventos_extra():
        assert ev.categoria in CATEGORIAS_CANONICAS, f"{ev.id}: {ev.categoria!r}"
        assert ev.tono in {"positivo", "negativo", "neutro"}, f"{ev.id}: {ev.tono!r}"
        assert ev.descripcion.strip(), f"{ev.id} sin descripción"
        assert len(ev.nodos) >= 2 and ev.nodo_raiz in ev.nodos


def test_cartas_extra_validas_y_sin_colisiones():
    cartas = construir_cartas()
    ids = [c["_id"] for c in cartas]

    assert len(cartas) == len(CARTAS_NUEVAS) == 10
    assert len(set(ids)) == len(ids)
    for carta in cartas:
        assert carta["universo_id"] == "corte_medieval"
        assert carta["categoria"] in {"item", "bonus", "personaje"}
        assert carta["nombre"].strip() and carta["descripcion"].strip()


def test_personajes_extra_validos_y_sin_colisiones():
    personajes = construir_personajes()
    ids = [p["_id"] for p in personajes]

    assert len(personajes) == len(PERSONAJES_NUEVOS) == 5
    assert len(set(ids)) == len(ids)
    for pj in personajes:
        assert pj["universo_id"] == "corte_medieval"
        assert pj["nombre"].strip() and pj["titulo"].strip()
        assert pj["pros"] and pj["cons"]
