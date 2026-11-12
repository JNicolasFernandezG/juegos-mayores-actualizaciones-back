"""Bonus de puntos por racha aplicado al completar desafíos diarios."""

from datetime import datetime, timedelta, timezone

import pytest

from app.features.economy.config import DEFAULT_ECONOMY_CONFIG
from app.shared.clock import today_art

pytestmark = pytest.mark.contract


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fecha(dias_atras: int) -> str:
    return (today_art() - timedelta(days=dias_atras)).isoformat()


async def _configurar_bonus(test_db, cleanup, **overrides):
    bonus = {
        "activo": True,
        "modo": "porcentaje",
        "tramos": [
            {"dias": 10, "valor": 10},
            {"dias": 15, "valor": 20},
            {"dias": 20, "valor": 30},
        ],
    }
    bonus.update(overrides)
    doc = dict(DEFAULT_ECONOMY_CONFIG)
    doc["bonus_racha"] = bonus
    await test_db["configuracion_economia"].replace_one(
        {"_id": "global_economy"}, doc, upsert=True
    )
    cleanup.add("configuracion_economia", {"_id": "global_economy"})


async def _ingreso(test_db, user_id: int, fecha: str):
    ahora = datetime.now(timezone.utc)
    await test_db["user_presence"].insert_one(
        {
            "user_id": user_id,
            "date": fecha,
            "first_seen_at": ahora,
            "last_seen_at": ahora,
        }
    )


async def _presencia_previa(test_db, user_id: int, dias: int):
    """Deja presencia en los días anteriores a hoy (sin incluir hoy)."""
    for dias_atras in range(1, dias + 1):
        await _ingreso(test_db, user_id, _fecha(dias_atras))


async def _completar(client, token: str, game_id: str = "wordle", **extra):
    payload = {
        "game_id": game_id,
        "date": _fecha(0),
        "status": "completed",
        "word": "TEST",
        "attempts": 1,
        "grade": "S",
        **extra,
    }
    response = await client.post("/api/games/attempts", json=payload, headers=_auth(token))
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_racha_de_diez_dias_agrega_el_primer_tramo(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)

    body = await _completar(client, make_token(user["id"]))

    assert body["score"] == 100
    assert body["bonus_racha_puntos"] == 10
    assert body["bonus_racha_dias"] == 10
    assert body["puntos_ganados"] == 110
    assert body["puntos_totales_usuario"] == 110


@pytest.mark.asyncio
async def test_tramo_mas_alto_reemplaza_al_anterior(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 14)

    body = await _completar(client, make_token(user["id"]))

    assert body["bonus_racha_puntos"] == 20
    assert body["bonus_racha_dias"] == 15
    assert body["puntos_ganados"] == 120


@pytest.mark.asyncio
async def test_racha_corta_no_genera_bonus(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 8)

    body = await _completar(client, make_token(user["id"]))

    assert body["bonus_racha_puntos"] == 0
    assert body["bonus_racha_dias"] == 0
    assert body["puntos_ganados"] == 100


@pytest.mark.asyncio
async def test_racha_cortada_no_genera_bonus(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    for dias_atras in range(2, 13):
        await _ingreso(test_db, user["id"], _fecha(dias_atras))

    body = await _completar(client, make_token(user["id"]))

    assert body["bonus_racha_puntos"] == 0
    assert body["puntos_ganados"] == 100


@pytest.mark.asyncio
async def test_bonus_inactivo_no_suma(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup, activo=False)
    await _presencia_previa(test_db, user["id"], 20)

    body = await _completar(client, make_token(user["id"]))

    assert body["bonus_racha_puntos"] == 0
    assert body["puntos_ganados"] == 100


@pytest.mark.asyncio
async def test_dos_juegos_el_mismo_dia_reciben_bonus(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)
    token = make_token(user["id"])

    wordle = await _completar(client, token, game_id="wordle")
    sudoku = await _completar(client, token, game_id="sudoku")

    assert wordle["puntos_ganados"] == 110
    assert sudoku["puntos_ganados"] == 110
    assert sudoku["puntos_totales_usuario"] == 220


@pytest.mark.asyncio
async def test_replay_no_vuelve_a_acreditar(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)
    token = make_token(user["id"])

    primero = await _completar(client, token)
    replay = await _completar(client, token)

    assert primero["puntos_ganados"] == 110
    assert replay["puntos_ganados"] == 0
    assert replay["puntos_totales_usuario"] == 110
    assert replay["bonus_racha_puntos"] == 10


@pytest.mark.asyncio
async def test_intento_fallido_no_cobra_ni_bonifica(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)

    body = await _completar(client, make_token(user["id"]), status="failed", grade=None)

    assert body["status"] == "failed"
    assert body["bonus_racha_puntos"] == 0
    assert body["puntos_ganados"] == 0


@pytest.mark.asyncio
async def test_narrativo_no_recibe_bonus(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)

    body = await _completar(client, make_token(user["id"]), game_id="narrativo")

    assert body["bonus_racha_puntos"] == 0
    assert body["bonus_racha_dias"] == 0
    assert body["puntos_ganados"] == 100


@pytest.mark.asyncio
async def test_ledger_registra_el_desglose_del_bonus(
    client, test_db, seeded_user, make_token, cleanup
):
    user = await seeded_user(puntos=0)
    await _configurar_bonus(test_db, cleanup)
    await _presencia_previa(test_db, user["id"], 9)

    await _completar(client, make_token(user["id"]))

    entry = await test_db["economy_ledger"].find_one(
        {"user_id": user["id"], "motivo": "attempt", "status": "applied"}
    )
    assert entry["puntos"] == 110
    assert entry["metadata"]["score_base"] == 100
    assert entry["metadata"]["bonus_racha"] == 10
    assert entry["metadata"]["racha_dias"] == 10
