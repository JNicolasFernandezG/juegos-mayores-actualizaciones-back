import pytest
import asyncio
import datetime
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import connect_to_mongo, close_mongo_connection, get_database
from app.core.security import crear_credencial_invitado, generar_guest_id
from app.scripts.seed_narrative import seed_narrative_game

FASES_AVANCE_NODO = {"TOMA_DECISION_EVENTO", "RESOLVER_CONVERSACION"}


def test_narrative_v2_full_cycle():
    """
    Test de integración extremo a extremo del flujo V2 de grafos:
    1. Verifica setup previo.
    2. Inicia partida V2 (/iniciar) con 3 miembros de corte y 3 cartas iniciales.
    3. Itera los 12 meses usando la API V2:
       - /elegir-carta-mes (devuelve grafo_actual)
       - /avanzar-nodo hasta BALANCE_MES (evento y conversación comparten el motor)
       - /avanzar-mes
    4. Verifica que al final del mes 12 la partida termina con finalización.
    """
    asyncio.run(_ejecutar_ciclo_v2())


async def _ejecutar_ciclo_v2():
    await connect_to_mongo()
    db = get_database()

    # Omitir seed si la base de datos ya contiene personajes para no sobreescribir imágenes del usuario
    if await db["narrative_characters"].count_documents({}) == 0:
        await seed_narrative_game()

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    challenge = await db["daily_challenges"].find_one({"game_id": "narrativo", "date": today_str})
    if not challenge:
        from app.features.narrative.admin.challenge_service import generar_mes_narrativo
        now = datetime.datetime.now()
        await generar_mes_narrativo(year=now.year, month=now.month, universo_id="corte_medieval")
        challenge = await db["daily_challenges"].find_one({"game_id": "narrativo", "date": today_str})

    transport = ASGITransport(app=app)
    guest_id = generar_guest_id()
    guest_headers = {"X-Guest-Credential": crear_credencial_invitado(guest_id)}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Limpiar run previa para test limpio
        await db["narrative_runs"].delete_one({"guest_id": guest_id, "date": today_str, "game_id": "narrativo"})
        cfg = challenge["config"]

        corte_elegida = cfg["setup_corte_ofrecidos_ids"][:3]
        cartas_elegidas = cfg["setup_cartas_ofrecidas_ids"][:3]

        # El ciclo completo vive en el motor de grafos V2. El seed de test tiene menos
        # eventos que meses del año, así que se habilita el reciclaje controlado del motor.
        await db["narrative_settings"].update_one(
            {"_id": "corte_medieval"},
            {"$set": {"motor": "v2", "reciclaje_eventos_v2": True}},
        )

        resp = await client.post(
            "/api/narrative/v2/partida/iniciar",
            json={
                "date": today_str,
                "corte_elegida_ids": corte_elegida,
                "cartas_iniciales_ids": cartas_elegidas,
            },
            headers=guest_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mes_actual"] == 1
        assert data["fase_actual"] == "DRAFT_MENSUAL"
        assert len(data["cartas_draft_actual"]) == 3

        finalizada = False
        for mes in range(1, 13):
            # Fase 1: elegir carta de draft y abrir el grafo del evento del mes
            carta_id = data["cartas_draft_actual"][0]["_id"]
            resp = await client.post(
                "/api/narrative/v2/partida/elegir-carta-mes",
                json={"date": today_str, "carta_id": carta_id},
                headers=guest_headers,
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if data["fase_actual"] == "FINALIZADA":
                finalizada = True
                break

            assert data["fase_actual"] == "TOMA_DECISION_EVENTO", data
            assert data["grafo_actual"] is not None

            # Fases 2 y 3: evento y conversación se recorren con el mismo endpoint.
            # Si el evento encadena un diálogo, el nodo activo pasa al grafo de conversación.
            estado = data["grafo_actual"]
            pasos = 0
            while estado["fase_actual"] in FASES_AVANCE_NODO:
                if estado.get("conversacion_actual"):
                    resp = await client.get(
                        "/api/narrative/v2/partida/grafo-actual",
                        params={"date": today_str},
                        headers=guest_headers,
                    )
                    assert resp.status_code == 200, resp.text
                    estado = resp.json()
                opciones = [
                    op for op in estado["nodo_actual"]["opciones"] if op.get("disponible", True)
                ]
                assert opciones, f"El nodo {estado['nodo_actual']['id']} no tiene opciones disponibles."
                pasos += 1
                assert pasos <= 60, "El grafo no converge a un nodo final."
                resp = await client.post(
                    "/api/narrative/v2/partida/avanzar-nodo",
                    json={"date": today_str, "opcion_id": opciones[0]["id"]},
                    headers=guest_headers,
                )
                assert resp.status_code == 200, resp.text
                estado = resp.json()
                if estado["fase_actual"] == "FINALIZADA" or estado.get("finalizacion"):
                    finalizada = True
                    break

            if finalizada:
                data = estado
                break

            # Fase 4: balance y avance de mes
            assert estado["fase_actual"] == "BALANCE_MES", estado
            resp = await client.post(
                "/api/narrative/v2/partida/avanzar-mes",
                json={"date": today_str},
                headers=guest_headers,
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if data["fase_actual"] == "FINALIZADA":
                finalizada = True
                # El reintento tras el cierre del año también debe ser idempotente.
                resp = await client.post(
                    "/api/narrative/v2/partida/avanzar-mes",
                    json={"date": today_str},
                    headers=guest_headers,
                )
                assert resp.status_code == 200, resp.text
                repetido = resp.json()
                assert repetido["fase_actual"] == "FINALIZADA"
                assert repetido["finalizacion"] is not None
                break
            assert data["mes_actual"] == mes + 1
            assert len(data["cartas_draft_actual"]) == 3

            # Un segundo POST del avance no debe romper: devuelve el mismo draft ya aplicado.
            resp = await client.post(
                "/api/narrative/v2/partida/avanzar-mes",
                json={"date": today_str},
                headers=guest_headers,
            )
            assert resp.status_code == 200, resp.text
            repetido = resp.json()
            assert repetido["fase_actual"] == "DRAFT_MENSUAL"
            assert repetido["mes_actual"] == data["mes_actual"]
            assert [c["_id"] for c in repetido["cartas_draft_actual"]] == [
                c["_id"] for c in data["cartas_draft_actual"]
            ]

        # El ciclo anual termina siempre con finalización (victoria o derrota)
        assert finalizada
        assert data["finalizacion"] is not None
        assert data["finalizacion"]["rango"] in ["S", "A", "B", "C", "F"]

    await close_mongo_connection()


pytestmark = pytest.mark.integration
