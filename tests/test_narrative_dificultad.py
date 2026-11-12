"""Modo fácil del narrativo: amortigua pérdidas de recursos con el factor del universo."""

import uuid

import pytest

from app.features.narrative.engine.rule_engine import aplicar_delta_recurso

FECHA = "2099-02-01"


def test_modo_facil_amortigua_solo_las_perdidas():
    run = {"recursos": {"oro": 100}, "dificultad_reduccion": 35}

    assert aplicar_delta_recurso(run, "oro", -40) == 74
    assert aplicar_delta_recurso(run, "oro", 10) == 84


def test_modo_normal_no_amortigua():
    run = {"recursos": {"oro": 100}, "dificultad_reduccion": 0}

    assert aplicar_delta_recurso(run, "oro", -40) == 60


def test_facil_se_combina_con_amortiguadores_pasivos():
    run = {
        "recursos": {"oro": 100},
        "dificultad_reduccion": 50,
        "modificadores_pasivos": [
            {"tipo": "amortiguar_danio", "clave": "oro", "reduccion_porcentual": 50}
        ],
    }

    assert aplicar_delta_recurso(run, "oro", -40) == 90


async def _preparar_universo(test_db, cleanup, reduccion):
    sufijo = uuid.uuid4().hex[:8]
    universo_id = f"universo_dificultad_{sufijo}"
    personajes = [f"pj_{sufijo}_{i}" for i in range(3)]
    cartas = [f"carta_{sufijo}_{i}" for i in range(3)]

    await test_db["narrative_settings"].insert_one({
        "_id": universo_id,
        "nombre": "Universo de prueba",
        "descripcion": "Solo para tests de dificultad",
        "motor": "v2",
        "recursos": [{"clave": "oro", "nombre": "Oro", "min": 0, "max": 100, "inicial": 100}],
        "dificultad_facil_reduccion": reduccion,
    })
    cleanup.add("narrative_settings", {"_id": universo_id})

    for pid in personajes:
        await test_db["narrative_characters"].insert_one({
            "_id": pid,
            "universo_id": universo_id,
            "nombre": pid,
            "afinidad_inicial": 50,
            "tags": [],
            "efectos": [],
        })
    cleanup.add("narrative_characters", {"universo_id": universo_id})

    for cid in cartas:
        await test_db["narrative_cards"].insert_one({
            "_id": cid,
            "universo_id": universo_id,
            "nombre": cid,
            "tags": [],
            "efectos": [],
        })
    cleanup.add("narrative_cards", {"universo_id": universo_id})

    config = {
        "universo_id": universo_id,
        "atributos_iniciales": {"oro": 100},
        "setup_corte_ofrecidos_ids": personajes,
        "setup_cartas_ofrecidas_ids": cartas,
        "pool_cartas_mensuales_ids": [],
    }
    return config, personajes, cartas


async def _iniciar(client, make_guest_credential, test_db, cleanup, dificultad, reduccion):
    config, personajes, cartas = await _preparar_universo(test_db, cleanup, reduccion)
    await test_db["daily_challenges"].replace_one(
        {"game_id": "narrativo", "date": FECHA},
        {
            "game_id": "narrativo",
            "date": FECHA,
            "difficulty": "normal",
            "title": "Desafío narrativo de prueba",
            "config": config,
        },
        upsert=True,
    )
    cleanup.add("daily_challenges", {"game_id": "narrativo", "date": FECHA})

    guest_id, headers = make_guest_credential()
    cleanup.add("narrative_runs", {"guest_id": guest_id, "date": FECHA})
    body = {
        "date": FECHA,
        "corte_elegida_ids": personajes,
        "cartas_iniciales_ids": cartas,
    }
    if dificultad is not None:
        body["dificultad"] = dificultad

    response = await client.post("/api/narrative/v2/partida/iniciar", json=body, headers=headers)
    assert response.status_code == 200, response.text

    run = await test_db["narrative_runs"].find_one({"guest_id": guest_id, "date": FECHA})
    assert run is not None
    return run


@pytest.mark.asyncio
async def test_iniciar_facil_guarda_el_factor_del_universo(
    client, test_db, make_guest_credential, cleanup
):
    run = await _iniciar(client, make_guest_credential, test_db, cleanup, "facil", 40)

    assert run["dificultad"] == "facil"
    assert run["dificultad_reduccion"] == 40


@pytest.mark.asyncio
async def test_iniciar_sin_flag_queda_en_normal(
    client, test_db, make_guest_credential, cleanup
):
    run = await _iniciar(client, make_guest_credential, test_db, cleanup, None, 40)

    assert run["dificultad"] == "normal"
    assert run["dificultad_reduccion"] == 0


@pytest.mark.asyncio
async def test_admin_conserva_el_factor_si_el_panel_no_lo_envia(
    client, test_db, admin_override, cleanup
):
    sufijo = uuid.uuid4().hex[:8]
    universo_id = f"universo_admin_{sufijo}"
    await test_db["narrative_settings"].insert_one({
        "_id": universo_id,
        "nombre": "Universo admin",
        "descripcion": "Solo para tests",
        "motor": "v2",
        "dificultad_facil_reduccion": 60,
        "recursos": [{"clave": "oro", "nombre": "Oro"}],
    })
    cleanup.add("narrative_settings", {"_id": universo_id})

    response = await client.post(
        "/api/narrative/admin/universos",
        json={
            "_id": universo_id,
            "nombre": "Universo admin",
            "descripcion": "Editado desde el panel",
            "recursos": [{"clave": "oro", "nombre": "Oro"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["dificultad_facil_reduccion"] == 60

    guardado = await test_db["narrative_settings"].find_one({"_id": universo_id})
    assert guardado["dificultad_facil_reduccion"] == 60
