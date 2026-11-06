"""Validación estática de grafos V2: referencias, hojas, pesos y ciclos."""

import pytest

from app.features.narrative.validation import TIPOS_VALIDOS, validar_grafo

pytestmark = pytest.mark.unit


def _nodo(nodo_id: str, *, es_final: bool = False, siguiente: str | None = None, desenlaces=None, opciones=None):
    if opciones is None:
        opciones = [] if es_final else [
            {
                "id": f"opt_{nodo_id}",
                "texto": "Continuar",
                "siguiente_nodo": siguiente,
                "desenlaces": desenlaces or [],
                "condiciones": [],
                "bloqueo_modo": "deshabilitada",
            }
        ]
    return {
        "id": nodo_id,
        "hablante_id": "narrador",
        "texto": f"Texto {nodo_id}",
        "es_final": es_final,
        "opciones": opciones,
        "resultado_texto": "Cierre" if es_final else "",
        "impactos_recursos": [],
        "impactos_afinidad": [],
        "impactos_tags": [],
    }


def _evento(nodos: dict, raiz: str = "inicio", **extra) -> dict:
    doc = {
        "_id": "evt_test",
        "universo_id": "universo_test",
        "titulo": "Evento",
        "imagen": "/x.webp",
        "nodo_raiz": raiz,
        "nodos": nodos,
    }
    doc.update(extra)
    return doc


def _codigos(resultado) -> set[str]:
    return {h.codigo for h in resultado.errores}


def test_grafo_valido_no_reporta_errores():
    grafo = _evento(
        {
            "inicio": _nodo("inicio", siguiente="fin"),
            "fin": _nodo("fin", es_final=True),
        }
    )
    resultado = validar_grafo(grafo, "evento")

    assert resultado.valido
    assert resultado.grafo_id == "evt_test"
    assert resultado.errores == []


def test_referencia_inexistente_es_error():
    grafo = _evento({"inicio": _nodo("inicio", siguiente="no_existe")})
    resultado = validar_grafo(grafo, "evento")

    assert not resultado.valido
    assert "referencia_inexistente" in _codigos(resultado)


def test_nodo_no_final_sin_opciones_es_error():
    grafo = _evento({"inicio": _nodo("inicio", opciones=[]), "fin": _nodo("fin", es_final=True)})
    resultado = validar_grafo(grafo, "evento")

    assert "nodo_sin_opciones" in _codigos(resultado)


def test_nodo_final_con_opciones_es_error():
    final = _nodo("fin", es_final=True)
    final["opciones"] = [{"id": "opt_x", "texto": "x", "siguiente_nodo": "inicio"}]
    grafo = _evento({"inicio": _nodo("inicio", siguiente="fin"), "fin": final})
    resultado = validar_grafo(grafo, "evento")

    assert "nodo_final_con_opciones" in _codigos(resultado)


def test_sin_final_alcanzable_es_error():
    grafo = _evento({"inicio": _nodo("inicio", siguiente="inicio")})
    resultado = validar_grafo(grafo, "evento")

    codigos = _codigos(resultado)
    assert "ciclo_detectado" in codigos
    assert "sin_final_alcanzable" in codigos


def test_ciclo_alcanzable_es_error():
    grafo = _evento(
        {
            "inicio": _nodo("inicio", siguiente="medio"),
            "medio": _nodo("medio", siguiente="inicio"),
            "fin": _nodo("fin", es_final=True),
        }
    )
    resultado = validar_grafo(grafo, "evento")

    assert "ciclo_detectado" in _codigos(resultado)


def test_nodo_inalcanzable_es_advertencia():
    grafo = _evento(
        {
            "inicio": _nodo("inicio", siguiente="fin"),
            "fin": _nodo("fin", es_final=True),
            "huerfano": _nodo("huerfano", siguiente="fin"),
        }
    )
    resultado = validar_grafo(grafo, "evento")

    assert resultado.valido
    assert any(h.codigo == "nodo_inalcanzable" and h.nodo_id == "huerfano" for h in resultado.advertencias)


def test_desenlaces_ponderados_validos():
    grafo = _evento(
        {
            "inicio": _nodo(
                "inicio",
                desenlaces=[
                    {"nodo": "fin_a", "peso": 40},
                    {"nodo": "fin_b", "peso": 60},
                ],
            ),
            "fin_a": _nodo("fin_a", es_final=True),
            "fin_b": _nodo("fin_b", es_final=True),
        }
    )
    resultado = validar_grafo(grafo, "evento")

    assert resultado.valido


def test_desenlaces_sin_peso_positivo_es_error():
    grafo = _evento(
        {
            "inicio": _nodo(
                "inicio",
                desenlaces=[
                    {"nodo": "fin_a", "peso": 0},
                    {"nodo": "fin_b", "peso": -5},
                ],
            ),
            "fin_a": _nodo("fin_a", es_final=True),
            "fin_b": _nodo("fin_b", es_final=True),
        }
    )
    resultado = validar_grafo(grafo, "evento")

    codigos = _codigos(resultado)
    assert "peso_no_positivo" in codigos
    assert "desenlaces_sin_peso_positivo" in codigos


def test_raiz_inexistente_es_error():
    grafo = _evento({"otro": _nodo("otro", es_final=True)}, raiz="inicio")
    resultado = validar_grafo(grafo, "evento")

    assert "nodo_raiz_inexistente" in _codigos(resultado)


def test_raiz_final_es_error():
    grafo = _evento({"inicio": _nodo("inicio", es_final=True)})
    resultado = validar_grafo(grafo, "evento")

    assert "raiz_es_final" in _codigos(resultado)


def test_opcion_duplicada_es_error():
    final_a = _nodo("fin_a", es_final=True)
    final_b = _nodo("fin_b", es_final=True)
    grafo = _evento(
        {
            "inicio": _nodo(
                "inicio",
                opciones=[
                    {"id": "opt_repetida", "texto": "A", "siguiente_nodo": "fin_a"},
                    {"id": "opt_repetida", "texto": "B", "siguiente_nodo": "fin_b"},
                ],
            ),
            "fin_a": final_a,
            "fin_b": final_b,
        }
    )
    resultado = validar_grafo(grafo, "evento")

    assert "opcion_duplicada" in _codigos(resultado)


def test_id_de_nodo_inconsistente_es_error():
    nodo = _nodo("otro_id", es_final=True)
    grafo = _evento({"inicio": nodo})
    resultado = validar_grafo(grafo, "evento")

    assert "id_nodo_inconsistente" in _codigos(resultado)


def test_evento_especial_exige_personaje_y_direccion():
    grafo = _evento({"inicio": _nodo("inicio", es_final=True)})
    grafo["_id"] = "esp_test"
    resultado = validar_grafo(grafo, "evento_especial")

    codigos = _codigos(resultado)
    assert "personaje_id_ausente" in codigos
    assert "direccion_invalida" in codigos


def test_evento_especial_valido():
    grafo = _evento(
        {
            "inicio": _nodo("inicio", siguiente="fin"),
            "fin": _nodo("fin", es_final=True),
        }
    )
    grafo.update({"_id": "esp_test", "personaje_id": "pj_elena", "direccion": "lealtad"})
    resultado = validar_grafo(grafo, "evento_especial")

    assert resultado.valido


def test_requisito_autorreferente_es_error():
    grafo = _evento(
        {"inicio": _nodo("inicio", es_final=True)},
        requisitos_eventos_previos=["evt_test"],
    )
    resultado = validar_grafo(grafo, "evento")

    assert "requisito_autorreferente" in _codigos(resultado)


def test_tipo_invalido_se_reporta():
    resultado = validar_grafo({}, "desconocido")

    assert not resultado.valido
    assert [h.codigo for h in resultado.errores] == ["tipo_invalido"]
    assert "evento" in TIPOS_VALIDOS


# ---------------------------------------------------------------------------
# Validación semántica del desenlace: lo que el motor no puede ejecutar
# ---------------------------------------------------------------------------

def _nodo_final_con_efectos(efectos, **extra):
    nodo = _nodo("fin", es_final=True)
    nodo.update(extra)
    nodo["efectos"] = efectos
    return nodo


def _con_contexto(recursos=("oro", "pueblo"), acciones=None, frecuencias=None):
    return {
        "recursos_validos": set(recursos),
        "catalogo_acciones": acciones or {},
        "catalogo_frecuencias": frecuencias or {},
    }


def test_efecto_bien_declarado_pasa():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {
                "disparador": "al_desenlace",
                "acciones": [{"accion_id": "modificar_recurso", "parametros": {"clave": "oro", "valor": -5}}],
            }
        ], impactos_recursos=[{"recurso": "pueblo", "delta": 3}]),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    assert resultado.valido, [h.as_dict() for h in resultado.errores]


def test_recurso_inexistente_en_impacto_y_en_efecto_es_error():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {
                "disparador": "al_desenlace",
                "acciones": [{"accion_id": "modificar_recurso", "parametros": {"clave": "azufre", "valor": 10}}],
            }
        ], impactos_recursos=[{"recurso": "madera", "delta": 4}]),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    codigos = [h.codigo for h in resultado.errores]
    assert "recurso_inexistente" in codigos
    assert {h.nodo_id for h in resultado.errores if h.codigo == "recurso_inexistente"} == {"fin"}


def test_frecuencia_fuera_del_catalogo_es_error():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {
                "frecuencia_id": "cada_4_meses",
                "acciones": [{"accion_id": "otorgar_tag", "parametros": {"tag": "sequia"}}],
            }
        ]),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    assert "evento_no_despachado" in _codigos(resultado)

    # La misma frecuencia sí es ejecutable cuando el universo la catalogó
    resultado = validar_grafo(
        grafo,
        "evento",
        **_con_contexto(frecuencias={"cada_4_meses": {"id": "cada_4_meses", "evento_motor": "inicio_mes", "cada": 4}}),
    )
    assert resultado.valido, [h.as_dict() for h in resultado.errores]


def test_accion_que_no_es_catalogo_ni_primitiva_es_error():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {
                "disparador": "al_desenlace",
                "acciones": [{"accion_id": "invocar_dragon", "parametros": {}}],
            }
        ]),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    assert "accion_desconocida" in _codigos(resultado)


def test_accion_catalogada_se_resuelve_por_su_primitiva():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {
                "disparador": "al_desenlace",
                "acciones": [{"accion_id": "tributo_real", "parametros": {"clave": "oro", "valor": -5}}],
            }
        ]),
    })
    resultado = validar_grafo(
        grafo,
        "evento",
        **_con_contexto(acciones={"tributo_real": {"primitiva": "modificar_recurso"}}),
    )

    assert resultado.valido, [h.as_dict() for h in resultado.errores]

    # Y el recurso sigue siendo exigido aunque la acción exista en el catálogo
    resultado = validar_grafo(
        grafo,
        "evento",
        **_con_contexto(recursos=("pueblo",), acciones={"tributo_real": {"primitiva": "modificar_recurso"}}),
    )
    assert "recurso_inexistente" in _codigos(resultado)


def test_efecto_sin_evento_o_sin_acciones_es_error():
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {"acciones": []},
            {"disparador": "al_desenlace", "acciones": []},
        ]),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    assert {"efecto_sin_evento", "efecto_sin_acciones"} <= _codigos(resultado)


def test_efectos_en_nodo_intermedio_es_error():
    grafo = _evento({
        "inicio": {
            **_nodo("inicio", siguiente="fin"),
            "efectos": [{"disparador": "al_desenlace", "acciones": [{"accion_id": "otorgar_tag", "parametros": {"tag": "x"}}]}],
        },
        "fin": _nodo("fin", es_final=True),
    })
    resultado = validar_grafo(grafo, "evento", **_con_contexto())

    assert "efectos_en_nodo_no_final" in _codigos(resultado)


def test_tipo_desenlace_desconocido_es_error():
    fin = _nodo("fin", es_final=True)
    fin["tipo_desenlace"] = "doloroso"
    grafo = _evento({"inicio": _nodo("inicio", siguiente="fin"), "fin": fin})
    resultado = validar_grafo(grafo, "evento")

    assert "tipo_desenlace_invalido" in _codigos(resultado)


def test_validacion_estructural_no_exige_catalogos():
    """Sin catálogo, el validador puro no puede opinar sobre recursos ni frecuencias."""
    grafo = _evento({
        "inicio": _nodo("inicio", siguiente="fin"),
        "fin": _nodo_final_con_efectos([
            {"frecuencia_id": "cada_4_meses", "acciones": [{"accion_id": "modificar_recurso", "parametros": {"clave": "oro"}}]}
        ], impactos_recursos=[{"recurso": "azufre", "delta": 1}]),
    })
    resultado = validar_grafo(grafo, "evento")

    assert resultado.valido
