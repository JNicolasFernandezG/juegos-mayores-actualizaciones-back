"""Conversión mecánica de contenido V1 a grafos V2 (funciones puras, sin base de datos)."""

import pytest

from app.scripts.convertir_v1_a_v2 import NODO_RAIZ, convertir_conversacion, convertir_evento

pytestmark = pytest.mark.unit


def _condicion_personaje(personaje_id: str) -> dict:
    return {"tipo": "tiene_personaje", "personaje_id": personaje_id}


def _resultado(res_id: str, **extra) -> dict:
    doc = {
        "_id": res_id,
        "universo_id": "corte_medieval",
        "titulo": f"Titulo {res_id}",
        "texto": f"Texto largo de {res_id}",
        "imagen": f"/assets/narrative/results/{res_id}.webp",
        "tipo_resultado": "positivo",
        "impacto_afinidad": [],
        "efectos": [
            {
                "disparador": "al_obtener",
                "condiciones": [],
                "accion": {"tipo": "modificar_recurso", "clave": "oro", "tipo_calculo": "fijo", "valor": -15.0},
            }
        ],
    }
    doc.update(extra)
    return doc


_RESULTADOS = {
    "res_a": _resultado("res_a"),
    "res_b": _resultado("res_b", tipo_resultado="negativo"),
    "res_c": _resultado("res_c", tipo_resultado="neutro", efectos=[]),
}


def _evento(opciones: list, **extra) -> dict:
    doc = {
        "_id": "evt_origen",
        "universo_id": "corte_medieval",
        "titulo": "Evento V1",
        "descripcion": "Descripcion del evento V1.",
        "imagen": "/assets/narrative/events/origen.webp",
        "peso_base": 100.0,
        "tags_tematicos": ["clima"],
        "opciones": opciones,
    }
    doc.update(extra)
    return doc


def _opcion(op_id: str, resultados: list, **extra) -> dict:
    opcion = {
        "id": op_id,
        "texto": f"Texto de {op_id}",
        "es_secreta": False,
        "condiciones": [],
        "resultados_posibles": [
            {"resultado_id": r, "peso_base": w, "modificadores_probabilidad": []} for r, w in resultados
        ],
    }
    opcion.update(extra)
    return opcion


def test_opcion_con_un_solo_resultado_usa_destino_fijo():
    grafo, avisos = convertir_evento(_evento([_opcion("op_a", [("res_a", 100.0)])]), _RESULTADOS)

    assert avisos == []
    assert grafo["nodo_raiz"] == NODO_RAIZ
    opcion = grafo["nodos"][NODO_RAIZ]["opciones"][0]
    assert opcion["siguiente_nodo"] == "fin_res_a"
    assert opcion["desenlaces"] == []


def test_opcion_con_varios_resultados_conserva_pesos_y_modificadores():
    opcion = _opcion(
        "op_a",
        [("res_a", 60.0), ("res_b", 40.0)],
    )
    opcion["resultados_posibles"][0]["modificadores_probabilidad"] = [
        {"condicion": _condicion_personaje("pj_elena"), "delta_peso": 30.0, "explicacion": "+30% por Elena"}
    ]

    grafo, _ = convertir_evento(_evento([opcion]), _RESULTADOS)

    desenlaces = grafo["nodos"][NODO_RAIZ]["opciones"][0]["desenlaces"]
    assert [d["nodo"] for d in desenlaces] == ["fin_res_a", "fin_res_b"]
    assert [d["peso"] for d in desenlaces] == [60.0, 40.0]
    assert desenlaces[0]["modificadores_probabilidad"][0]["delta_peso"] == 30.0


def test_el_efecto_al_obtener_de_v1_se_convierte_en_impacto_del_nodo_final():
    grafo, _ = convertir_evento(_evento([_opcion("op_a", [("res_a", 100.0)])]), _RESULTADOS)

    final = grafo["nodos"]["fin_res_a"]
    assert final["es_final"] is True
    assert final["impactos_recursos"] == [{"recurso": "oro", "delta": -15}]
    assert final["efectos"] == []
    assert final["tipo_desenlace"] == "positivo"
    assert final["imagen"] == "/assets/narrative/results/res_a.webp"
    assert final["resultado_texto"] == "Texto largo de res_a"


def test_un_efecto_periodico_no_se_convierte_en_impacto():
    resultado = _resultado(
        "res_c",
        efectos=[
            {
                "disparador": "cada_mes",
                "condiciones": [],
                "accion": {"tipo": "modificar_recurso", "clave": "fe", "tipo_calculo": "fijo", "valor": 2.0},
            }
        ],
    )

    grafo, _ = convertir_evento(_evento([_opcion("op_a", [("res_c", 100.0)])]), {**_RESULTADOS, "res_c": resultado})

    final = grafo["nodos"]["fin_res_c"]
    assert final["impactos_recursos"] == []
    assert final["efectos"][0]["disparador"] == "cada_mes"


def test_la_opcion_secreta_se_convierte_en_opcion_oculta():
    grafo, _ = convertir_evento(
        _evento([_opcion("op_c", [("res_a", 100.0)], es_secreta=True, condiciones=[{"tipo": "tiene_tag", "tag": "sello_real"}])]),
        _RESULTADOS,
    )

    opcion = grafo["nodos"][NODO_RAIZ]["opciones"][0]
    assert opcion["bloqueo_modo"] == "oculta"
    assert opcion["condiciones"] == [{"tipo": "tiene_tag", "tag": "sello_real"}]


def test_un_resultado_inexistente_se_avisa_y_no_ensucia_el_grafo():
    grafo, avisos = convertir_evento(
        _evento([_opcion("op_a", [("res_a", 50.0), ("res_fantasma", 50.0)])]),
        _RESULTADOS,
    )

    assert any("res_fantasma" in a for a in avisos)
    assert "fin_res_fantasma" not in grafo["nodos"]
    # Queda un solo desenlace resoluble, así que pasa a destino fijo.
    assert grafo["nodos"][NODO_RAIZ]["opciones"][0]["siguiente_nodo"] == "fin_res_a"


def test_evento_sin_opciones_resolubles_se_rechaza():
    grafo, avisos = convertir_evento(_evento([_opcion("op_a", [("res_fantasma", 100.0)])]), _RESULTADOS)

    assert grafo is None
    assert "ninguna opción resoluble" in avisos[0]


def test_conversacion_encadena_frases_y_decide_en_la_ultima():
    conv = {
        "_id": "conv_origen",
        "universo_id": "corte_medieval",
        "titulo": "Conversación V1",
        "imagen": "/assets/narrative/conversations/sala.webp",
        "requisitos": [{"personajeId": "pj_elena"}, {"personajeId": "pj_marcus"}],
        "frases": [
            {"personajeId": "pj_marcus", "texto": "Primera frase."},
            {"personajeId": "pj_elena", "texto": "Segunda frase."},
        ],
        "decisiones": [
            {
                "opcion": 1,
                "texto": "Apoyar a Elena",
                "condiciones": [],
                "resultado_texto": "Marcus acata con desagrado.",
                "impacto_afinidad": [
                    {"personaje_id": "pj_elena", "delta": 15},
                    {"personaje_id": "pj_marcus", "delta": -15},
                ],
            },
            {"opcion": 2, "texto": "Apoyar a Marcus", "condiciones": [], "resultado_texto": "Elena toma nota.", "impacto_afinidad": []},
        ],
    }

    grafo, avisos = convertir_conversacion(conv)

    assert avisos == []
    assert grafo["requisitos"] == ["pj_elena", "pj_marcus"]
    assert grafo["nodo_raiz"] == "frase_1"
    assert grafo["nodos"]["frase_1"]["opciones"][0]["siguiente_nodo"] == "frase_2"
    assert [o["id"] for o in grafo["nodos"]["frase_2"]["opciones"]] == ["opt_1", "opt_2"]
    assert grafo["nodos"]["fin_op_1"]["impactos_afinidad"] == [
        {"personaje_id": "pj_elena", "delta": 15},
        {"personaje_id": "pj_marcus", "delta": -15},
    ]
    assert grafo["nodos"]["fin_op_1"]["resultado_texto"] == "Marcus acata con desagrado."


def test_conversacion_sin_decisiones_se_rechaza():
    grafo, avisos = convertir_conversacion({"_id": "conv_vacia", "universo_id": "corte_medieval", "frases": [], "decisiones": []})

    assert grafo is None
    assert "no tiene decisiones" in avisos[0]
