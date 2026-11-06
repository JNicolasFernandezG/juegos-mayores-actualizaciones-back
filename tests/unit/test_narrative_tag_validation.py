from app.features.narrative.validation.graph_validator import (
    hallazgos_de_efectos,
    hallazgos_de_tags_referenciados,
)

TAGS = {"fe", "religion", "militar"}


def test_tags_referenciados_detecta_tag_inexistente():
    hallazgos = hallazgos_de_tags_referenciados(["fe", "fantasma"], tags_validos=TAGS)
    assert [h.codigo for h in hallazgos] == ["tag_inexistente"]
    assert "fantasma" in hallazgos[0].mensaje


def test_condiciones_tiene_tag_contra_catalogo():
    hallazgos = hallazgos_de_tags_referenciados(
        condiciones=[{"tipo": "tiene_tag", "tag": "sello_real"}],
        tags_validos=TAGS,
    )
    assert [h.codigo for h in hallazgos] == ["tag_inexistente"]


def test_sin_catalogo_no_valida_tags():
    assert hallazgos_de_tags_referenciados(["fantasma"], tags_validos=None) == []


def _efecto(accion_id, parametros, condiciones=None):
    return {
        "frecuencia_id": "al_obtener",
        "condiciones": condiciones or [],
        "acciones": [{"accion_id": accion_id, "parametros": parametros}],
    }


def test_otorgar_tag_valida_catalogo():
    hallazgos = hallazgos_de_efectos(
        [_efecto("otorgar_tag", {"tag": "fantasma"})], tags_validos=TAGS
    )
    assert [h.codigo for h in hallazgos] == ["tag_inexistente"]


def test_mutar_estado_entidad_tag_valida_catalogo():
    hallazgos = hallazgos_de_efectos(
        [_efecto("mutar_estado_entidad", {"entidad": "tag", "operacion": "alta", "id_entidad": "fantasma"})],
        tags_validos=TAGS,
    )
    assert [h.codigo for h in hallazgos] == ["tag_inexistente"]


def test_mutar_estado_entidad_personaje_no_valida_tags():
    hallazgos = hallazgos_de_efectos(
        [_efecto("mutar_estado_entidad", {"entidad": "personaje", "operacion": "alta", "id_entidad": "pj_x"})],
        tags_validos=TAGS,
    )
    assert hallazgos == []


def test_condiciones_del_efecto_validan_tag():
    hallazgos = hallazgos_de_efectos(
        [_efecto("otorgar_tag", {"tag": "fe"}, condiciones=[{"tipo": "tiene_tag", "tag": "fantasma"}])],
        tags_validos=TAGS,
    )
    assert [h.codigo for h in hallazgos] == ["tag_inexistente"]
