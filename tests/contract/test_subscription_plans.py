"""Catálogo de planes de suscripción: lectura del jugador y administración."""

import pytest
import pytest_asyncio

pytestmark = pytest.mark.contract


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _plan(**extra) -> dict:
    base = {
        "codigo": "premium",
        "nombre": "Premium",
        "descripcion": "Todo el archivo de desafíos, sin esperas.",
        "precio": {"monto": 5000, "moneda": "ARS"},
        "descuento_anual_pct": 20,
        "beneficios": ["Días históricos sin costo", "Pistas incluidas"],
        "orden": 10,
        "visible": True,
        "habilitado": False,
    }
    base.update(extra)
    return base


@pytest_asyncio.fixture
async def planes_limpios(test_db, cleanup):
    await test_db["planes_suscripcion"].delete_many({})
    cleanup.add("planes_suscripcion", {})
    return test_db["planes_suscripcion"]


@pytest_asyncio.fixture
async def config_limpia(test_db, cleanup):
    await test_db["suscripcion_config"].delete_many({})
    cleanup.add("suscripcion_config", {})
    return test_db["suscripcion_config"]


@pytest.mark.asyncio
async def test_planes_exige_autenticacion(client, planes_limpios):
    response = await client.get("/api/subscription/plans")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jugador_solo_ve_planes_visibles_y_ordenados(
    client, planes_limpios, config_limpia, seeded_user, make_token
):
    await planes_limpios.insert_many(
        [
            _plan(codigo="plan-caro", nombre="Caro", orden=20),
            _plan(codigo="plan-base", nombre="Base", orden=5, habilitado=True),
            _plan(codigo="plan-oculto", nombre="Oculto", orden=1, visible=False),
        ]
    )
    user = await seeded_user()

    response = await client.get(
        "/api/subscription/plans", headers=_auth(make_token(user["id"]))
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["anual_habilitado"] is False
    assert [plan["codigo"] for plan in body["planes"]] == ["plan-base", "plan-caro"]
    assert body["planes"][0]["precio"] == {"monto": 5000, "moneda": "ARS"}
    assert body["planes"][0]["habilitado"] is True
    assert body["planes"][1]["habilitado"] is False


@pytest.mark.asyncio
async def test_precio_anual_deriva_del_mensual_y_el_descuento(
    client, admin_override, planes_limpios
):
    creado = await client.post(
        "/api/admin/subscription/plans",
        json=_plan(codigo="sin-descuento", descuento_anual_pct=0),
    )
    assert creado.status_code == 200, creado.text
    assert creado.json()["precio_anual"] == {"monto": 60000, "moneda": "ARS"}

    con_descuento = await client.post(
        "/api/admin/subscription/plans",
        json=_plan(codigo="con-descuento", descuento_anual_pct=25, orden=20),
    )
    assert con_descuento.status_code == 200, con_descuento.text
    assert con_descuento.json()["descuento_anual_pct"] == 25
    assert con_descuento.json()["precio_anual"] == {"monto": 45000, "moneda": "ARS"}

    sin_monto = await client.post(
        "/api/admin/subscription/plans",
        json=_plan(
            codigo="a-confirmar",
            precio={"monto": None, "moneda": "ARS"},
            descuento_anual_pct=10,
            orden=30,
        ),
    )
    assert sin_monto.status_code == 200, sin_monto.text
    assert sin_monto.json()["precio_anual"] == {"monto": None, "moneda": "ARS"}


@pytest.mark.asyncio
async def test_plan_legado_sin_descuento_sigue_leyendo_su_precio(
    client, planes_limpios, config_limpia, seeded_user, make_token
):
    await planes_limpios.insert_one(
        {
            "codigo": "legado",
            "nombre": "Legado",
            "precio": {"monto": 4999, "moneda": "ARS", "periodo": "mensual"},
            "visible": True,
            "habilitado": False,
        }
    )
    user = await seeded_user()

    response = await client.get(
        "/api/subscription/plans", headers=_auth(make_token(user["id"]))
    )

    assert response.status_code == 200, response.text
    plan = response.json()["planes"][0]
    assert plan["precio"] == {"monto": 4999, "moneda": "ARS"}
    assert plan["descuento_anual_pct"] == 0
    assert plan["precio_anual"] == {"monto": 59988, "moneda": "ARS"}


@pytest.mark.asyncio
async def test_admin_crea_edita_y_elimina_planes(
    client, admin_override, planes_limpios
):
    assert (await client.get("/api/admin/subscription/plans")).json() == []

    creado = await client.post("/api/admin/subscription/plans", json=_plan())
    assert creado.status_code == 200, creado.text
    assert creado.json()["codigo"] == "premium"
    assert creado.json()["visible"] is True
    assert creado.json()["habilitado"] is False

    duplicado = await client.post("/api/admin/subscription/plans", json=_plan())
    assert duplicado.status_code == 409

    editado = await client.put(
        "/api/admin/subscription/plans/premium",
        json={"visible": False, "habilitado": True, "orden": 3, "descuento_anual_pct": 50},
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["visible"] is False
    assert editado.json()["habilitado"] is True
    assert editado.json()["orden"] == 3
    assert editado.json()["descuento_anual_pct"] == 50
    assert editado.json()["precio_anual"] == {"monto": 30000, "moneda": "ARS"}

    listado = (await client.get("/api/admin/subscription/plans")).json()
    assert [plan["codigo"] for plan in listado] == ["premium"]

    eliminado = await client.delete("/api/admin/subscription/plans/premium")
    assert eliminado.status_code == 200
    assert eliminado.json()["success"] is True
    assert (await client.get("/api/admin/subscription/plans")).json() == []

    faltante = await client.delete("/api/admin/subscription/plans/premium")
    assert faltante.status_code == 404


@pytest.mark.asyncio
async def test_plan_invalido_es_rechazado(client, admin_override, planes_limpios):
    codigo_invalido = await client.post(
        "/api/admin/subscription/plans", json=_plan(codigo="Premium Mensual")
    )
    assert codigo_invalido.status_code == 422

    precio_negativo = await client.post(
        "/api/admin/subscription/plans",
        json=_plan(precio={"monto": -10, "moneda": "ARS"}),
    )
    assert precio_negativo.status_code == 422

    descuento_excesivo = await client.post(
        "/api/admin/subscription/plans", json=_plan(descuento_anual_pct=150)
    )
    assert descuento_excesivo.status_code == 422

    beneficios_excesivos = await client.post(
        "/api/admin/subscription/plans", json=_plan(beneficios=["x"] * 9)
    )
    assert beneficios_excesivos.status_code == 422


@pytest.mark.asyncio
async def test_admin_controla_las_membresias_anuales(
    client, admin_override, planes_limpios, config_limpia, seeded_user, make_token
):
    inicial = await client.get("/api/admin/subscription/settings")
    assert inicial.status_code == 200, inicial.text
    assert inicial.json()["anual_habilitado"] is False

    await planes_limpios.insert_one(_plan())
    user = await seeded_user()
    visible = await client.get(
        "/api/subscription/plans", headers=_auth(make_token(user["id"]))
    )
    assert visible.json()["anual_habilitado"] is False

    activado = await client.put(
        "/api/admin/subscription/settings", json={"anual_habilitado": True}
    )
    assert activado.status_code == 200, activado.text
    assert activado.json()["anual_habilitado"] is True

    visible = await client.get(
        "/api/subscription/plans", headers=_auth(make_token(user["id"]))
    )
    assert visible.json()["anual_habilitado"] is True

    desactivado = await client.put(
        "/api/admin/subscription/settings", json={"anual_habilitado": False}
    )
    assert desactivado.status_code == 200, desactivado.text
    assert desactivado.json()["anual_habilitado"] is False


@pytest.mark.asyncio
async def test_admin_exige_rol_de_operador(
    client, planes_limpios, config_limpia, seeded_user, make_token
):
    user = await seeded_user()
    headers = _auth(make_token(user["id"]))

    assert (await client.get("/api/admin/subscription/plans", headers=headers)).status_code == 403
    assert (await client.get("/api/admin/subscription/settings", headers=headers)).status_code == 403
    assert (
        await client.put(
            "/api/admin/subscription/settings",
            headers=headers,
            json={"anual_habilitado": True},
        )
    ).status_code == 403
