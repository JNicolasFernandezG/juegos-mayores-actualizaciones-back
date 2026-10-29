"""
test_crucigrama_validator.py
Valida el módulo validator: estructura, solubilidad con reintentos, determinismo
y consistencia del léxico con las pistas curadas.
"""

import json
from pathlib import Path

import pytest

from app.features.daily_challenges.crucigrama.clues import CURATED_CLUES
from app.features.daily_challenges.crucigrama.templates_facil import CRUCIGRAMA_TEMPLATES
from app.features.daily_challenges.crucigrama.validator import _is_symmetric, validate_pattern

ROOT = Path(__file__).resolve().parents[1]
LEXICO = ROOT / "app" / "data" / "acentos_todas_palabras.json"

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

POCAS_PALABRAS = [
    ".......",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
]

RACHA_CORTA = [
    "..#####",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
]

CELDA_AISLADA = [
    ".######",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
    "#######",
]


def _assert_solucion_completa(pattern, solution):
    assert len(solution) == len(pattern)
    for r, fila in enumerate(pattern):
        assert len(solution[r]) == len(fila)
        for c, ch in enumerate(fila):
            if ch == "#":
                assert solution[r][c] == "#"
            else:
                assert solution[r][c].isalpha(), (r, c, solution[r][c])


def test_plantillas_facil_son_estructuralmente_validas():
    for tmpl in CRUCIGRAMA_TEMPLATES:
        report = validate_pattern(
            tmpl["pattern"], prefer_curated=True, attempt_budgets=(100,)
        )
        assert report["valid"], (tmpl["id"], report["errors"])


def test_plantilla_facil_es_soluble():
    report = validate_pattern(CRUCIGRAMA_TEMPLATES[0]["pattern"], prefer_curated=True)
    assert report["valid"]
    assert report["solvable"], report
    _assert_solucion_completa(
        CRUCIGRAMA_TEMPLATES[0]["pattern"], report["solution"]
    )


def test_mascara_11x11_es_soluble_con_reintentos():
    report = validate_pattern(MASK_11X11, prefer_curated=False)
    assert report["valid"], report["errors"]
    assert report["solvable"], report
    assert report["attempts"] >= 1
    _assert_solucion_completa(MASK_11X11, report["solution"])


@pytest.mark.parametrize(
    "pattern,esperado",
    [
        ([], "lista de filas"),
        ([".......", "......"], "mismo largo"),
        (["....."] * 7, "cuadrado"),
        (["......."] * 6 + ["......X"], "Caracteres inválidos"),
        (RACHA_CORTA, "2 letras"),
        (CELDA_AISLADA, "aisladas"),
        (["..........."] * 11, "más de 10 letras"),
        (POCAS_PALABRAS, "al menos 5"),
    ],
)
def test_errores_estructurales(pattern, esperado):
    report = validate_pattern(pattern, attempt_budgets=(100,))
    assert not report["valid"]
    assert any(esperado in error for error in report["errors"]), report["errors"]
    assert report["solvable"] is False


def test_advertencia_por_asimetria():
    pattern = ["#......"] + ["......."] * 6
    report = validate_pattern(pattern, attempt_budgets=(100,))
    assert report["valid"], report["errors"]
    assert any("simétrico" in warning for warning in report["warnings"])
    assert not _is_symmetric(pattern)


def test_validador_determinista():
    pattern = CRUCIGRAMA_TEMPLATES[1]["pattern"]
    primero = validate_pattern(pattern, prefer_curated=True)
    segundo = validate_pattern(pattern, prefer_curated=True)
    assert primero["solvable"] == segundo["solvable"]
    assert primero["solution"] == segundo["solution"]


def test_lexico_incluye_todas_las_curadas():
    lexico = json.loads(LEXICO.read_text(encoding="utf-8"))
    claves = set(lexico)
    faltantes = []
    for palabra in CURATED_CLUES:
        variantes = {palabra, palabra.replace("Ñ", "N"), palabra.replace("N", "Ñ")}
        if not variantes & claves:
            faltantes.append(palabra)
    assert not faltantes, faltantes
    assert {"AGUAS", "VIDA", "FLORES", "ZAPALLO"} <= claves


def test_pista_albanil_cubre_ambas_formas():
    assert CURATED_CLUES["ALBANIL"] == CURATED_CLUES["ALBAÑIL"]
