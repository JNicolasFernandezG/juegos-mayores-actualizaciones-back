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
    assert body["meses"] == [
        {
            "mes": "2026-11",
            "juegos": {
                juego: {"S": 0, "A": 0, "B": 0, "C": 0, "F": 0}
                for juego in ("wordle", "sopa_letras", "sudoku", "crucigrama")
            },
        }
    ]
    assert body["actividad"] == []
    assert body["completadas_por_dia"] == {}


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
async def test_perfil_expone_meses_por_juego_ordenados(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    await _intento(test_db, uid, "2026-11-02", grade="S")
    await _intento(test_db, uid, "2026-11-03", game_id="sopa_letras", grade="B")
    await _intento(test_db, uid, "2026-10-10", grade="A")
    await _intento(test_db, uid, "2026-10-11", grade="A")
    await _intento(test_db, uid, "2026-09-01", game_id="sudoku", grade="C")

    meses = (await _resumen(client, make_token(uid)))["meses"]

    assert [mes["mes"] for mes in meses] == ["2026-11", "2026-10", "2026-09"]
    assert all(
        set(mes["juegos"]) == {"wordle", "sopa_letras", "sudoku", "crucigrama"}
        for mes in meses
    )
    assert all(
        set(conteos) == {"S", "A", "B", "C", "F"}
        for mes in meses
        for conteos in mes["juegos"].values()
    )

    noviembre, octubre, septiembre = meses
    assert noviembre["juegos"]["wordle"]["S"] == 1
    assert noviembre["juegos"]["sopa_letras"]["B"] == 1
    assert octubre["juegos"]["wordle"]["A"] == 2
    assert octubre["juegos"]["wordle"]["S"] == 0
    assert septiembre["juegos"]["sudoku"]["C"] == 1


@pytest.mark.asyncio
async def test_perfil_meses_corta_la_ventana_en_doce_meses(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    # HOY=2026-11-13: la ventana arranca en 2025-12-01.
    await _intento(test_db, uid, "2025-11-30", grade="S")
    await _intento(test_db, uid, "2025-12-01", grade="A")
    await _intento(test_db, uid, "2026-11-02", grade="S")

    body = await _resumen(client, make_token(uid))

    assert [mes["mes"] for mes in body["meses"]] == ["2026-11", "2025-12"]
    # El historial no tiene ventana: sigue contando el intento más viejo.
    assert body["medallas"]["historico"]["wordle"]["S"] == 2
    assert body["medallas"]["historico"]["wordle"]["A"] == 1


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


@pytest.mark.asyncio
async def test_perfil_cuenta_desafios_completados_por_dia(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    await _intento(test_db, uid, "2026-11-10", grade="S")
    await _intento(test_db, uid, "2026-11-10", game_id="sopa_letras", grade="A")
    await _intento(test_db, uid, "2026-11-10", game_id="narrativo", grade="B")
    # Un fallo cuenta como medalla del día, pero no como desafío completado.
    await _intento(
        test_db, uid, "2026-11-10", game_id="sudoku", status="failed", grade="F"
    )
    # Fuera de la ventana de 84 días no se publica.
    await _intento(test_db, uid, "2026-08-20", grade="S")

    body = await _resumen(client, make_token(uid))

    assert body["completadas_por_dia"] == {"2026-11-10": 3}


@pytest.mark.asyncio
async def test_perfil_atribuye_por_dia_de_juego_y_no_por_fecha_del_desafio(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    # Desafío del 19 de octubre resuelto el 3 de noviembre: la medalla es de noviembre.
    await _intento(
        test_db,
        uid,
        "2026-10-19",
        grade="S",
        completed_at=datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc),
    )
    # Desafío del 30 de septiembre resuelto a las 23:30 ART del 31 de octubre
    # (02:30 UTC del 1 de noviembre): sigue perteneciendo a octubre.
    await _intento(
        test_db,
        uid,
        "2026-09-30",
        grade="A",
        completed_at=datetime(2026, 11, 1, 2, 30, tzinfo=timezone.utc),
    )

    body = await _resumen(client, make_token(uid))

    mes = body["medallas"]["mes_actual"]
    assert (mes["wordle"]["S"], mes["wordle"]["A"]) == (1, 0)
    assert body["medallas"]["historico"]["wordle"]["A"] == 1

    meses = {fila["mes"]: fila["juegos"]["wordle"] for fila in body["meses"]}
    assert meses["2026-11"]["S"] == 1
    assert meses["2026-10"]["A"] == 1
    assert "2026-09" not in meses
    assert body["completadas_por_dia"] == {"2026-11-03": 1, "2026-10-31": 1}
    assert body["rendimiento"]["wordle"]["ultima_fecha"] == "2026-11-03"


@pytest.mark.asyncio
async def test_perfil_conserva_la_medalla_aunque_haya_guardados_posteriores(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    # Completada el 31 de octubre; después se jugó otra dificultad y falló el 2 de
    # noviembre, lo que mueve updated_at pero no el cierre de la partida.
    await _intento(
        test_db,
        uid,
        "2026-10-20",
        grade="B",
        completed_at=datetime(2026, 10, 31, 22, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc),
    )

    body = await _resumen(client, make_token(uid))

    meses = {fila["mes"]: fila["juegos"]["wordle"] for fila in body["meses"]}
    assert meses["2026-10"]["B"] == 1
    assert meses["2026-11"]["B"] == 0
    assert body["completadas_por_dia"] == {"2026-10-31": 1}


@pytest.mark.asyncio
async def test_perfil_usa_updated_at_en_documentos_sin_completed_at(
    client, test_db, seeded_user, make_token, perfil_hoy
):
    user = await seeded_user()
    uid = user["id"]

    await _intento(
        test_db,
        uid,
        "2026-10-01",
        grade="C",
        updated_at=datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc),
    )

    body = await _resumen(client, make_token(uid))

    meses = {fila["mes"]: fila["juegos"]["wordle"] for fila in body["meses"]}
    assert meses["2026-11"]["C"] == 1
    assert meses.get("2026-10", {}).get("C", 0) == 0
