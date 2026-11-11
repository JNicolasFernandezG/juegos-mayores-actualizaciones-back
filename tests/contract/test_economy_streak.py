"""Racha diaria derivada de los ingresos (user_presence), expuesta en la economía."""

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.shared.clock import today_art
from app.shared.streak import calcular_racha, registrar_ingreso

pytestmark = pytest.mark.contract


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fecha(dias_atras: int) -> str:
    return (today_art() - timedelta(days=dias_atras)).isoformat()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _ingreso(test_db, user_id: int, fecha: str):
    await test_db["user_presence"].insert_one(
        {
            "user_id": user_id,
            "date": fecha,
            "first_seen_at": _ahora(),
            "last_seen_at": _ahora(),
        }
    )


async def _intento(test_db, user_id: int, fecha: str, **extra):
    doc = {
        "user_id": user_id,
        "game_id": "wordle",
        "date": fecha,
        "mode": "daily",
        "status": "completed",
        "attempts": 1,
        "stars": 3,
        "score": 100,
        **extra,
    }
    await test_db["user_attempts"].insert_one(doc)


async def _economia(client, token: str) -> dict:
    response = await client.get("/api/economy/me", headers=_auth(token))
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_primer_ingreso_inicia_la_racha(client, test_db, seeded_user, make_token):
    user = await seeded_user()

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 1
    assert body["racha_ultima_fecha"] == _fecha(0)
    assert body["racha_hoy_ingresada"] is True
    assert await test_db["user_presence"].count_documents({"user_id": user["id"]}) == 1


@pytest.mark.asyncio
async def test_segundo_ingreso_el_mismo_dia_no_suma(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    token = make_token(user["id"])

    primero = await _economia(client, token)
    segundo = await _economia(client, token)

    assert primero["racha"] == segundo["racha"] == 1
    assert await test_db["user_presence"].count_documents({"user_id": user["id"]}) == 1


@pytest.mark.asyncio
async def test_ingresos_consecutivos_suman(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    await _ingreso(test_db, user["id"], _fecha(1))
    await _ingreso(test_db, user["id"], _fecha(2))

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 3
    assert body["racha_ultima_fecha"] == _fecha(0)
    assert body["racha_hoy_ingresada"] is True


@pytest.mark.asyncio
async def test_dia_salteado_reinicia_la_racha(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    await _ingreso(test_db, user["id"], _fecha(2))
    await _ingreso(test_db, user["id"], _fecha(3))

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 1
    assert body["racha_ultima_fecha"] == _fecha(0)


@pytest.mark.asyncio
async def test_desafios_completados_ya_no_dan_racha(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    for dias in (0, 1, 2):
        await _intento(test_db, user["id"], _fecha(dias))

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 1
    assert body["racha_ultima_fecha"] == _fecha(0)


@pytest.mark.asyncio
async def test_fecha_futura_no_cuenta(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    await _ingreso(test_db, user["id"], _fecha(-1))

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 1
    assert body["racha_ultima_fecha"] == _fecha(0)


@pytest.mark.asyncio
async def test_racha_no_se_mezcla_entre_usuarios(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    otro = await seeded_user()
    for dias in (0, 1, 2):
        await _ingreso(test_db, otro["id"], _fecha(dias))

    body = await _economia(client, make_token(user["id"]))

    assert body["racha"] == 1


@pytest.mark.asyncio
async def test_sesion_por_cookie_registra_el_ingreso(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    client.cookies.set("access_token", make_token(user["id"]))

    response = await client.get("/api/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["racha"] == 1
    assert body["racha_ultima_fecha"] == _fecha(0)
    assert body["racha_hoy_ingresada"] is True
    assert await test_db["user_presence"].count_documents({"user_id": user["id"]}) == 1


@pytest.mark.asyncio
async def test_ingresos_concurrentes_registran_un_solo_dia(test_db, seeded_user):
    user = await seeded_user()

    await asyncio.gather(*(registrar_ingreso(user["id"]) for _ in range(5)))

    assert await test_db["user_presence"].count_documents({"user_id": user["id"]}) == 1


@pytest.mark.asyncio
async def test_calculo_deterministico_con_gracia_de_un_dia(test_db, seeded_user):
    user = await seeded_user()
    await _ingreso(test_db, user["id"], "2026-11-09")
    await _ingreso(test_db, user["id"], "2026-11-10")

    sin_ingreso_hoy = await calcular_racha(user["id"], hoy=date(2026, 11, 11))
    assert sin_ingreso_hoy.actual == 2
    assert sin_ingreso_hoy.hoy_ingresada is False

    await registrar_ingreso(user["id"], hoy=date(2026, 11, 11))
    con_ingreso_hoy = await calcular_racha(user["id"], hoy=date(2026, 11, 11))

    assert con_ingreso_hoy.actual == 3
    assert con_ingreso_hoy.ultima_fecha == "2026-11-11"
    assert con_ingreso_hoy.hoy_ingresada is True


@pytest.mark.asyncio
async def test_racha_se_corta_si_el_ultimo_ingreso_fue_anteayer(test_db, seeded_user):
    user = await seeded_user()
    await _ingreso(test_db, user["id"], "2026-11-08")
    await _ingreso(test_db, user["id"], "2026-11-09")

    racha = await calcular_racha(user["id"], hoy=date(2026, 11, 11))

    assert racha.actual == 0
    assert racha.ultima_fecha == "2026-11-09"
    assert racha.hoy_ingresada is False


@pytest.mark.asyncio
async def test_contrato_de_campos_de_racha(client, seeded_user, make_token):
    user = await seeded_user()

    body = await _economia(client, make_token(user["id"]))

    assert {"racha", "racha_ultima_fecha", "racha_hoy_ingresada"} <= set(body)
    assert "racha_hoy_jugada" not in body
