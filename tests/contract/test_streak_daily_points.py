"""Puntos que se ganan por ingresar cada día de la racha."""

from datetime import timedelta

import pytest

from app.shared.clock import today_art
from app.shared.streak import registrar_ingreso_y_racha

pytestmark = [pytest.mark.contract, pytest.mark.puntos_diarios]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _saldo(test_db, user_id: int) -> int:
    user = await test_db["usuarios"].find_one({"id": user_id})
    return int(user.get("puntos", 0))


async def _presencia(test_db, user_id: int, dias_atras: int):
    await test_db["user_presence"].insert_one(
        {"user_id": user_id, "date": (today_art() - timedelta(days=dias_atras)).isoformat()}
    )


@pytest.mark.asyncio
async def test_primer_ingreso_suma_40_y_no_repite_el_mismo_dia(client, test_db, seeded_user, make_token):
    user = await seeded_user()
    token = make_token(user["id"])
    base = await _saldo(test_db, user["id"])

    primero = await client.get("/api/economy/me", headers=_auth(token))
    segundo = await client.get("/api/economy/me", headers=_auth(token))

    assert primero.json()["puntos"] == base + 40
    assert segundo.json()["puntos"] == base + 40
    assert primero.json()["racha_puntos_dia"] == 40
    assert {"dias": 25, "puntos": 160} in primero.json()["racha_tramos_diarios"]


@pytest.mark.asyncio
@pytest.mark.parametrize("dias_previos,esperado", [(13, 40), (14, 80), (18, 80), (19, 120), (23, 120), (24, 160), (40, 160)])
async def test_puntos_segun_el_dia_de_racha(test_db, seeded_user, dias_previos, esperado):
    user = await seeded_user()
    for atras in range(1, dias_previos + 1):
        await _presencia(test_db, user["id"], atras)
    base = await _saldo(test_db, user["id"])

    racha = await registrar_ingreso_y_racha(user["id"])

    assert racha.actual == dias_previos + 1
    assert await _saldo(test_db, user["id"]) == base + esperado


@pytest.mark.asyncio
async def test_un_dia_sin_ingresar_reinicia_en_el_dia_uno(test_db, seeded_user):
    user = await seeded_user()
    for atras in (2, 3, 4, 5, 6):  # falta ayer
        await _presencia(test_db, user["id"], atras)
    base = await _saldo(test_db, user["id"])

    racha = await registrar_ingreso_y_racha(user["id"])

    assert racha.actual == 1
    assert await _saldo(test_db, user["id"]) == base + 40
