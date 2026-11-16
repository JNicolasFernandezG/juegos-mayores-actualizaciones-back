"""Resumen de perfil: medallas del mes e históricas, rendimiento y actividad."""

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.contract

HOY = date(2026, 11, 13)


@pytest.fixture
def perfil_hoy(monkeypatch):
    monkeypatch.setattr(
        "app.features.profile.service.today_art", lambda: HOY
    )
    return HOY


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
        "grade": "S",
        "time_taken_seconds": 120,
        **extra,
    }
    await test_db["user_attempts"].insert_one(doc)


async def _presencia(test_db, user_id: int, fecha: str):
    ahora = datetime.now(timezone.utc)
    await test_db["user_presence"].insert_one(
        {
            "user_id": user_id,
            "date": fecha,
            "first_seen_at": ahora,
            "last_seen_at": ahora,
        }
    )


async def _resumen(client, token: str, query: str = "") -> dict:
    response = await client.get(f"/api/profile/summary{query}", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_perfil_exige_autenticacion(client, perfil_hoy):
    response = await client.get("/api/profile/summary")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_perfil_vacio_devuelve_ceros_y_ventana(client, seeded_user, make_token, perfil_hoy):
    user = await seeded_user()

    body = await _resumen(client, make_token(user["id"]))

    assert body["periodo"] == {
        "mes": "2026-11",
        "desde": "2026-08-22",
        "hasta": "2026-11-13",
    }
    assert set(body["medallas"]["mes_actual"]) == {
        "wordle",
        "sopa_letras",
        "sudoku",
        "crucigrama",
    }
    assert all(
        conteos == {"S": 0, "A": 0, "B": 0, "C": 0, "F": 0}
        for conteos in body["medallas"]["mes_actual"].values()
    )
    assert body["medallas"]["historico"] == body["medallas"]["mes_actual"]
    assert body["rendimiento"]["wordle"] == {
        "completadas": 0,
        "mejor_tiempo_segundos": None,
        "promedio_tiempo_segundos": None,
        "ultima_fecha": None,
    }
    assert body["actividad"] == []


@pytest.mark.asyncio
async def test_perfil_separa_mes_de_historico_y_cuenta_fallos(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    await _intento(test_db, uid, "2026-11-02", grade="S")
    await _intento(test_db, uid, "2026-11-10", grade="A")
    await _intento(test_db, uid, "2026-10-15", grade="S")
    await _intento(
        test_db, uid, "2026-11-05", game_id="crucigrama", status="failed", grade="F", score=0
    )
    await _intento(test_db, uid, "2026-11-06", game_id="sudoku", grade="B")
    # Un guardado intermedio y un juego fuera del catálogo no son medallas.
    await _intento(test_db, uid, "2026-11-07", status="in_progress", grade="C")
    await _intento(test_db, uid, "2026-11-08", game_id="desconocido", grade="S")

    body = await _resumen(client, make_token(uid))

    mes = body["medallas"]["mes_actual"]
    historico = body["medallas"]["historico"]
    assert (mes["wordle"]["S"], mes["wordle"]["A"]) == (1, 1)
    assert historico["wordle"]["S"] == 2
    assert historico["wordle"]["A"] == 1
    assert mes["crucigrama"]["F"] == 1
    assert historico["crucigrama"]["F"] == 1
    assert mes["sudoku"]["B"] == 1
    assert "desconocido" not in mes


@pytest.mark.asyncio
async def test_perfil_ignora_user_id_ajeno(client, test_db, seeded_user, make_token, perfil_hoy):
    yo = await seeded_user()
    otro = await seeded_user()
    await _intento(test_db, otro["id"], "2026-11-02", grade="S")

    body = await _resumen(
        client, make_token(yo["id"]), query=f"?user_id={otro['id']}"
    )

    assert body["medallas"]["historico"]["wordle"]["S"] == 0


@pytest.mark.asyncio
async def test_perfil_rendimiento_ignora_tiempos_de_fallos_y_nulos(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    await _intento(test_db, uid, "2026-11-02", time_taken_seconds=120)
    await _intento(test_db, uid, "2026-11-03", time_taken_seconds=240)
    await _intento(
        test_db, uid, "2026-11-04", status="failed", grade="F", time_taken_seconds=30
    )
    await _intento(test_db, uid, "2026-11-05", time_taken_seconds=None)

    rendimiento = (await _resumen(client, make_token(uid)))["rendimiento"]["wordle"]

    assert rendimiento == {
        "completadas": 3,
        "mejor_tiempo_segundos": 120,
        "promedio_tiempo_segundos": 180,
        "ultima_fecha": "2026-11-05",
    }


@pytest.mark.asyncio
async def test_perfil_actividad_se_limita_a_la_ventana(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    inicio_ventana = (HOY - timedelta(days=83)).isoformat()
    await _presencia(test_db, uid, "2026-08-21")
    await _presencia(test_db, uid, inicio_ventana)
    await _presencia(test_db, uid, "2026-11-13")
    await _presencia(test_db, uid, "2026-09-01")

    actividad = (await _resumen(client, make_token(uid)))["actividad"]

    assert actividad == [inicio_ventana, "2026-09-01", "2026-11-13"]
