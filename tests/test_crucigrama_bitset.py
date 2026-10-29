"""
test_crucigrama_bitset.py
Motor AC-3 + MRV del diseñador: solubilidad de máscaras densas, determinismo,
anclas, vetos y regresión sobre plantillas reales.
"""

import random

import pytest

from app.features.daily_challenges.crucigrama.solver import (
    _parse_template_slots,
    is_known_word,
    normalize_word,
)
from app.features.daily_challenges.crucigrama.solver_bitset import solve_with_bitsets
from app.features.daily_challenges.crucigrama.templates_facil import CRUCIGRAMA_TEMPLATES
from app.features.daily_challenges.crucigrama.validator import validate_pattern

DENSE = [
    "......#",
    "......#",
    "......#",
    "......#",
    ".....#.",
    "....##.",
    "####...",
]

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


def _solve(pattern, seed="dense", **kwargs):
    slots, intersections = _parse_template_slots(pattern)
    rng = random.Random(seed)
    solution = solve_with_bitsets(
        slots, intersections, rng, max_seconds=30, **kwargs
    )
    return slots, solution


def _assert_solucion(pattern, slots, assignment):
    assert assignment is not None
    assert set(assignment) == {slot["id"] for slot in slots}
    assert len(set(assignment.values())) == len(assignment)
    for word in assignment.values():
        assert is_known_word(word), word

    R, C = len(pattern), len(pattern[0])
    grid = [["#" if pattern[r][c] == "#" else "" for c in range(C)] for r in range(R)]
    for slot in slots:
        for (r, c), ch in zip(slot["coords"], assignment[slot["id"]]):
            assert grid[r][c] in ("", ch)
            grid[r][c] = ch
    for r in range(R):
        for c in range(C):
            if pattern[r][c] == ".":
                assert grid[r][c].isalpha(), (r, c)


def _palabras_de_la_solucion(pattern, solution):
    slots, _ = _parse_template_slots(pattern)
    return {
        slot["id"]: "".join(solution[r][c] for r, c in slot["coords"])
        for slot in slots
    }


def test_mascara_densa_se_resuelve():
    slots, solution = _solve(DENSE, prefer_curated=True)
    _assert_solucion(DENSE, slots, solution)


def test_mascara_densa_se_resuelve_por_el_validador():
    report = validate_pattern(DENSE, prefer_curated=True, engine="bitset")
    assert report["valid"], report["errors"]
    assert report["engine"] == "bitset"
    assert report["solvable"], report
    assert report["attempts"] >= 1

    slots, _ = _parse_template_slots(DENSE)
    _assert_solucion(DENSE, slots, _palabras_de_la_solucion(DENSE, report["solution"]))


def test_motor_es_determinista_por_semilla():
    _, primero = _solve(DENSE, seed="estable")
    _, segundo = _solve(DENSE, seed="estable")
    assert primero == segundo


def test_anclas_se_respetan_en_mascara_densa():
    slots, base = _solve(DENSE)
    assert base is not None
    anclas = {
        slot["id"]: base[slot["id"]]
        for slot in [s for s in slots if s["len"] == 6][:2]
    }

    _, con_anclas = _solve(DENSE, seed="otra", preassigned=anclas)
    assert con_anclas is not None
    for slot_id, word in anclas.items():
        assert con_anclas[slot_id] == word


def test_vetos_excluyen_palabras():
    pattern = CRUCIGRAMA_TEMPLATES[0]["pattern"]
    _, base = _solve(pattern, prefer_curated=True)
    assert base is not None
    vetada = next(iter(base.values()))

    _, con_veto = _solve(
        pattern, prefer_curated=True, banned_words={normalize_word(vetada)}
    )
    assert con_veto is not None
    assert vetada not in con_veto.values()


def test_ancla_vetada_es_error():
    slots, intersections = _parse_template_slots(DENSE)
    solution = solve_with_bitsets(
        slots, intersections, random.Random("dense"), max_seconds=30
    )
    assert solution is not None
    slot_id, word = next(iter(solution.items()))

    with pytest.raises(ValueError, match="fijada y vetada"):
        solve_with_bitsets(
            slots,
            intersections,
            random.Random("x"),
            max_seconds=5,
            preassigned={slot_id: word},
            banned_words={word},
        )


def test_regresion_plantillas_facil_y_11x11():
    for tmpl in CRUCIGRAMA_TEMPLATES[:3]:
        slots, solution = _solve(tmpl["pattern"], prefer_curated=True)
        _assert_solucion(tmpl["pattern"], slots, solution)

    slots, solution = _solve(MASK_11X11, prefer_curated=False)
    _assert_solucion(MASK_11X11, slots, solution)
