"""
test_narrative_v2_desenlaces_tags.py
Suite de tests de integración para las extensiones del motor V2:
1. Desenlaces ponderados: una opción puede sortear entre varios nodos destino por peso.
2. Impactos de tags: un nodo terminal otorga tags permanentes al reino (run.tags_activos).
3. Efectos ECA del desenlace: el nodo final despacha sus efectos y emite la señal que
   reactivos de cartas y corte esperan, gobernada por el catálogo del universo.
Verifica además el anti-spoiler: los desenlaces no se filtran al cliente.
"""

import pytest

import asyncio
from unittest.mock import patch

from app.core.database import connect_to_mongo, get_database
from app.features.narrative.constants import (
    COLL_V2_EVENTS,
    COLL_CARDS,
    COLL_RUNS
)
from app.features.narrative.game.motor_v2.graph_engine import graph_engine


def test_v2_desenlaces_y_tags():
    asyncio.run(_ejecutar_tests())


async def _ejecutar_tests():
    await connect_to_mongo()
    db = get_database()

    test_user_id = 777002
    date_str = "2026-12-28"
    # Limpiar runs residuales de ejecuciones previas
    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})

    # Grafo sintético: opción con desenlaces ponderados (fin_a peso 0, fin_b peso 100)
    grafo = {
        "_id": "evt_test_desenlaces_tags",
        "universo_id": "corte_medieval",
        "titulo": "Prueba de desenlaces y tags",
        "imagen": "",
        "nodo_raiz": "inicio",
        "nodos": {
            "inicio": {
                "id": "inicio",
                "hablante_id": "narrador",
                "texto": "Una decisión con dos desenlaces posibles.",
                "es_final": False,
                "opciones": [
                    {
                        "id": "opt_azar",
                        "texto": "Arriesgar",
                        "desenlaces": [
                            {"nodo": "fin_a", "peso": 0},
                            {"nodo": "fin_b", "peso": 100}
                        ]
                    }
                ]
            },
            "fin_a": {
                "id": "fin_a",
                "hablante_id": "narrador",
                "texto": "Desenlace A.",
                "es_final": True,
                "opciones": [],
                "resultado_texto": "Resultó A.",
                "impactos_recursos": [],
                "impactos_afinidad": []
            },
            "fin_b": {
                "id": "fin_b",
                "hablante_id": "narrador",
                "texto": "Desenlace B.",
                "es_final": True,
                "opciones": [],
                "resultado_texto": "Resultó B.",
                "impactos_recursos": [],
                "impactos_afinidad": [],
                "impactos_tags": ["favor_baron"]
            }
        }
    }
    await db[COLL_V2_EVENTS].replace_one({"_id": grafo["_id"]}, grafo, upsert=True)

    run = {
        "_id": f"run_desenlaces_tags_{test_user_id}",
        "user_id": test_user_id,
        "date": date_str,
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "fase_actual": "TOMA_DECISION_EVENTO",
        "status": "CONTINUA",
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
        "afinidad": {"pj_canciller_elena": 50},
        "eventos_jugados": [],
        "conversaciones_jugadas": [],
        "grafo_activo": None
    }
    await db[COLL_RUNS].replace_one({"_id": run["_id"]}, run, upsert=True)

    # ========================================================================
    # TEST 1: Anti-spoiler — el inicio no expone desenlaces ni destino
    # ========================================================================
    estado_inicio = await graph_engine.iniciar_grafo_en_partida(
        run=run, grafo=grafo, tipo="evento", fase="TOMA_DECISION_EVENTO"
    )
    assert estado_inicio.nodo_actual.id == "inicio"
    assert len(estado_inicio.nodo_actual.opciones) == 1
    opcion_cliente = estado_inicio.nodo_actual.opciones[0].model_dump()
    assert "desenlaces" not in opcion_cliente
    assert "siguiente_nodo" not in opcion_cliente
    print("[OK] Test 1: Los desenlaces ponderados no se filtran al cliente.")

    # ========================================================================
    # TEST 2: Sorteo determinista (fin_a peso 0) resuelve a fin_b
    # ========================================================================
    with patch("app.features.narrative.game.motor_v2.graph_engine.random.random", return_value=0.99):
        estado = await graph_engine.avanzar_nodo(run, "opt_azar")

    assert estado.nodo_actual.id == "fin_b", f"Se esperaba fin_b, se obtuvo {estado.nodo_actual.id}"
    assert estado.fase_actual == "BALANCE_MES"
    print("[OK] Test 2: El sorteo ponderado resuelve al desenlace de mayor peso.")

    # ========================================================================
    # TEST 3: El nodo final otorga tags permanentes al reino
    # ========================================================================
    assert estado.nodo_actual.impactos_tags == ["favor_baron"]
    assert run["tags_activos"] == ["favor_baron"]
    run_bd = await db[COLL_RUNS].find_one({"_id": run["_id"]})
    assert "favor_baron" in run_bd["tags_activos"]
    print("[OK] Test 3: El tag 'favor_baron' quedó registrado en run.tags_activos.")

    # Limpieza
    await db[COLL_V2_EVENTS].delete_one({"_id": "evt_test_desenlaces_tags"})
    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})
    print("\n[SUCCESS] ¡La suite de Desenlaces Ponderados y Tags V2 pasó exitosamente al 100%!")


def test_v2_efectos_del_desenlace():
    asyncio.run(_ejecutar_test_efectos_desenlace())


async def _ejecutar_test_efectos_desenlace():
    await connect_to_mongo()
    db = get_database()

    test_user_id = 777003
    date_str = "2026-12-29"
    grafo_id = "evt_test_efectos_desenlace"
    carta_id = "carta_test_reactiva"

    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})

    grafo = {
        "_id": grafo_id,
        "universo_id": "corte_medieval",
        "titulo": "Prueba de efectos del desenlace",
        "imagen": "",
        "nodo_raiz": "inicio",
        "nodos": {
            "inicio": {
                "id": "inicio",
                "hablante_id": "narrador",
                "texto": "Elegí el desenlace.",
                "es_final": False,
                "opciones": [
                    {"id": "opt_dano", "texto": "Sufrir", "siguiente_nodo": "fin_dano"},
                    {"id": "opt_mentira", "texto": "Mentir", "siguiente_nodo": "fin_mentira"},
                ]
            },
            "fin_dano": {
                "id": "fin_dano",
                "hablante_id": "narrador",
                "texto": "Pérdida real.",
                "es_final": True,
                "opciones": [],
                "resultado_texto": "Perdistes oro.",
                "impactos_recursos": [{"recurso": "oro", "delta": -10}],
                "impactos_afinidad": [],
                "efectos": [
                    {
                        "disparador": "al_desenlace",
                        "acciones": [
                            {"accion_id": "otorgar_tag", "parametros": {"tag": "sello_del_desenlace"}}
                        ]
                    },
                    {
                        "frecuencia_id": "no_catalgada",
                        "acciones": [
                            {"accion_id": "otorgar_tag", "parametros": {"tag": "fantasma"}}
                        ]
                    }
                ]
            },
            "fin_mentira": {
                "id": "fin_mentira",
                "hablante_id": "narrador",
                "texto": "Pérdida disfrazada de éxito.",
                "es_final": True,
                "opciones": [],
                "resultado_texto": "Mentiste y nadie lo nota.",
                "tipo_desenlace": "positivo",
                "impactos_recursos": [{"recurso": "oro", "delta": -10}],
                "impactos_afinidad": []
            }
        }
    }
    await db[COLL_V2_EVENTS].replace_one({"_id": grafo_id}, grafo, upsert=True)

    carta = {
        "_id": carta_id,
        "universo_id": "corte_medieval",
        "nombre": "Carta reactiva de prueba",
        "efectos": [
            {
                "disparador": "en_evento_negativo",
                "acciones": [{"accion_id": "otorgar_tag", "parametros": {"tag": "reactivo_negativo"}}]
            },
            {
                "disparador": "en_evento_positivo",
                "acciones": [{"accion_id": "otorgar_tag", "parametros": {"tag": "reactivo_positivo"}}]
            }
        ]
    }
    await db[COLL_CARDS].replace_one({"_id": carta_id}, carta, upsert=True)

    run = {
        "_id": f"run_efectos_desenlace_{test_user_id}",
        "user_id": test_user_id,
        "date": date_str,
        "game_id": "narrativo",
        "universo_id": "corte_medieval",
        "fase_actual": "TOMA_DECISION_EVENTO",
        "status": "CONTINUA",
        "mes_actual": 1,
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
        "afinidad": {},
        "tags_activos": [],
        "cartas_en_mano": [carta_id],
        "eventos_jugados": [],
        "conversaciones_jugadas": [],
        "grafo_activo": None
    }
    await db[COLL_RUNS].replace_one({"_id": run["_id"]}, run, upsert=True)

    # ========================================================================
    # TEST 1: El nodo final despacha sus efectos y la carta reacciona al negativo
    # ========================================================================
    await graph_engine.iniciar_grafo_en_partida(
        run=run, grafo=grafo, tipo="evento", fase="TOMA_DECISION_EVENTO"
    )
    with patch("app.features.narrative.game.motor_v2.graph_engine.random.random", return_value=0.99):
        estado_dano = await graph_engine.avanzar_nodo(run, "opt_dano")

    assert run["recursos"]["oro"] == 40, "El impacto del nodo debía restar 10 de oro"
    assert "sello_del_desenlace" in run["tags_activos"], "El efecto del desenlace no se despachó"
    assert "fantasma" not in run["tags_activos"], "Una frecuencia fuera del catálogo no puede disparar"
    assert "reactivo_negativo" in run["tags_activos"], "La carta no reaccionó al desenlace negativo"
    assert "reactivo_positivo" not in run["tags_activos"]
    print("[OK] Test 1: efectos del desenlace y reactivos despachados contra el catálogo.")

    # ========================================================================
    # TEST 2: El autor declara el signo y gana sobre la inferencia por deltas
    # ========================================================================
    run["tags_activos"] = []
    run["recursos"]["oro"] = 50
    await graph_engine.iniciar_grafo_en_partida(
        run=run, grafo=grafo, tipo="evento", fase="TOMA_DECISION_EVENTO"
    )
    with patch("app.features.narrative.game.motor_v2.graph_engine.random.random", return_value=0.99):
        await graph_engine.avanzar_nodo(run, "opt_mentira")

    assert run["recursos"]["oro"] == 40
    assert "reactivo_positivo" in run["tags_activos"], "tipo_desenlace='positivo' debía gobernar la señal"
    assert "reactivo_negativo" not in run["tags_activos"]
    print("[OK] Test 2: tipo_desenlace declarada por el autor prevalece sobre el balance de recursos.")

    # ========================================================================
    # TEST 3: Los efectos del nodo permanecen del lado del servidor
    # ========================================================================
    nodo_cliente_final = estado_dano.nodo_actual.model_dump()
    assert nodo_cliente_final["id"] == "fin_dano"
    assert "efectos" not in nodo_cliente_final, "el desenlace revelaría sus propios efectos"
    assert "tipo_desenlace" not in nodo_cliente_final
    print("[OK] Test 3: los efectos declarados en el nodo no se filtran al cliente.")

    # Limpieza
    await db[COLL_V2_EVENTS].delete_one({"_id": grafo_id})
    await db[COLL_CARDS].delete_one({"_id": carta_id})
    await db[COLL_RUNS].delete_many({"user_id": test_user_id, "game_id": "narrativo"})
    print("\n[SUCCESS] ¡La suite de Efectos del Desenlace V2 pasó exitosamente al 100%!")

pytestmark = pytest.mark.integration
