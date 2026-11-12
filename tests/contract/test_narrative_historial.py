"""Enriquecimiento del historial de partida para evitar consultas a /api/narrative/admin/*."""

import pytest

from app.features.narrative.constants import (
    COLL_CARDS,
    COLL_CONVERSATIONS,
    COLL_EVENTS,
    COLL_RESULTS,
    COLL_RUNS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTS,
)

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_historial_enriquece_cronica_v2_para_alumno_sin_exponer_admin(
    client, test_db, seeded_user, make_token, cleanup
):
    alumno = await seeded_user(tipo_usuario=1, name="Alumno Cronica")
    token = make_token(alumno["id"], tipo_usuario=1)
    headers = {"Authorization": f"Bearer {token}"}
    fecha = "2099-05-10"
    run_id = f"{alumno['id']}_{fecha}"

    cleanup.add(COLL_CARDS, {"_id": "carta_cronica_test"})
    cleanup.add(COLL_CARDS, {"_id": "carta_no_jugada_test"})
    cleanup.add(COLL_V2_EVENTS, {"_id": "evt_v2_cronica_test"})
    cleanup.add(COLL_V2_CONVERSATIONS, {"_id": "conv_v2_cronica_test"})
    cleanup.add(COLL_RUNS, {"_id": run_id})

    await test_db[COLL_CARDS].insert_many([
        {
            "_id": "carta_cronica_test",
            "universo_id": "corte_medieval",
            "categoria": "accion",
            "nombre": "Sello del Tesoro",
            "descripcion": "Refuerza las arcas reales.",
        },
        {
            "_id": "carta_no_jugada_test",
            "universo_id": "corte_medieval",
            "categoria": "accion",
            "nombre": "Carta Secreta",
            "descripcion": "No deberia filtrarse al historial.",
        },
    ])
    await test_db[COLL_V2_EVENTS].insert_one({
        "_id": "evt_v2_cronica_test",
        "universo_id": "corte_medieval",
        "titulo": "Sequía en los campos",
        "imagen": "/assets/narrative/eventos/default.webp",
        "nodo_raiz": "inicio",
        "nodos": {
            "inicio": {
                "id": "inicio",
                "hablante_id": "narrador",
                "texto": "Los graneros están vacíos.",
                "es_final": False,
                "opciones": [
                    {"id": "opt_abrir_silos", "texto": "Abrir los silos reales", "siguiente_nodo": "fin_silos"},
                    {"id": "opt_oculta", "texto": "Opción secreta no elegida", "siguiente_nodo": "fin_oculta"},
                ],
            },
            "fin_silos": {
                "id": "fin_silos",
                "hablante_id": "narrador",
                "texto": "El pueblo agradece.",
                "es_final": True,
                "resultado_texto": "El grano alcanzó hasta la cosecha.",
                "impactos_afinidad": [{"personaje_id": "pj_elena", "delta": 10}],
            },
        },
    })
    await test_db[COLL_V2_CONVERSATIONS].insert_one({
        "_id": "conv_v2_cronica_test",
        "universo_id": "corte_medieval",
        "titulo": "Audiencia en palacio",
        "imagen": "/assets/narrative/conversaciones/default.webp",
        "nodo_raiz": "inicio",
        "nodos": {
            "inicio": {
                "id": "inicio",
                "hablante_id": "pj_marcus",
                "texto": "¿Qué opinás?",
                "es_final": False,
                "opciones": [
                    {"id": "conv_opt_apoyar", "texto": "Respaldar la guardia", "siguiente_nodo": "conv_fin"},
                ],
            },
            "conv_fin": {
                "id": "conv_fin",
                "hablante_id": "pj_marcus",
                "texto": "Cierre.",
                "es_final": True,
                "resultado_texto": "Marcus asiente satisfecho.",
                "impactos_afinidad": [{"personaje_id": "pj_marcus", "delta": 5}],
            },
        },
    })
    await test_db[COLL_RUNS].insert_one({
        "_id": run_id,
        "user_id": alumno["id"],
        "date": fecha,
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "mes_actual": 2,
        "fase_actual": "DRAFT_MENSUAL",
        "status": "in_progress",
        "recursos": {"oro": 45, "pueblo": 60, "ejercito": 50, "fe": 50},
        "afinidad": {"pj_elena": 60, "pj_marcus": 55},
        "cartas_en_mano": ["carta_cronica_test"],
        "tags_activos": [],
        "turno_actual": {},
        "historial_mensual": [
            {
                "mes": 1,
                "carta_elegida_id": "carta_cronica_test",
                "evento_id": "evt_v2_cronica_test",
                "opcion_elegida_id": "opt_abrir_silos",
                "resultado_id": "fin_silos",
                "conversacion_id": "conv_v2_cronica_test",
                "decision_conversacion_opcion": None,
                "decisiones_v2": [
                    {
                        "mes": 1,
                        "tipo": "evento",
                        "grafo_id": "evt_v2_cronica_test",
                        "opcion_elegida_id": "opt_abrir_silos",
                        "resultado_obtenido_id": "fin_silos",
                    },
                    {
                        "mes": 1,
                        "tipo": "conversacion",
                        "grafo_id": "conv_v2_cronica_test",
                        "opcion_elegida_id": "conv_opt_apoyar",
                        "resultado_obtenido_id": "conv_fin",
                    },
                ],
                "recursos_fin_mes": {"oro": 45, "pueblo": 60, "ejercito": 50, "fe": 50},
            }
        ],
    })

    # El alumno sigue sin poder consultar /api/narrative/admin/*
    admin_res = await client.get("/api/narrative/admin/cartas", headers=headers)
    assert admin_res.status_code == 403

    # Pero GET /api/narrative/partida/historial entrega toda su crónica lista para leer
    hist_res = await client.get(f"/api/narrative/partida/historial?date={fecha}", headers=headers)
    assert hist_res.status_code == 200
    body = hist_res.json()
    assert len(body["historial_mensual"]) == 1
    mes = body["historial_mensual"][0]
    assert mes["carta_nombre"] == "Sello del Tesoro"
    assert mes["evento_titulo"] == "Sequía en los campos"
    assert mes["opcion_texto"] == "Abrir los silos reales"
    assert mes["resultado_texto"] == "El grano alcanzó hasta la cosecha."
    assert mes["conversacion_titulo"] == "Audiencia en palacio"
    assert mes["decision_texto"] == "Respaldar la guardia"
    assert mes["decision_resultado_texto"] == "Marcus asiente satisfecho."
    assert mes["impacto_afinidad"] == [
        {"personaje_id": "pj_elena", "delta": 10},
        {"personaje_id": "pj_marcus", "delta": 5},
    ]


@pytest.mark.asyncio
async def test_historial_mantiene_compatibilidad_con_registros_v1(
    client, test_db, seeded_user, make_token, cleanup
):
    alumno = await seeded_user(tipo_usuario=1, name="Alumno V1")
    token = make_token(alumno["id"], tipo_usuario=1)
    fecha = "2099-05-11"
    run_id = f"{alumno['id']}_{fecha}"

    cleanup.add(COLL_EVENTS, {"_id": "evt_v1_test"})
    cleanup.add(COLL_RESULTS, {"_id": "res_v1_test"})
    cleanup.add(COLL_CONVERSATIONS, {"_id": "conv_v1_test"})
    cleanup.add(COLL_RUNS, {"_id": run_id})

    await test_db[COLL_EVENTS].insert_one({
        "_id": "evt_v1_test",
        "titulo": "Torneo de primavera",
        "opciones": [{"id": "opt_v1", "texto": "Patrocinar justas"}],
    })
    await test_db[COLL_RESULTS].insert_one({
        "_id": "res_v1_test",
        "titulo": "Ovación popular",
        "texto": "La plaza celebra.",
        "impacto_afinidad": [{"personaje_id": "pj_elena", "delta": 8}],
    })
    await test_db[COLL_CONVERSATIONS].insert_one({
        "_id": "conv_v1_test",
        "titulo": "Charla nocturna",
        "decisiones": [
            {
                "opcion": 1,
                "texto": "Brindar",
                "resultado_texto": "Ambiente distendido.",
                "impacto_afinidad": [{"personaje_id": "pj_marcus", "delta": 4}],
            }
        ],
    })
    await test_db[COLL_RUNS].insert_one({
        "_id": run_id,
        "user_id": alumno["id"],
        "date": fecha,
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "mes_actual": 2,
        "fase_actual": "DRAFT_MENSUAL",
        "status": "in_progress",
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
        "afinidad": {},
        "cartas_en_mano": [],
        "tags_activos": [],
        "turno_actual": {},
        "historial_mensual": [
            {
                "mes": 1,
                "evento_id": "evt_v1_test",
                "opcion_elegida_id": "opt_v1",
                "resultado_id": "res_v1_test",
                "conversacion_id": "conv_v1_test",
                "decision_conversacion_opcion": 1,
                "recursos_fin_mes": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
            }
        ],
    })

    hist_res = await client.get(
        f"/api/narrative/partida/historial?date={fecha}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hist_res.status_code == 200
    mes = hist_res.json()["historial_mensual"][0]
    assert mes["evento_titulo"] == "Torneo de primavera"
    assert mes["opcion_texto"] == "Patrocinar justas"
    assert mes["resultado"] == "Ovación popular"
    assert mes["resultado_texto"] == "La plaza celebra."
    assert mes["conversacion_titulo"] == "Charla nocturna"
    assert mes["decision_texto"] == "Brindar"
    assert mes["decision_resultado_texto"] == "Ambiente distendido."
    assert mes["impacto_afinidad"] == [
        {"personaje_id": "pj_elena", "delta": 8},
        {"personaje_id": "pj_marcus", "delta": 4},
    ]
