from app.features.narrative.engine.rule_engine import ejecutar_accion
from app.features.narrative.schemas.rules_schemas import PrimitivaOperacionEnum

def test_mutar_estado_entidad_alta_y_baja_tag():
    run_data = {
        "tags_activos": ["comercio"],
        "recursos": {"oro": 50}
    }

    # 1. Alta de tag
    accion_alta = {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value,
        "entidad": "tag",
        "operacion": "alta",
        "id_entidad": "disciplina_militar"
    }
    ejecutar_accion(accion_alta, run_data)
    assert "disciplina_militar" in run_data["tags_activos"]
    assert "comercio" in run_data["tags_activos"]

    # 2. Idempotencia en alta
    ejecutar_accion(accion_alta, run_data)
    assert run_data["tags_activos"].count("disciplina_militar") == 1

    # 3. Baja de tag
    accion_baja = {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value,
        "entidad": "tag",
        "operacion": "baja",
        "id_entidad": "comercio"
    }
    ejecutar_accion(accion_baja, run_data)
    assert "comercio" not in run_data["tags_activos"]
    assert "disciplina_militar" in run_data["tags_activos"]


def test_mutar_estado_entidad_alta_y_baja_personaje():
    run_data = {
        "corte_activa": ["pj_marcus", "pj_elena"],
        "afinidad": {"pj_marcus": 60, "pj_elena": 50},
        "modificadores_pasivos": [
            {"fuente": "pj_marcus", "tipo": "amortiguar_danio", "clave": "ejercito", "reduccion_porcentual": 25},
            {"fuente": "card_escudo", "tipo": "amortiguar_danio", "clave": "moral", "reduccion_porcentual": 10}
        ],
        "tags_activos": ["militar", "orden"],
        "tags_origen": {"pj_marcus": ["orden"]},
        "mes_actual": 3
    }

    # 1. Alta de nuevo personaje
    accion_alta_pj = {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value,
        "entidad": "personaje",
        "operacion": "alta",
        "id_entidad": "pj_tomas"
    }
    ejecutar_accion(accion_alta_pj, run_data)
    assert "pj_tomas" in run_data["corte_activa"]
    assert run_data["afinidad"]["pj_tomas"] == 50
    assert run_data["adquisiciones"]["pj_tomas"]["mes"] == 3

    # 2. Baja de pj_marcus con Limpieza Total
    accion_baja_pj = {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value,
        "entidad": "personaje",
        "operacion": "baja",
        "id_entidad": "pj_marcus"
    }
    ejecutar_accion(accion_baja_pj, run_data)

    # Verificaciones de limpieza total
    assert "pj_marcus" not in run_data["corte_activa"]
    assert "pj_marcus" not in run_data["afinidad"]
    # El amortiguador de Marcus desapareció, pero el de la carta sigue
    assert len(run_data["modificadores_pasivos"]) == 1
    assert run_data["modificadores_pasivos"][0]["fuente"] == "card_escudo"
    # El tag propio de Marcus se retiró
    assert "orden" not in run_data["tags_activos"]
    assert "militar" in run_data["tags_activos"]
