"""Contrato del bonus de racha en la configuración de economía."""

import pytest
import pytest_asyncio

pytestmark = pytest.mark.contract


BONUS_ACTIVO = {
    "activo": True,
    "modo": "porcentaje",
    "tramos": [
        {"dias": 20, "valor": 30},
        {"dias": 10, "valor": 10},
        {"dias": 15, "valor": 20},
    ],
}


@pytest_asyncio.fixture
async def config_limpia(test_db, cleanup):
    await test_db["configuracion_economia"].delete_one({"_id": "global_economy"})
    cleanup.add("configuracion_economia", {"_id": "global_economy"})
    return test_db


async def _get_config(client) -> dict:
    response = await client.get("/api/admin/economy/config")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_default_inactivo_con_tres_tramos(client, admin_override, config_limpia):
    bonus = (await _get_config(client))["bonus_racha"]

    assert bonus["activo"] is False
    assert bonus["modo"] == "porcentaje"
    assert [(t["dias"], t["valor"]) for t in bonus["tramos"]] == [
        (10, 10),
        (15, 20),
        (20, 30),
    ]


@pytest.mark.asyncio
async def test_admin_guarda_y_lee_el_bonus_ordenado(client, admin_override, config_limpia):
    response = await client.put(
        "/api/admin/economy/config",
        json={"bonus_racha": BONUS_ACTIVO},
    )
    assert response.status_code == 200

    bonus = (await _get_config(client))["bonus_racha"]
    assert bonus["activo"] is True
    assert bonus["modo"] == "porcentaje"
    assert [(t["dias"], t["valor"]) for t in bonus["tramos"]] == [
        (10, 10),
        (15, 20),
        (20, 30),
    ]


@pytest.mark.asyncio
async def test_omitir_bonus_conserva_la_configuracion_actual(client, admin_override, config_limpia):
    await client.put("/api/admin/economy/config", json={"bonus_racha": BONUS_ACTIVO})

    response = await client.put(
        "/api/admin/economy/config",
        json={"costo_pista_puntos": 35},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["costo_pista_puntos"] == 35
    assert body["bonus_racha"]["activo"] is True


@pytest.mark.parametrize(
    "bonus",
    [
        {"activo": True, "modo": "porcentaje", "tramos": []},
        {
            "activo": True,
            "modo": "porcentaje",
            "tramos": [{"dias": 10, "valor": 10}, {"dias": 10, "valor": 20}],
        },
        {"activo": True, "modo": "porcentaje", "tramos": [{"dias": 0, "valor": 10}]},
        {"activo": True, "modo": "porcentaje", "tramos": [{"dias": 10, "valor": -5}]},
        {"activo": True, "modo": "porcentaje", "tramos": [{"dias": 10, "valor": 501}]},
        {"activo": True, "modo": "otro", "tramos": [{"dias": 10, "valor": 10}]},
    ],
    ids=[
        "activo-sin-tramos",
        "dias-duplicados",
        "dias-fuera-de-rango",
        "valor-negativo",
        "porcentaje-excesivo",
        "modo-desconocido",
    ],
)
@pytest.mark.asyncio
async def test_bonus_invalido_devuelve_422(client, admin_override, config_limpia, bonus):
    response = await client.put(
        "/api/admin/economy/config",
        json={"bonus_racha": bonus},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bonus_corrupto_en_base_cae_a_defaults(client, admin_override, config_limpia):
    await config_limpia["configuracion_economia"].insert_one(
        {"_id": "global_economy", "bonus_racha": {"activo": "sí", "modo": "x"}}
    )

    bonus = (await _get_config(client))["bonus_racha"]

    assert bonus["activo"] is False
    assert bonus["modo"] == "porcentaje"
    assert [t["dias"] for t in bonus["tramos"]] == [10, 15, 20]
