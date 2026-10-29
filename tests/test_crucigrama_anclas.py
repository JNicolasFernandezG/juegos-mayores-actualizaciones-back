"""
test_crucigrama_anclas.py
Cubre el soporte de palabras ancla del diseñador de máscaras:
normalización/validación en el solver, informe del validador y determinismo.
"""

import pytest

from app.features.daily_challenges.crucigrama import solver as solver_mod
from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    normalize_preassigned,
)
from app.features.daily_challenges.crucigrama.templates_facil import CRUCIGRAMA_TEMPLATES
from app.features.daily_challenges.crucigrama.validator import (
    validate_pattern,
    validate_structure,
)

PATTERN = CRUCIGRAMA_TEMPLATES[0]["pattern"]

MASK_11X11 = [
    ".........##",
    ".#####.#...",
    ".#.##....##",
    "......##.#.",
    ".#.##.##...",
    ".#.......#.",
    "##.#.###.#.",
    "#.....##.#.",
    "##.#.#....#",
    "####.##.###",
    "######.....",
]


@pytest.fixture(scope="module")
def slots_e_intersecciones():
    return _parse_template_slots(PATTERN)


@pytest.fixture(scope="module")
def reporte_base():
    report = validate_pattern(PATTERN, prefer_curated=True)
    assert report["solvable"], report
    return report


def _anclas_de_la_solucion(reporte, cantidad=2):
    palabras = reporte["solution_words"]
    ids = list(palabras)[:cantidad]
    return {s_id: palabras[s_id] for s_id in ids}


def _letra_en_cruce(slots, intersecciones, s_a, s_b):
    for pos_a, other_id, pos_b in intersecciones[s_a["id"]]:
        if other_id == s_b["id"]:
            return pos_a, pos_b
    return None


def _palabra_con_letra_distinta(longitud, posicion, letra):
    solver_mod._init_word_index()
    for palabra in solver_mod._WORDS_BY_LEN.get(longitud, []):
        if palabra[posicion] != letra:
            return palabra
    return None


def test_anclas_se_respetan(reporte_base, slots_e_intersecciones):
    slots, _ = slots_e_intersecciones
    anclas = _anclas_de_la_solucion(reporte_base)

    reporte = validate_pattern(PATTERN, prefer_curated=True, anchors=anclas)

    assert reporte["valid"], reporte["errors"]
    assert reporte["solvable"], reporte
    assert reporte["anchors"] == anclas
    por_id = {s["id"]: s for s in slots}
    for s_id, palabra in anclas.items():
        for (r, c), ch in zip(por_id[s_id]["coords"], palabra):
            assert reporte["solution"][r][c] == ch


def test_anclas_mantienen_determinismo(reporte_base):
    anclas = _anclas_de_la_solucion(reporte_base)

    primero = validate_pattern(PATTERN, prefer_curated=True, anchors=anclas)
    segundo = validate_pattern(PATTERN, prefer_curated=True, anchors=anclas)

    assert primero["solution"] == segundo["solution"]
    assert primero["attempts"] == segundo["attempts"]


def test_anclas_en_mascara_11x11():
    base = validate_pattern(MASK_11X11, prefer_curated=False)
    assert base["solvable"], base

    centrales = sorted(base["slots"], key=lambda s: s["crossings"], reverse=True)[:2]
    anclas = {s["id"]: base["solution_words"][s["id"]] for s in centrales}

    reporte = validate_pattern(MASK_11X11, prefer_curated=False, anchors=anclas)
    assert reporte["valid"], reporte["errors"]
    assert reporte["solvable"], reporte


def test_slots_expuestos_coinciden_con_el_solver(slots_e_intersecciones):
    slots, intersecciones = slots_e_intersecciones
    por_id = {s["id"]: s for s in slots}
    reporte = validate_structure(PATTERN)

    assert [s["id"] for s in reporte["slots"]] == [s["id"] for s in slots]
    for expuesto in reporte["slots"]:
        assert expuesto["length"] == por_id[expuesto["id"]]["len"]
        assert expuesto["crossings"] == len(intersecciones[expuesto["id"]])
    assert reporte["solvable"] is False
    assert reporte["solution"] is None


def test_normaliza_acentos_sin_tocar_la_enie(slots_e_intersecciones):
    slots, intersecciones = slots_e_intersecciones
    solver_mod._init_word_index()
    acentos = {"A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú"}

    for largo in sorted({s["len"] for s in slots}):
        candidatas = [
            w for w in solver_mod._WORDS_BY_LEN.get(largo, []) if any(v in w for v in acentos)
        ]
        if not candidatas:
            continue
        palabra = candidatas[0]
        idx = next(i for i, ch in enumerate(palabra) if ch in acentos)
        acentuada = palabra[:idx] + acentos[palabra[idx]] + palabra[idx + 1:]
        slot = next(s for s in slots if s["len"] == largo)

        normalizadas = normalize_preassigned({slot["id"]: acentuada}, slots, intersecciones)
        assert normalizadas[slot["id"]] == palabra
        return

    pytest.skip("La plantilla no tiene un slot compatible con el léxico acentuado.")


@pytest.mark.parametrize(
    "anclas_builder,esperado",
    [
        (lambda slots: {"NO_EXISTE": "CASA"}, "no existe en la máscara"),
        (lambda slots: {slots[0]["id"]: ""}, "está vacía"),
        (lambda slots: {slots[0]["id"]: "AB1"}, "solo puede contener letras"),
        (lambda slots: {slots[0]["id"]: "Z" * slots[0]["len"]}, "no está en el léxico"),
    ],
)
def test_anclas_invalidas(slots_e_intersecciones, anclas_builder, esperado):
    slots, intersecciones = slots_e_intersecciones
    with pytest.raises(ValueError, match=esperado):
        normalize_preassigned(anclas_builder(slots), slots, intersecciones)


def test_ancla_con_longitud_incorrecta(slots_e_intersecciones):
    slots, intersecciones = slots_e_intersecciones
    slot = next(s for s in slots if s["len"] != 4)
    with pytest.raises(ValueError, match="requiere"):
        normalize_preassigned({slot["id"]: "CASA"}, slots, intersecciones)


def test_palabra_repetida_en_dos_slots(slots_e_intersecciones, reporte_base):
    slots, intersecciones = slots_e_intersecciones
    por_largo = {}
    for slot in slots:
        por_largo.setdefault(slot["len"], []).append(slot)
    par = next((grupo for grupo in por_largo.values() if len(grupo) >= 2), None)
    assert par, "La plantilla necesita dos slots del mismo largo para esta prueba."
    palabra = reporte_base["solution_words"][par[0]["id"]]

    with pytest.raises(ValueError, match="más de un slot"):
        normalize_preassigned(
            {par[0]["id"]: palabra, par[1]["id"]: palabra}, slots, intersecciones
        )


def test_cruce_incompatible(slots_e_intersecciones, reporte_base):
    slots, intersecciones = slots_e_intersecciones
    for s_a in slots:
        for _, other_id, _ in intersecciones[s_a["id"]]:
            s_b = next(s for s in slots if s["id"] == other_id)
            cruce = _letra_en_cruce(slots, intersecciones, s_a, s_b)
            if cruce is None:
                continue
            pos_a, pos_b = cruce
            palabra_a = reporte_base["solution_words"][s_a["id"]]
            palabra_b = _palabra_con_letra_distinta(s_b["len"], pos_b, palabra_a[pos_a])
            if palabra_b is None:
                continue
            with pytest.raises(ValueError, match="Cruce incompatible"):
                normalize_preassigned(
                    {s_a["id"]: palabra_a, s_b["id"]: palabra_b},
                    slots,
                    intersecciones,
                )
            return
    pytest.skip("No se encontró un par de cruce con palabras incompatibles.")


def test_validador_reporta_ancla_invalida():
    reporte = validate_pattern(PATTERN, attempt_budgets=(100,), anchors={"NO_EXISTE": "CASA"})

    assert not reporte["valid"]
    assert not reporte["solvable"]
    assert any("no existe en la máscara" in error for error in reporte["errors"])
    assert reporte["anchors"] == {}


def test_validador_advierte_si_las_anclas_no_tienen_solucion(reporte_base):
    anclas = _anclas_de_la_solucion(reporte_base)

    reporte = validate_pattern(
        PATTERN, prefer_curated=True, attempt_budgets=(1,), anchors=anclas
    )

    assert reporte["anchors"] == anclas
    assert not reporte["solvable"]
    assert any("palabras fijadas" in warning for warning in reporte["warnings"])
