"""
test_narrative_v2_encadenamiento_desenlace.py
Verifica la corrección del Bug Crítico 1:
Al alcanzar un nodo terminal (es_final=True) en un evento, el motor V2
devuelve SIEMPRE el desenlace del evento (nodo_actual con resultado_texto y deltas)
y, si se sortea una conversación incidental o evento especial, lo encadena en conversacion_actual
sin tragar ni descartar la consecuencia de la decisión del jugador.
"""

import pytest
import asyncio
from unittest.mock import patch

from app.core.database import connect_to_mongo, get_database
from app.features.narrative.constants import (
    COLL_V2_EVENTS,
    COLL_V2_CONVERSATIONS,
    COLL_RUNS,
)
from app.features.narrative.game.motor_v2.graph_engine import graph_engine

pytestmark = pytest.mark.integration

def test_v2_encadenamiento_preserva_desenlace_evento():
    asyncio.run(_ejecutar_test_encadenamiento())

async def _ejecutar_test_encadenamiento():
    await connect_to_mongo()
    db = get_database()

    test_user_id = 888101

    # Limpiar runs previas
    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})

    # 1. Crear evento sintético con nodo raíz y nodo final
    grafo_evento = {
        "_id": "evt_test_preservar_desenlace",
        "universo_id": "corte_medieval",
        "titulo": "El Juicio del Herrero",
        "imagen": "/assets/narrative/eventos/herrero.webp",
        "nodo_raiz": "raiz_juicio",
        "nodos": {
            "raiz_juicio": {
                "id": "raiz_juicio",
                "hablante_id": "narrador",
                "texto": "Un herrero es acusado de vender armas defectuosas.",
                "es_final": False,
                "opciones": [
                    {"id": "opt_absolver", "texto": "Absolver al herrero", "siguiente_nodo": "fin_absuelto"}
                ]
            },
            "fin_absuelto": {
                "id": "fin_absuelto",
                "hablante_id": "narrador",
                "texto": "El tribunal declara inocente al herrero.",
                "es_final": True,
                "resultado_texto": "El herrero jura gratitud a la corona (+10 Pueblo, +5 Oro).",
                "impactos_recursos": [
                    {"recurso": "pueblo", "delta": 10},
                    {"recurso": "oro", "delta": 5}
                ],
                "impactos_afinidad": [],
                "impactos_tags": []
            }
        }
    }
    await db[COLL_V2_EVENTS].replace_one({"_id": grafo_evento["_id"]}, grafo_evento, upsert=True)

    # 2. Crear conversación sintética de corte
    grafo_conv = {
        "_id": "conv_test_incidental_herrero",
        "universo_id": "corte_medieval",
        "titulo": "Rumor en las Forjas",
        "imagen": "/assets/narrative/conv/forjas.webp",
        "nodo_raiz": "raiz_conv",
        "nodos": {
            "raiz_conv": {
                "id": "raiz_conv",
                "hablante_id": "pj_comandante_marcus",
                "texto": "Majestad, el gremio de herreros celebra vuestra clemencia.",
                "es_final": False,
                "opciones": [
                    {"id": "opt_conv_agradecer", "texto": "Nos complace oírlo", "siguiente_nodo": "fin_conv"}
                ]
            },
            "fin_conv": {
                "id": "fin_conv",
                "hablante_id": "pj_comandante_marcus",
                "texto": "Marcus asiente y parte a supervisar la armería.",
                "es_final": True,
                "resultado_texto": "Las tropas reciben equipamiento reforzado.",
                "impactos_recursos": [{"recurso": "ejercito", "delta": 5}],
                "impactos_afinidad": [],
                "impactos_tags": []
            }
        }
    }
    await db[COLL_V2_CONVERSATIONS].replace_one({"_id": grafo_conv["_id"]}, grafo_conv, upsert=True)

    # Base de run activa en la raíz del evento
    run = {
        "_id": f"run_test_encadenar_{test_user_id}",
        "user_id": test_user_id,
        "date": "2026-11-06",
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "fase_actual": "TOMA_DECISION_EVENTO",
        "status": "CONTINUA",
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
        "afinidad": {"pj_comandante_marcus": 50},
        "eventos_jugados": [],
        "conversaciones_jugadas": [],
        "especiales_pendientes": [],
        "grafo_activo": {
            "tipo": "evento",
            "grafo_id": "evt_test_preservar_desenlace",
            "nodo_actual_id": "raiz_juicio"
        }
    }
    await db[COLL_RUNS].replace_one({"_id": run["_id"]}, run, upsert=True)

    # ========================================================================
    # PASO 1: Avanzar a nodo final con disparo de conversación incidental (40%)
    # ========================================================================
    with patch("app.features.narrative.game.motor_v2.graph_engine.random.random", return_value=0.10):
        with patch.object(graph_engine, "sortear_conversacion_v2", return_value=grafo_conv):
            estado_res = await graph_engine.avanzar_nodo(run, "opt_absolver")

    # ASERCIÓN CLAVE BUG CRÍTICO 1:
    # 1. El estado devuelto debe ser el desenlace del evento, NO la conversación directa
    assert estado_res.tipo == "evento", f"Se esperaba tipo 'evento', se obtuvo '{estado_res.tipo}'"
    assert estado_res.grafo_id == "evt_test_preservar_desenlace"
    assert estado_res.nodo_actual.es_final is True, "El nodo_actual debe ser el nodo terminal del evento."
    assert estado_res.nodo_actual.id == "fin_absuelto"
    assert "El herrero jura gratitud" in estado_res.nodo_actual.resultado_texto
    assert len(estado_res.nodo_actual.impactos_recursos) == 2

    # 2. La conversación incidental sorteada debe estar en 'conversacion_actual' lista para el front
    assert estado_res.conversacion_actual is not None, "Debe encadenar la conversación en 'conversacion_actual'."
    assert estado_res.conversacion_actual["_id"] == "conv_test_incidental_herrero"
    assert estado_res.conversacion_actual["nodo_id"] == "raiz_conv"
    assert len(estado_res.conversacion_actual["decisiones"]) == 1
    assert estado_res.conversacion_actual["decisiones"][0]["opcion"] == "opt_conv_agradecer"

    # 3. La run en memoria y BD debe tener el grafo_activo apuntando a la conversación encadenada
    assert run["grafo_activo"]["tipo"] == "conversacion"
    assert run["grafo_activo"]["grafo_id"] == "conv_test_incidental_herrero"
    assert run["grafo_activo"]["nodo_actual_id"] == "raiz_conv"
    assert run["fase_actual"] == "RESOLVER_CONVERSACION"

    run_bd = await db[COLL_RUNS].find_one({"_id": run["_id"]})
    assert run_bd["grafo_activo"]["grafo_id"] == "conv_test_incidental_herrero"
    assert run_bd["recursos"]["pueblo"] == 60  # 50 + 10 aplicado atómicamente
    assert run_bd["recursos"]["oro"] == 55      # 50 + 5 aplicado atómicamente

    print("[OK] Paso 1: Desenlace del evento preservado y conversación incidental encadenada correctamente.")

    # ========================================================================
    # PASO 2: Resolver la conversación encadenada a través de avanzar_nodo
    # ========================================================================
    estado_conv_res = await graph_engine.avanzar_nodo(run, "opt_conv_agradecer")

    # La conversación concluye
    assert estado_conv_res.tipo == "conversacion"
    assert estado_conv_res.grafo_id == "conv_test_incidental_herrero"
    assert estado_conv_res.nodo_actual.es_final is True
    assert estado_conv_res.nodo_actual.id == "fin_conv"
    assert estado_conv_res.conversacion_actual is None, "No debe haber más conversaciones encadenadas."

    # La partida pasa a BALANCE_MES y grafo_activo queda en None
    assert run["grafo_activo"] is None
    assert run["fase_actual"] == "BALANCE_MES"

    run_bd_final = await db[COLL_RUNS].find_one({"_id": run["_id"]})
    assert run_bd_final["grafo_activo"] is None
    assert run_bd_final["recursos"]["ejercito"] == 55  # 50 + 5 aplicado por la conversación

    print("[OK] Paso 2: La conversación encadenada se resuelve y transiciona limpiamente a BALANCE_MES.")

    # ========================================================================
    # PASO 3: Caso sin conversación incidental (random >= 0.40)
    # ========================================================================
    run_sin_conv = {
        "_id": f"run_test_sin_conv_{test_user_id}",
        "user_id": test_user_id,
        "date": "2026-11-05",
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "fase_actual": "TOMA_DECISION_EVENTO",
        "status": "CONTINUA",
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
        "afinidad": {"pj_comandante_marcus": 50},
        "eventos_jugados": [],
        "conversaciones_jugadas": [],
        "especiales_pendientes": [],
        "grafo_activo": {
            "tipo": "evento",
            "grafo_id": "evt_test_preservar_desenlace",
            "nodo_actual_id": "raiz_juicio"
        }
    }
    await db[COLL_RUNS].replace_one({"_id": run_sin_conv["_id"]}, run_sin_conv, upsert=True)

    with patch("app.features.narrative.game.motor_v2.graph_engine.random.random", return_value=0.99):
        estado_sin = await graph_engine.avanzar_nodo(run_sin_conv, "opt_absolver")

    assert estado_sin.tipo == "evento"
    assert estado_sin.nodo_actual.es_final is True
    assert estado_sin.conversacion_actual is None
    assert run_sin_conv["grafo_activo"] is None
    assert run_sin_conv["fase_actual"] == "BALANCE_MES"

    print("[OK] Paso 3: Sin conversación incidental pasa directamente a BALANCE_MES con desenlace intacto.")

    # Limpieza
    await db[COLL_V2_EVENTS].delete_one({"_id": grafo_evento["_id"]})
    await db[COLL_V2_CONVERSATIONS].delete_one({"_id": grafo_conv["_id"]})
    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})
    print("\n[SUCCESS] ¡Test de preservación de desenlace y encadenamiento V2 superado al 100%!")
