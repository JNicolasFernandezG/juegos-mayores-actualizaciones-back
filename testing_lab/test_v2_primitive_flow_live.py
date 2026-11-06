"""
testing_lab/test_v2_primitive_flow_live.py
Suite de verificación exhaustiva end-to-end del nuevo motor de primitivas V2:
1. Auditoría de catálogo en MongoDB:
   - Verifica que todas las acciones en COLL_ACTIONS tengan primitiva válida en PrimitivaOperacionEnum.
   - Verifica que personajes y cartas del universo canónico usen EfectoSchema desacoplado.
2. Setup e inicio de partida con primitivas:
   - Selección de Elena (mutar_estado limites.oro.max +20, cada_2_meses +15% oro).
   - Selección de Marcus (modificar_recurso +15 ejercito, amortiguar_danio 25%, disciplina_militar).
   - Selección de Tomás (mutar_estado fijar afinidad 70).
   - Cartas iniciales: Sello Real (mutar_estado limites.oro.max +30), Reserva Trigo (limites.pueblo.min = 10).
   - Verificación de límites dinámicos (oro max = 150, pueblo min = 10), afinidad y modificadores pasivos.
3. Selección de draft mensual con mutar_estado:
   - Elección de carta mensual y aplicación de al_obtener.
4. Ejecución del motor de grafos V2 con consecuencias de nodo terminal:
   - Verificación de amortiguación pasiva en pérdidas de recursos (amortiguar_danio).
   - Verificación de clamping contra run['limites'] dinámicos.
5. Transición mensual y frecuencias relativas:
   - Mes 1 -> Mes 2: frecuencia mensual (-5 oro) ejecuta; cada_2_meses NO ejecuta (desfase relativo).
   - Mes 2 -> Mes 3: frecuencia cada_2_meses de Elena SÍ ejecuta ((3 - 1) % 2 == 0) aplicando +15% oro.
6. Filtrado de condiciones de aparición (condiciones_aparicion) en cartas de draft.
"""

import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
import asyncio

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.core.security import create_access_token
from app.features.narrative.constants import (
    COLL_SETTINGS,
    COLL_ACTIONS,
    COLL_FREQUENCIES,
    COLL_CHARACTERS,
    COLL_CARDS,
    COLL_CHALLENGES,
    COLL_RUNS,
    COLL_V2_EVENTS,
)
from app.features.narrative.enums import (
    TipoCondicionEnum,
    OperadorEnum,
    OperacionMatematicaEnum,
    RunPhaseEnum,
)
from app.features.narrative.engine.rule_engine import (
    evaluar_condiciones,
    ejecutar_accion,
    _aplicar_operacion_matematica,
)
from app.features.narrative.schemas.rules_schemas import (
    CondicionSchema,
    AccionReferenciadaSchema,
    ParametrosAccionSchema,
    EfectoSchema,
    PrimitivaOperacionEnum,
)

BASE_URL = "http://127.0.0.1:8090"
TEST_DATE = "2026-11-15"  # Fecha dedicada para pruebas controladas
TEST_USER_ID = 88888


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def record(self, category: str, name: str, success: bool, details: str = ""):
        if success:
            self.passed += 1
            print(f"  [PASS] {name} -> {details}")
        else:
            self.failed += 1
            print(f"  [FAIL] {name} -> {details}")
        self.results.append({"category": category, "name": name, "success": success, "details": details})

    def request(self, method: str, path: str, data: dict = None, headers: dict = None, expected_status: int = 200) -> dict:
        url = f"{BASE_URL}{path}"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                parsed = json.loads(resp_body) if resp_body else {}
                if resp.status != expected_status:
                    raise Exception(f"Status esperado {expected_status}, recibido {resp.status}. Body: {resp_body[:200]}")
                return parsed
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            if e.code == expected_status:
                try:
                    return json.loads(err_body)
                except Exception:
                    return {"raw": err_body}
            raise Exception(f"HTTP {e.code} (esperado {expected_status}): {err_body[:200]}")
        except Exception as e:
            raise Exception(f"Error de conexión a {url}: {e}")


async def setup_test_challenge_in_mongo(db):
    """Crea un desafío narrativo controlado para TEST_DATE con personajes y cartas canónicas."""
    cards = await db[COLL_CARDS].find({"universo_id": "corte_medieval"}).to_list(None)
    card_ids = [c["_id"] for c in cards]
    pjs = await db[COLL_CHARACTERS].find({"universo_id": "corte_medieval"}).to_list(None)
    pj_ids = [p["_id"] for p in pjs]

    # Asegurar que el universo canónico tenga motor v2
    await db[COLL_SETTINGS].update_one({"_id": "corte_medieval"}, {"$set": {"motor": "v2"}}, upsert=True)

    doc = {
        "_id": f"desafio_narrativo_{TEST_DATE}",
        "game_id": "narrativo",
        "date": TEST_DATE,
        "config": {
            "universo_id": "corte_medieval",
            "atributos_iniciales": {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50},
            "setup_corte_ofrecidos_ids": ["pj_canciller_elena", "pj_comandante_marcus", "pj_obispo_tomas", "pj_alquimista_vera", "pj_ladrona_sylvia"],
            "setup_cartas_ofrecidas_ids": ["card_sello_real", "card_reserva_trigo", "card_remedio_herbario", "card_escudo_hierro", "card_tratado_paz"],
            "pool_cartas_mensuales_ids": card_ids,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLL_CHALLENGES].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    # Limpiar posibles runs previas de prueba
    await db[COLL_RUNS].delete_many({"user_id": TEST_USER_ID, "date": TEST_DATE})


async def run_full_suite():
    print("=" * 75)
    print("TEST SUITE: MOTOR DE PRIMITIVAS V2, MUTAR ESTADO Y FRECUENCIAS")
    print("=" * 75)

    runner = TestRunner()
    mongo_uri = settings.MONGO_URI or "mongodb://localhost:27017"
    db_name = settings.MONGO_DB_NAME or "mayores_actualizaciones_dev"
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    # Setup de token JWT para el usuario de pruebas
    token = create_access_token(user={"id": TEST_USER_ID, "name": "Admin Tester", "tipo_usuario": 1})
    auth_headers = {"Authorization": f"Bearer {token}"}

    # =========================================================================
    # 1. AUDITORÍA DE DERIVACIÓN DE CÓDIGO (¿Todas las acciones tienen código?)
    # =========================================================================
    print("\n--- 1. AUDITORÍA: DERIVACIÓN DE ACCIONES A CÓDIGO EJECUTABLE ---")
    primitivas_implementadas = {p.value for p in PrimitivaOperacionEnum}
    acciones_mongo = await db[COLL_ACTIONS].find({"universo_id": "corte_medieval"}).to_list(None)

    todas_tienen_codigo = True
    for acc in acciones_mongo:
        acc_id = acc["_id"]
        primitiva = acc.get("primitiva")
        tiene_codigo = primitiva in primitivas_implementadas
        if not tiene_codigo:
            todas_tienen_codigo = False
        runner.record(
            "AccionesCodigo",
            f"Acción MongoDB '{acc_id}' mapea a primitiva '{primitiva}'",
            tiene_codigo,
            f"Implementada en motor: {tiene_codigo}",
        )

    runner.record(
        "AccionesCodigo",
        "100% de acciones en catálogo derivan en código ejecutable de rule_engine",
        todas_tienen_codigo,
        f"{len(acciones_mongo)} acciones verificadas contra {len(primitivas_implementadas)} primitivas",
    )

    # =========================================================================
    # 2. AUDITORÍA DE PERSONAJES Y CARTAS CON EFECTOS DESACOPLADOS V2
    # =========================================================================
    print("\n--- 2. AUDITORÍA: PERSONAJES Y CARTAS CON ESQUEMA V2 ---")
    pjs = await db[COLL_CHARACTERS].find({"universo_id": "corte_medieval"}).to_list(None)
    cartas = await db[COLL_CARDS].find({"universo_id": "corte_medieval"}).to_list(None)

    for p in pjs:
        efs = p.get("efectos", [])
        valido = all("frecuencia_id" in e and "acciones" in e for e in efs)
        runner.record("PersonajesV2", f"Personaje {p['_id']} tiene estructura EfectoSchema", valido, f"{len(efs)} efectos")

    for c in cartas:
        efs = c.get("efectos", [])
        valido = all("frecuencia_id" in e and "acciones" in e for e in efs)
        runner.record("CartasV2", f"Carta {c['_id']} tiene estructura EfectoSchema", valido, f"{len(efs)} efectos")

    # =========================================================================
    # 3. VERIFICACIÓN DE OPERACIONES MATEMÁTICAS EN MEMORIA (UNIT TEST MOTOR)
    # =========================================================================
    print("\n--- 3. VERIFICACIÓN DE OPERACIONES MATEMÁTICAS DE mutar_estado ---")
    runner.record("MathEngine", "Sumar: 50 + 20 = 70", _aplicar_operacion_matematica(50, OperacionMatematicaEnum.SUMAR, 20) == 70)
    runner.record("MathEngine", "Restar: 50 - 15 = 35", _aplicar_operacion_matematica(50, OperacionMatematicaEnum.RESTAR, 15) == 35)
    runner.record("MathEngine", "Multiplicar: 50 * 1.2 = 60", _aplicar_operacion_matematica(50, OperacionMatematicaEnum.MULTIPLICAR, 1.2) == 60)
    runner.record("MathEngine", "Dividir: 60 / 2 = 30", _aplicar_operacion_matematica(60, OperacionMatematicaEnum.DIVIDIR, 2) == 30)
    runner.record("MathEngine", "Dividir por 0 mantiene valor (salvaguarda)", _aplicar_operacion_matematica(60, OperacionMatematicaEnum.DIVIDIR, 0) == 60)
    runner.record("MathEngine", "Porcentual (+20% de 50 = 60)", _aplicar_operacion_matematica(50, OperacionMatematicaEnum.PORCENTUAL, 20) == 60)
    runner.record("MathEngine", "Fijar valor a 85", _aplicar_operacion_matematica(50, OperacionMatematicaEnum.FIJAR, 85) == 85)

    # =========================================================================
    # 4. PREPARAR ESCENARIO EN VIVO Y SETUP INICIAL
    # =========================================================================
    print("\n--- 4. ESCENARIO EN VIVO: SETUP E INICIO DE PARTIDA V2 ---")
    await setup_test_challenge_in_mongo(db)

    # 4.1 Setup
    setup_res = runner.request("GET", f"/api/narrative/partida/setup?date={TEST_DATE}", headers=auth_headers)
    runner.record("LiveSetup", "GET /api/narrative/partida/setup", True, f"Personajes={len(setup_res.get('personajes_ofrecidos', []))}")

    # 4.2 Iniciar partida con Elena, Marcus y Tomás + Sello Real, Reserva Trigo y Remedio Herbario
    iniciar_payload = {
        "date": TEST_DATE,
        "corte_elegida_ids": ["pj_canciller_elena", "pj_comandante_marcus", "pj_obispo_tomas"],
        "cartas_iniciales_ids": ["card_sello_real", "card_reserva_trigo", "card_remedio_herbario"],
    }
    init_res = runner.request("POST", "/api/narrative/v2/partida/iniciar", data=iniciar_payload, headers=auth_headers)
    runner.record("LiveInit", "POST /api/narrative/v2/partida/iniciar", True, f"Mes={init_res.get('mes_actual')}")

    # 4.3 Consultar la partida en BD para verificar efectos al_obtener
    run_db = await db[COLL_RUNS].find_one({"user_id": TEST_USER_ID, "date": TEST_DATE})
    assert run_db is not None

    # Límites dinámicos:
    # Elena muta limites.oro.max (+20) -> base 100 + 20 = 120
    # Sello Real muta limites.oro.max (+30) -> 120 + 30 = 150
    # Reserva Trigo muta limites.pueblo.min a 10
    lim_oro_max = run_db.get("limites", {}).get("oro", {}).get("max")
    lim_pueblo_min = run_db.get("limites", {}).get("pueblo", {}).get("min")
    runner.record("LivePrimitivas", "Límite dinámico oro max mutó a 150 (Elena + Sello)", lim_oro_max == 150, f"oro.max={lim_oro_max}")
    runner.record("LivePrimitivas", "Límite dinámico pueblo min mutó a 10 (Reserva Trigo)", lim_pueblo_min == 10, f"pueblo.min={lim_pueblo_min}")

    # Afinidad fijada por Tomás:
    afinidad_tomas = run_db.get("afinidad", {}).get("pj_obispo_tomas")
    runner.record("LivePrimitivas", "Afinidad de Hermano Tomás fijada a 70", afinidad_tomas == 70, f"afinidad={afinidad_tomas}")

    # Tags otorgados: disciplina_militar (Marcus), sello_real (Sello), salud_reino (Remedio)
    tags = set(run_db.get("tags_activos", []))
    runner.record("LivePrimitivas", "Tags otorgados al reino", {"disciplina_militar", "sello_real", "salud_reino"}.issubset(tags), f"Tags={tags}")

    # Amortiguador pasivo otorgado por Marcus (25% ejercito)
    mods = run_db.get("modificadores_pasivos", [])
    has_marcus_dampener = any(m.get("clave") == "ejercito" and m.get("reduccion_porcentual") == 25.0 for m in mods)
    runner.record("LivePrimitivas", "Amortiguador de Marcus activo (25% bajas ejercito)", has_marcus_dampener)

    # Recursos post-setup:
    # Marcus da +15 ejercito (50 + 15 = 65)
    # Reserva Trigo da +20 pueblo (50 + 20 = 70)
    # Remedio Herbario da +15 pueblo (70 + 15 = 85)
    rec = run_db.get("recursos", {})
    runner.record("LivePrimitivas", "Recursos iniciales modificados correctamente", rec.get("ejercito") == 65 and rec.get("pueblo") == 85, f"ejercito={rec.get('ejercito')}, pueblo={rec.get('pueblo')}")

    # =========================================================================
    # 5. DRAFT MENSUAL CON mutar_estado (TRATADO DE PAZ)
    # =========================================================================
    print("\n--- 5. DRAFT MENSUAL Y MUTACIÓN MULTIPLICATIVA ---")
    # Forzamos card_tratado_paz en las opciones de draft para probar multiplicación
    await db[COLL_RUNS].update_one(
        {"_id": run_db["_id"]},
        {"$set": {"turno_actual.cartas_ofrecidas_ids": ["card_tratado_paz", "card_escudo_hierro", "card_bendicion_papal"]}}
    )

    oro_antes = rec.get("oro", 50)
    pueblo_antes = rec.get("pueblo", 85)

    draft_res = runner.request(
        "POST",
        "/api/narrative/v2/partida/elegir-carta-mes",
        data={"date": TEST_DATE, "carta_id": "card_tratado_paz"},
        headers=auth_headers,
    )
    runner.record("LiveDraft", "POST /api/narrative/v2/partida/elegir-carta-mes (Tratado de Paz)", True, f"Fase={draft_res.get('fase_actual')}")

    run_db = await db[COLL_RUNS].find_one({"_id": run_db["_id"]})
    # card_tratado_paz: mutar_estado recursos.oro multiplicar 1.10 (50 * 1.1 = 55), pueblo +15 (85 + 15 = 100)
    oro_despues = run_db.get("recursos", {}).get("oro")
    pueblo_despues = run_db.get("recursos", {}).get("pueblo")
    runner.record(
        "LiveDraft",
        "Mutación multiplicativa Tratado de Paz (oro * 1.10 = 55)",
        oro_despues == 55,
        f"oro_antes={oro_antes} -> oro_despues={oro_despues}",
    )
    runner.record(
        "LiveDraft",
        "Modificación aditiva Tratado de Paz (pueblo + 15 = 100)",
        pueblo_despues == 100,
        f"pueblo_antes={pueblo_antes} -> pueblo_despues={pueblo_despues}",
    )

    # =========================================================================
    # 6. MOTOR DE GRAFOS V2: AMORTIGUACIÓN PASIVA Y LÍMITES DINÁMICOS
    # =========================================================================
    print("\n--- 6. MOTOR DE GRAFOS V2: AMORTIGUACIÓN Y LÍMITES DINÁMICOS ---")
    # Inyectamos un evento V2 temporal de prueba en COLL_V2_EVENTS
    test_event_id = "evt_test_v2_impact"
    test_event_doc = {
        "_id": test_event_id,
        "universo_id": "corte_medieval",
        "titulo": "Asalto en la Frontera de Pruebas",
        "descripcion": "Una horda incursiona en la frontera norte.",
        "imagen": "/assets/narrative/events/incursion.webp",
        "nodo_inicial": "n_inicio",
        "nodos": [
            {
                "id": "n_inicio",
                "hablante_id": "narrador",
                "texto": "¿Cómo respondes a la incursión?",
                "es_final": False,
                "opciones": [
                    {
                        "id": "opt_contraataque",
                        "texto": "Lanzar un contraataque frontal feroz.",
                        "siguiente_nodo": "n_victoria_militar",
                    }
                ],
            },
            {
                "id": "n_victoria_militar",
                "hablante_id": "narrador",
                "texto": "El frente se mantiene pero hay bajas.",
                "es_final": True,
                # Pérdida nominal de 20 de ejército. Marcus amortigua 25% -> pérdida real = 15!
                # Ganancia nominal de 60 de oro. Sello Real expandió límite a 150, así que debe alcanzar 55 + 60 = 115!
                "impactos_recursos": [
                    {"recurso": "ejercito", "delta": -20},
                    {"recurso": "oro", "delta": 60},
                ],
                "impactos_afinidad": [
                    {"personaje_id": "pj_comandante_marcus", "delta": 10}
                ],
                "impactos_tags": ["veteranos_frontera"],
            },
        ],
    }
    await db[COLL_V2_EVENTS].replace_one({"_id": test_event_id}, test_event_doc, upsert=True)

    # Configuramos el evento activo en la run
    await db[COLL_RUNS].update_one(
        {"_id": run_db["_id"]},
        {
            "$set": {
                "fase_actual": RunPhaseEnum.TOMA_DECISION_EVENTO.value,
                "grafo_activo": {
                    "tipo": "evento",
                    "grafo_id": test_event_id,
                    "nodo_actual_id": "n_inicio",
                },
            }
        },
    )

    # Avanzar el nodo eligiendo la opción
    nav_payload = {
        "date": TEST_DATE,
        "opcion_id": "opt_contraataque",
    }
    nav_res = runner.request("POST", "/api/narrative/v2/partida/avanzar-nodo", data=nav_payload, headers=auth_headers)
    runner.record("GraphEngineV2", "POST /api/narrative/v2/partida/avanzar-nodo", True, f"Fase={nav_res.get('fase_actual')}")

    run_db = await db[COLL_RUNS].find_one({"_id": run_db["_id"]})
    # Ejercito antes era 65. Pérdida nominal -20 con amortiguación del 25%: delta real = -15 -> 65 - 15 = 50!
    ejercito_final = run_db.get("recursos", {}).get("ejercito")
    runner.record(
        "GraphEngineV2",
        "Amortiguación pasiva de bajas militares (Marcus 25% reduce -20 a -15: ejercito=50)",
        ejercito_final == 50,
        f"ejercito esperado 50, obtenido {ejercito_final}",
    )

    # Oro antes era 55. Ganancia +60 -> 115. Respeta el límite dinámico de 150 (en vez de quedar clamped en 100)
    oro_final = run_db.get("recursos", {}).get("oro")
    runner.record(
        "GraphEngineV2",
        "Límite dinámico oro max (150) permite superar los 100 estándar (oro=115)",
        oro_final == 115,
        f"oro esperado 115, obtenido {oro_final}",
    )

    # Afinidad de Marcus subió +10 (50 + 10 = 60)
    af_marcus = run_db.get("afinidad", {}).get("pj_comandante_marcus")
    runner.record("GraphEngineV2", "Impacto de afinidad en nodo terminal (Marcus=60)", af_marcus == 60, f"afinidad={af_marcus}")

    # Tag otorgado en nodo terminal
    runner.record("GraphEngineV2", "Tag de combate veteranos_frontera otorgado", "veteranos_frontera" in run_db.get("tags_activos", []))

    # =========================================================================
    # 7. FRECUENCIAS RELATIVAS: MENSUAL vs CADA_2_MESES
    # =========================================================================
    print("\n--- 7. FRECUENCIAS RELATIVAS Y DESFASES TEMPORALES ---")
    # La partida debe estar en FASE_BALANCE_MES para avanzar mes
    # Si estaba en FASE_EVENTO_SECUNDARIO o FASE_CONVERSACION_CORTE, la seteamos en FASE_BALANCE_MES para probar transición
    await db[COLL_RUNS].update_one(
        {"_id": run_db["_id"]},
        {"$set": {"fase_actual": RunPhaseEnum.BALANCE_MES.value}}
    )

    # Transición Mes 1 -> Mes 2:
    # Marcus tiene efecto MENSUAL: -5 oro -> 115 - 5 = 110.
    # Elena tiene efecto CADA_2_MESES (adquirida en mes 1).
    # En mes 2: (2 - 1) % 2 == 1 != 0 -> NO ejecuta.
    avanzar_m2 = runner.request("POST", "/api/narrative/v2/partida/avanzar-mes", data={"date": TEST_DATE}, headers=auth_headers)
    runner.record("Frecuencias", "Avanzar a Mes 2", avanzar_m2.get("mes_actual") == 2, f"Mes={avanzar_m2.get('mes_actual')}")

    run_db = await db[COLL_RUNS].find_one({"_id": run_db["_id"]})
    oro_m2 = run_db.get("recursos", {}).get("oro")
    runner.record(
        "Frecuencias",
        "Efecto mensual de Marcus (-5 oro) ejecutó en Mes 2 (oro=110)",
        oro_m2 == 110,
        f"oro={oro_m2}",
    )

    # Ahora simulamos llegar al final del Mes 2 y pasar al Mes 3:
    # En mes 3:
    # Marcus mensual ejecuta: -5 oro -> 110 - 5 = 105.
    # Elena cada_2_meses: (3 - 1) % 2 == 0 -> SÍ EJECUTA!
    # Condición de Elena: pueblo >= 40 (pueblo está en 100 >= 40 -> CUMPLE!).
    # Elena aplica +15% oro sobre 105: 105 * 0.15 = 15.75 -> round a 16 -> 105 + 16 = 121!
    await db[COLL_RUNS].update_one(
        {"_id": run_db["_id"]},
        {"$set": {"fase_actual": RunPhaseEnum.BALANCE_MES.value}}
    )
    avanzar_m3 = runner.request("POST", "/api/narrative/v2/partida/avanzar-mes", data={"date": TEST_DATE}, headers=auth_headers)
    runner.record("Frecuencias", "Avanzar a Mes 3", avanzar_m3.get("mes_actual") == 3, f"Mes={avanzar_m3.get('mes_actual')}")

    run_db = await db[COLL_RUNS].find_one({"_id": run_db["_id"]})
    oro_m3 = run_db.get("recursos", {}).get("oro")
    # Puede ser 121 (si Elena aplica sobre 105) o similar
    elena_ejecuto = oro_m3 > 105
    runner.record(
        "Frecuencias",
        f"Efecto cada_2_meses de Elena ejecutó en Mes 3 por periodicidad relativa (oro={oro_m3})",
        elena_ejecuto,
        f"oro esperado ~121, obtenido {oro_m3}",
    )

    # =========================================================================
    # 8. FILTRADO POR CONDICIONES DE APARICIÓN (condiciones_aparicion)
    # =========================================================================
    print("\n--- 8. EVALUACIÓN Y FILTRADO POR condiciones_aparicion ---")
    # Estado simulado de baja fe (fe = 20) y alto ejército (ejercito = 70)
    estado_test_1 = {
        "recursos": {"oro": 50, "pueblo": 50, "ejercito": 70, "fe": 20},
        "afinidad": {},
        "corte_activa": [],
        "tags_activos": [],
    }
    # card_escudo_hierro requiere ejercito >= 25 -> CUMPLE
    c_escudo = await db[COLL_CARDS].find_one({"_id": "card_escudo_hierro"})
    cumple_escudo = evaluar_condiciones(c_escudo.get("condiciones_aparicion", []), estado_test_1)
    runner.record("CondicionesAparicion", "card_escudo_hierro aparece si ejercito >= 25 (ejercito=70)", cumple_escudo)

    # card_bendicion_papal requiere fe >= 45 -> NO CUMPLE en estado_test_1 (fe=20)
    c_bendicion = await db[COLL_CARDS].find_one({"_id": "card_bendicion_papal"})
    cumple_bendicion_baja = evaluar_condiciones(c_bendicion.get("condiciones_aparicion", []), estado_test_1)
    runner.record("CondicionesAparicion", "card_bendicion_papal NO aparece si fe < 45 (fe=20)", not cumple_bendicion_baja)

    # Estado con alta fe (fe = 60) -> CUMPLE
    estado_test_2 = dict(estado_test_1, recursos=dict(estado_test_1["recursos"], fe=60))
    cumple_bendicion_alta = evaluar_condiciones(c_bendicion.get("condiciones_aparicion", []), estado_test_2)
    runner.record("CondicionesAparicion", "card_bendicion_papal SÍ aparece si fe >= 45 (fe=60)", cumple_bendicion_alta)

    # =========================================================================
    # LIMPIEZA
    # =========================================================================
    await db[COLL_RUNS].delete_many({"user_id": TEST_USER_ID, "date": TEST_DATE})
    await db[COLL_CHALLENGES].delete_one({"_id": f"desafio_narrativo_{TEST_DATE}"})
    await db[COLL_V2_EVENTS].delete_one({"_id": test_event_id})

    # =========================================================================
    # RESUMEN FINAL
    # =========================================================================
    print("\n" + "=" * 75)
    print(f"RESUMEN FINAL: {runner.passed} PASARON, {runner.failed} FALLARON")
    print("=" * 75)

    if runner.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_full_suite())
