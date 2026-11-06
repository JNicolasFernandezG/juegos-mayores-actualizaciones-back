import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import connect_to_mongo, get_database
from app.features.narrative.constants import COLL_CARDS, COLL_CHARACTERS

def test_narrative_v2_admin_crud(admin_override):
    asyncio.run(_ejecutar_tests_admin())

async def _ejecutar_tests_admin():
    await connect_to_mongo()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Listar eventos V2
        resp = await client.get("/api/narrative/admin/v2/eventos")
        assert resp.status_code == 200
        eventos = resp.json()
        assert isinstance(eventos, list)

        # 2. Crear evento V2
        test_evt_id = "evt_test_admin_suite_v2"
        payload_evt = {
            "_id": test_evt_id,
            "id": test_evt_id,
            "universo_id": "corte_medieval",
            "titulo": "Evento de Prueba Admin V2",
            "imagen": "/assets/narrative/eventos/default.webp",
            "requisitos_eventos_previos": ["evt_cometa_caido_v2"],
            "nodo_raiz": "inicio",
            "nodos": {
                "inicio": {
                    "id": "inicio",
                    "hablante_id": "narrador",
                    "texto": "Un emisario llega corriendo.",
                    "es_final": False,
                    "opciones": [
                        {"id": "opt_1", "texto": "Recibirlo", "siguiente_nodo": "fin_recibir"},
                        {"id": "opt_2", "texto": "Ignorarlo", "siguiente_nodo": "fin_ignorar"}
                    ],
                    "resultado_texto": "",
                    "impactos_recursos": [],
                    "impactos_afinidad": []
                },
                "fin_recibir": {
                    "id": "fin_recibir",
                    "hablante_id": "narrador",
                    "texto": "El emisario traía noticias valiosas.",
                    "es_final": True,
                    "opciones": [],
                    "resultado_texto": "Obtuviste información estratégica.",
                    "impactos_recursos": [{"recurso": "ejercito", "delta": 10}],
                    "impactos_afinidad": []
                },
                "fin_ignorar": {
                    "id": "fin_ignorar",
                    "hablante_id": "narrador",
                    "texto": "El emisario fue rechazado.",
                    "es_final": True,
                    "opciones": [],
                    "resultado_texto": "Ignoraste una advertencia importante.",
                    "impactos_recursos": [{"recurso": "pueblo", "delta": -10}],
                    "impactos_afinidad": []
                }
            }
        }

        resp_create = await client.post("/api/narrative/admin/v2/eventos", json=payload_evt)
        assert resp_create.status_code == 200
        created_data = resp_create.json()
        assert created_data["_id"] == test_evt_id
        assert len(created_data["nodos"]) == 3

        # 3. Obtener por ID
        resp_get = await client.get(f"/api/narrative/admin/v2/eventos/{test_evt_id}")
        assert resp_get.status_code == 200
        assert resp_get.json()["titulo"] == "Evento de Prueba Admin V2"

        # 4. Eliminar evento
        resp_del = await client.delete(f"/api/narrative/admin/v2/eventos/{test_evt_id}")
        assert resp_del.status_code == 200

        # Verificar 404
        resp_get_after = await client.get(f"/api/narrative/admin/v2/eventos/{test_evt_id}")
        assert resp_get_after.status_code == 404

        # 5. Crear conversación V2
        test_conv_id = "conv_test_admin_suite_v2"
        payload_conv = {
            "_id": test_conv_id,
            "id": test_conv_id,
            "universo_id": "corte_medieval",
            "titulo": "Conversación de Prueba Admin V2",
            "imagen": "/assets/narrative/conversation-hall.png",
            "requisitos": ["pj_canciller_elena"],
            "nodo_raiz": "inicio",
            "nodos": {
                "inicio": {
                    "id": "inicio",
                    "hablante_id": "pj_canciller_elena",
                    "texto": "Majestad, debemos revisar el censo.",
                    "es_final": False,
                    "opciones": [
                        {
                            "id": "opt_aprobar",
                            "texto": "Aprobar el censo",
                            "siguiente_nodo": "final_aprobado"
                        }
                    ]
                },
                "final_aprobado": {
                    "id": "final_aprobado",
                    "hablante_id": "pj_canciller_elena",
                    "texto": "El censo avanza.",
                    "es_final": True,
                    "opciones": [],
                    "resultado_texto": "Aprobaste el nuevo censo.",
                    "tipo_desenlace": "positivo",
                    "impactos_recursos": [{"recurso": "oro", "delta": 15}],
                    "impactos_afinidad": [{"personaje_id": "pj_canciller_elena", "delta": 10}]
                }
            }
        }

        resp_conv_create = await client.post("/api/narrative/admin/v2/conversaciones", json=payload_conv)
        assert resp_conv_create.status_code == 200

        # 6. Eliminar conversación
        resp_conv_del = await client.delete(f"/api/narrative/admin/v2/conversaciones/{test_conv_id}")
        assert resp_conv_del.status_code == 200


def test_barrera_efectos_al_guardar_carta_y_personaje(admin_override):
    asyncio.run(_ejecutar_barrera_efectos())


def _carta_payload(efectos) -> dict:
    return {
        "_id": "carta_test_barrera_efectos",
        "universo_id": "corte_medieval",
        "categoria": "item",
        "nombre": "Carta de prueba",
        "descripcion": "Descripción de prueba",
        "efectos": efectos,
    }


async def _ejecutar_barrera_efectos():
    await connect_to_mongo()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        db = get_database()
        await db[COLL_CARDS].delete_one({"_id": "carta_test_barrera_efectos"})
        await db[COLL_CHARACTERS].delete_one({"_id": "pj_test_barrera_efectos"})

        try:
            resp_ok = await client.post(
                "/api/narrative/admin/cartas",
                json=_carta_payload([
                    {
                        "id": "efecto_ok",
                        "disparador": "al_obtener",
                        "acciones": [
                            {"accion_id": "modificar_recurso", "parametros": {"clave": "oro", "valor": 5}}
                        ],
                    }
                ]),
            )
            assert resp_ok.status_code == 200, resp_ok.text

            resp_recurso = await client.post(
                "/api/narrative/admin/cartas",
                json=_carta_payload([
                    {
                        "id": "efecto_mal_recurso",
                        "disparador": "al_obtener",
                        "acciones": [
                            {"accion_id": "modificar_recurso", "parametros": {"clave": "uranio", "valor": 5}}
                        ],
                    }
                ]),
            )
            assert resp_recurso.status_code == 422, resp_recurso.text
            assert {h["codigo"] for h in resp_recurso.json()["detail"]["errores"]} == {"recurso_inexistente"}

            resp_evento = await client.post(
                "/api/narrative/admin/cartas",
                json=_carta_payload([
                    {
                        "id": "efecto_mal_evento",
                        "frecuencia_id": "frecuencia_inventada_xyz",
                        "acciones": [
                            {"accion_id": "modificar_recurso", "parametros": {"clave": "oro", "valor": 5}}
                        ],
                    }
                ]),
            )
            assert resp_evento.status_code == 422, resp_evento.text
            assert "evento_no_despachado" in {h["codigo"] for h in resp_evento.json()["detail"]["errores"]}

            resp_vacio = await client.post(
                "/api/narrative/admin/cartas",
                json=_carta_payload([{"id": "efecto_sin_acciones", "disparador": "al_obtener"}]),
            )
            assert resp_vacio.status_code == 422, resp_vacio.text
            assert "efecto_sin_acciones" in {h["codigo"] for h in resp_vacio.json()["detail"]["errores"]}

            guardada = await db[COLL_CARDS].find_one({"_id": "carta_test_barrera_efectos"})
            assert guardada is not None, "un rechazo no debe pisar la carta válida ya guardada"
            assert guardada["efectos"][0]["id"] == "efecto_ok"

            resp_pj = await client.post(
                "/api/narrative/admin/personajes",
                json={
                    "_id": "pj_test_barrera_efectos",
                    "universo_id": "corte_medieval",
                    "nombre": "Personaje de prueba",
                    "titulo": "Conde",
                    "descripcion": "Descripción",
                    "efectos": [
                        {
                            "id": "efecto_mal_primitiva",
                            "disparador": "al_desenlace",
                            "acciones": [
                                {"accion_id": "invocar_dragon", "parametros": {"clave": "oro", "valor": 5}}
                            ],
                        }
                    ],
                },
            )
            assert resp_pj.status_code == 422, resp_pj.text
            assert "accion_desconocida" in {h["codigo"] for h in resp_pj.json()["detail"]["errores"]}
            assert await db[COLL_CHARACTERS].find_one({"_id": "pj_test_barrera_efectos"}) is None
        finally:
            await db[COLL_CARDS].delete_one({"_id": "carta_test_barrera_efectos"})
            await db[COLL_CHARACTERS].delete_one({"_id": "pj_test_barrera_efectos"})


pytestmark = pytest.mark.integration
