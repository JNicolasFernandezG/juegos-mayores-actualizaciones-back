#!/usr/bin/env python
"""
Auditoria en vivo del motor narrativo V2.

Lee la configuracion real de cartas, personajes, frecuencias, acciones y nodos
terminales desde la DB de desarrollo (solo lectura) y juega partidas de invitado
contra la API real. En cada transicion compara el estado observable contra un
evaluador de referencia independiente:

- setup: efectos al_obtener de personajes y cartas iniciales
- draft: efecto al_obtener de la carta elegida
- desenlace: impactos declarados por el nodo terminal
- avanzar-mes: pasivos cada_mes / periodicidades relativas y condiciones

Tambien verifica el estado interno del run (tags, limites, variables,
modificadores, adquisiciones, cartas en mano) leyendo narrative_runs por guest.
"""

import copy
import json
import sys
import time
import urllib.error
import urllib.request

import pymongo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8090"
DATE = "2026-11-06"
DBNAME = "mayores_actualizaciones_dev"
UNIVERSO_ID = "corte_medieval"

client = pymongo.MongoClient("mongodb://localhost:27017")
db = client[DBNAME]

SETTINGS = db.narrative_settings.find_one({"_id": UNIVERSO_ID})
BASE_RECURSOS = {r["clave"]: r for r in SETTINGS["recursos"]}
FREQS = {i["id"]: i for i in (db.narrative_frequencies.find_one({"universo_id": UNIVERSO_ID}) or {}).get("items", [])}
ACTIONS = {a["_id"]: a for a in db.narrative_actions.find({"universo_id": UNIVERSO_ID})}
CARDS = {c["_id"]: c for c in db.narrative_cards.find()}
CHARS = {c["_id"]: c for c in db.narrative_characters.find()}
GRAPHS = {}
for tipo, coll in (
    ("evento", "narrative_v2_events"),
    ("conversacion", "narrative_v2_conversations"),
    ("evento_especial", "narrative_v2_eventos_especiales"),
):
    for g in db[coll].find():
        GRAPHS[(tipo, g["_id"])] = g

ALIAS = {"al_obtener": "al_obtener", "cada_mes": "inicio_mes", "mensual": "inicio_mes", "inicio_mes": "inicio_mes"}

PASS = 0
FAIL = 0
CHECKS = []


def norm(value):
    return ALIAS.get(str(value), str(value))


def db_order(coll, ids):
    """Orden real que devuelve Mongo para el mismo $in que usa el motor."""
    ids = list(ids)
    if not ids:
        return []
    return [str(d["_id"]) for d in db[coll].find({"_id": {"$in": ids}})]


def check(ok, label, esperado=None, observado=None):
    global PASS, FAIL
    if ok:
        PASS += 1
        CHECKS.append(("PASS", label))
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        CHECKS.append(("FAIL", label, esperado, observado))
        print(f"  FAIL  {label}")
        if esperado is not None or observado is not None:
            print(f"        esperado:  {json.dumps(esperado, ensure_ascii=False, sort_keys=True)}")
            print(f"        observado: {json.dumps(observado, ensure_ascii=False, sort_keys=True)}")


# =============================================================================
# Evaluador de referencia (semantica de rule_engine, reimplementada aparte)
# =============================================================================

class Ref:
    def __init__(self, recursos, afinidad, tags, limites, variables, mods, cartas, adq, mes):
        self.recursos = dict(recursos)
        self.afinidad = dict(afinidad)
        self.tags = list(tags)
        self.limites = copy.deepcopy(limites)
        self.variables = dict(variables)
        self.mods = copy.deepcopy(mods)
        self.cartas = list(cartas)
        self.adq = copy.deepcopy(adq)
        self.mes = mes

    @staticmethod
    def from_run(run):
        return Ref(
            recursos=run.get("recursos", {}),
            afinidad=run.get("afinidad", {}),
            tags=run.get("tags_activos", []),
            limites=run.get("limites", {}),
            variables=run.get("variables", {}),
            mods=run.get("modificadores_pasivos", []),
            cartas=run.get("cartas_en_mano", []),
            adq=run.get("adquisiciones", {}),
            mes=run.get("mes_actual", 1),
        )

    def snapshot(self):
        return {
            "recursos": dict(sorted(self.recursos.items())),
            "afinidad": dict(sorted(self.afinidad.items())),
            "tags": sorted(self.tags),
            "limites": copy.deepcopy(self.limites),
            "variables": dict(sorted(self.variables.items())),
            "mods": sorted(
                (m.get("tipo"), m.get("clave"), m.get("reduccion_porcentual"), m.get("fuente"))
                for m in self.mods
            ),
            "cartas": sorted(self.cartas),
            "adq": {k: v.get("mes") for k, v in sorted(self.adq.items())},
        }


def comparar(actual, op, objetivo):
    if op == ">=":
        return actual >= objetivo
    if op == "<=":
        return actual <= objetivo
    if op == ">":
        return actual > objetivo
    if op == "<":
        return actual < objetivo
    if op == "==":
        return actual == objetivo
    if op == "!=":
        return actual != objetivo
    return False


def evaluar_condicion(c, s):
    tipo = c.get("tipo")
    if tipo == "comparar_recurso":
        return comparar(float(s.recursos.get(c.get("clave"), 0)), c.get("operador"), float(c.get("valor") or 0))
    if tipo == "tiene_personaje":
        return c.get("personaje_id") in (list(s.afinidad.keys()) or [])
    if tipo == "afinidad_personaje":
        return comparar(float(s.afinidad.get(c.get("personaje_id"), 50)), c.get("operador"), float(c.get("valor") or 0))
    if tipo == "tiene_tag":
        return c.get("tag") in s.tags
    if tipo == "tiene_carta":
        return c.get("carta_id") in s.cartas
    return False


def evaluar_condiciones(condiciones, s):
    return all(evaluar_condicion(c, s) for c in condiciones) if condiciones else True


def limites_de(s, clave):
    lim = (s.limites or {}).get(clave)
    base = BASE_RECURSOS.get(clave, {})
    if isinstance(lim, dict) and ("min" in lim or "max" in lim):
        return (float(lim.get("min", base.get("min", 0))), float(lim.get("max", base.get("max", 100))))
    if base:
        return (float(base.get("min", 0)), float(base.get("max", 100)))
    return None


def aplicar_delta(s, clave, delta):
    if clave not in s.recursos:
        return None
    actual = float(s.recursos[clave])
    efectivo = float(delta)
    if efectivo < 0:
        for mod in s.mods:
            if mod.get("tipo") == "amortiguar_danio" and (not mod.get("clave") or mod.get("clave") == clave):
                red = float(mod.get("reduccion_porcentual", 0))
                if 0 < red <= 100:
                    efectivo *= 1.0 - red / 100.0
    nuevo = actual + efectivo
    lim = limites_de(s, clave)
    if lim is not None:
        nuevo = max(lim[0], min(lim[1], nuevo))
    s.recursos[clave] = int(round(nuevo))
    return s.recursos[clave]


def operar(actual, op, valor):
    op = str(op or "sumar").lower()
    if op == "sumar":
        return actual + valor
    if op == "restar":
        return actual - valor
    if op == "multiplicar":
        return actual * valor
    if op == "dividir":
        return actual if valor == 0 else actual / valor
    if op == "porcentual":
        return actual + actual * (valor / 100.0)
    if op == "fijar":
        return valor
    return actual + valor


def agregar_tag(s, tag):
    if tag and tag not in s.tags:
        s.tags.append(tag)


def ejecutar_accion(s, accion_id, params, owner):
    prim = (ACTIONS.get(accion_id) or {}).get("primitiva", accion_id)

    if prim == "modificar_recurso":
        clave = params.get("clave")
        if not clave:
            return
        actual = float(s.recursos.get(clave, 0))
        valor = float(params.get("valor") or 0)
        delta = actual * (valor / 100.0) if params.get("tipo_calculo") in ("porcentual", "PORCENTUAL") else valor
        aplicar_delta(s, clave, delta)
        return

    if prim == "modificar_afinidad":
        target = None
        if params.get("destino", "personaje") == "portador":
            if owner in s.afinidad:
                target = owner
        else:
            target = params.get("personaje_id")
        if not target:
            return
        actual = int(s.afinidad.get(target, 50))
        s.afinidad[target] = max(0, min(100, actual + int(float(params.get("valor") or 0))))
        return

    if prim == "otorgar_tag":
        agregar_tag(s, params.get("tag"))
        return

    if prim == "remover_tag":
        if params.get("tag") in s.tags:
            s.tags.remove(params.get("tag"))
        return

    if prim == "amortiguar_danio":
        clave = params.get("clave")
        reduccion = float(params.get("valor") or params.get("porcentaje") or 0)
        existente = next(
            (m for m in s.mods
             if m.get("tipo") == "amortiguar_danio" and m.get("clave") == clave and m.get("fuente") == owner),
            None,
        )
        if existente:
            existente["reduccion_porcentual"] = max(float(existente.get("reduccion_porcentual", 0)), reduccion)
        else:
            s.mods.append({"tipo": "amortiguar_danio", "clave": clave, "reduccion_porcentual": reduccion, "fuente": owner})
        return

    if prim == "mutar_estado":
        ruta = params.get("ruta") or params.get("clave")
        if not ruta:
            return
        op = params.get("operacion_matematica", "sumar")
        valor = float(params.get("valor") or 0.0)

        if ruta.startswith("recursos.") or ruta in BASE_RECURSOS:
            clave = ruta.split(".", 1)[1] if ruta.startswith("recursos.") else ruta
            if clave not in s.recursos:
                return
            actual = float(s.recursos[clave])
            nuevo = operar(actual, op, valor)
            aplicar_delta(s, clave, nuevo - actual)
            return

        if ruta.startswith("limites."):
            partes = ruta.split(".")
            if len(partes) < 3:
                return
            clave, sub = partes[1], partes[2]
            lim = s.limites.setdefault(clave, {})
            default = 0 if sub == "min" else 100
            if clave in BASE_RECURSOS:
                default = BASE_RECURSOS[clave].get(sub, default)
            actual = float(lim.get(sub, default))
            nuevo = int(round(operar(actual, op, valor)))
            otro = "max" if sub == "min" else "min"
            valor_otro = lim.get(otro)
            if valor_otro is None:
                valor_otro = BASE_RECURSOS.get(clave, {}).get(otro)
            if valor_otro is not None:
                nuevo = min(nuevo, int(valor_otro)) if sub == "min" else max(nuevo, int(valor_otro))
            lim[sub] = nuevo
            if clave in s.recursos:
                lo = float(lim.get("min", BASE_RECURSOS.get(clave, {}).get("min", 0)))
                hi = float(lim.get("max", BASE_RECURSOS.get(clave, {}).get("max", 100)))
                s.recursos[clave] = int(max(lo, min(hi, float(s.recursos[clave]))))
            return

        if ruta.startswith("afinidad."):
            target = ruta.split(".", 1)[1]
            if target in ("portador", "self", "me"):
                if owner in s.afinidad:
                    target = owner
                else:
                    return
            if target in s.afinidad:
                actual = float(s.afinidad[target])
                s.afinidad[target] = max(0, min(100, int(round(operar(actual, op, valor)))))
            return

        if ruta.startswith("variables."):
            clave = ruta.split(".", 1)[1]
            actual = float(s.variables.get(clave, 0.0))
            s.variables[clave] = round(operar(actual, op, valor), 4)


def frecuencia_coincide(efecto, trigger, s, owner, mes):
    disp = norm(trigger)
    if efecto.get("disparador") and norm(efecto["disparador"]) == disp:
        return True
    fid = efecto.get("frecuencia_id")
    item = FREQS.get(fid)
    if not item or norm(item.get("evento_motor")) != disp:
        return False
    if disp != "inicio_mes":
        return True
    cada = max(1, int(item.get("cada", 1) or 1))
    desfase = int(item.get("desfase", 0) or 0)
    conteo = item.get("conteo_desde", "adquisicion")
    if conteo == "adquisicion" and owner:
        mes_adq = int((s.adq.get(owner) or {}).get("mes", 1))
        delta = mes - mes_adq
        return delta > 0 and (delta - desfase) >= 0 and ((delta - desfase) % cada == 0)
    return (mes - desfase) > 0 and ((mes - desfase) % cada == 0)


def dispatch(s, efectos, trigger, owner, mes):
    for efecto in efectos or []:
        if not frecuencia_coincide(efecto, trigger, s, owner, mes):
            continue
        if not evaluar_condiciones(efecto.get("condiciones") or [], s):
            continue
        acciones = efecto.get("acciones") or []
        if acciones:
            for accion in acciones:
                ejecutar_accion(s, accion["accion_id"], accion.get("parametros") or {}, owner)
        elif efecto.get("accion"):
            leg = efecto["accion"]
            ejecutar_accion(s, leg.get("tipo"), {
                "clave": leg.get("clave"),
                "valor": leg.get("valor"),
                "tipo_calculo": leg.get("tipo_calculo", "fijo"),
                "personaje_id": leg.get("personaje_id"),
                "tag": leg.get("tag"),
                "destino": "portador" if not leg.get("personaje_id") else "personaje",
            }, owner)


# =============================================================================
# Transiciones esperadas
# =============================================================================

def ref_setup(attrs, char_ids, card_ids):
    chars = db_order("narrative_characters", char_ids)
    cards = db_order("narrative_cards", card_ids)
    s = Ref(
        recursos=dict(attrs),
        afinidad={cid: CHARS[cid].get("afinidad_inicial", 50) for cid in chars},
        tags=sorted({t for cid in cards for t in (CARDS[cid].get("tags") or [])}),
        limites={k: {"min": v.get("min", 0), "max": v.get("max", 100)} for k, v in BASE_RECURSOS.items()},
        variables={},
        mods=[],
        cartas=list(card_ids),
        adq={**{cid: {"mes": 1} for cid in chars}, **{cid: {"mes": 1} for cid in cards}},
        mes=1,
    )
    for cid in chars:
        dispatch(s, CHARS[cid].get("efectos"), "al_obtener", cid, 1)
    for cid in cards:
        dispatch(s, CARDS[cid].get("efectos"), "al_obtener", cid, 1)
    return s


def ref_draft(run, card_id):
    s = Ref.from_run(run)
    s.cartas.append(card_id)
    s.adq[card_id] = {"mes": s.mes, "tipo": "carta"}
    for t in CARDS[card_id].get("tags") or []:
        agregar_tag(s, t)
    dispatch(s, CARDS[card_id].get("efectos"), "al_obtener", card_id, s.mes)
    return s


def ref_month(run, nuevo_mes):
    s = Ref.from_run(run)
    s.mes = nuevo_mes
    for cid in db_order("narrative_characters", list(s.afinidad.keys())):
        dispatch(s, CHARS[cid].get("efectos"), "cada_mes", cid, nuevo_mes)
    for cid in db_order("narrative_cards", s.cartas):
        dispatch(s, CARDS[cid].get("efectos"), "cada_mes", cid, nuevo_mes)
    return s


def ref_terminal(run, tipo, grafo_id, nodo_id):
    s = Ref.from_run(run)
    g = GRAPHS.get((tipo, grafo_id))
    if not g or nodo_id not in (g.get("nodos") or {}):
        return None
    nodo = g["nodos"][nodo_id]
    for imp in nodo.get("impactos_recursos") or []:
        aplicar_delta(s, str(imp.get("recurso", "")).lower(), float(imp.get("delta") or 0))
    for imp in nodo.get("impactos_afinidad") or []:
        pid = imp.get("personaje_id")
        if pid in s.afinidad:
            s.afinidad[pid] = max(0, min(100, s.afinidad[pid] + int(imp.get("delta") or 0)))
    for tag in nodo.get("impactos_tags") or []:
        agregar_tag(s, tag)
    if nodo.get("efectos"):
        dispatch(s, nodo["efectos"], "al_desenlace", None, s.mes)
    senal = nodo.get("tipo_desenlace")
    if not senal:
        neto = sum(float(i.get("delta") or 0) for i in nodo.get("impactos_recursos") or [])
        senal = "positivo" if neto > 0 else ("negativo" if neto < 0 else None)
    if senal in ("positivo", "negativo"):
        trig = "en_evento_positivo" if senal == "positivo" else "en_evento_negativo"
        for cid in db_order("narrative_cards", s.cartas):
            dispatch(s, CARDS[cid].get("efectos"), trig, cid, s.mes)
        for cid in db_order("narrative_characters", list(s.afinidad.keys())):
            dispatch(s, CHARS[cid].get("efectos"), trig, cid, s.mes)
    return s


# =============================================================================
# Cliente HTTP
# =============================================================================

class Api:
    def __init__(self):
        self.credential = None
        self.guest_id = None
        self.calls = 0

    def _request(self, method, path, body=None, auth=True):
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth and self.credential:
            headers["X-Guest-Credential"] = self.credential
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as res:
                self.calls += 1
                raw = res.read().decode("utf-8")
                return res.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw
            return err.code, payload

    def guest(self):
        for intento in range(2):
            status, data = self._request("POST", "/api/auth/guest-credential", auth=False)
            if status == 200:
                self.credential = data["credential"]
                self.guest_id = data["guest_id"]
                return
            if status == 429 and intento == 0:
                time.sleep(6)
                continue
            raise RuntimeError(f"guest-credential fallo: {status} {data}")

    def get(self, path):
        status, data = self._request("GET", path)
        if status != 200:
            raise RuntimeError(f"GET {path} -> {status}: {data}")
        return data

    def post(self, path, body):
        status, data = self._request("POST", path, body)
        if status != 200:
            raise RuntimeError(f"POST {path} -> {status}: {data}")
        return data


def leer_run(api, date=DATE):
    return db.narrative_runs.find_one({"guest_id": api.guest_id, "date": date, "game_id": "narrativo"})


def comparar_estado(label, esperado, run, respuesta=None, campos=("recursos", "afinidad")):
    snap = esperado.snapshot()
    if "recursos" in campos:
        check(run.get("recursos") == snap["recursos"], f"{label}: recursos",
              snap["recursos"], run.get("recursos"))
        if respuesta is not None and respuesta.get("recursos") is not None:
            check(respuesta["recursos"] == snap["recursos"], f"{label}: recursos en payload",
                  snap["recursos"], respuesta["recursos"])
    if "afinidad" in campos:
        check(run.get("afinidad") == snap["afinidad"], f"{label}: afinidad",
              snap["afinidad"], run.get("afinidad"))
        if respuesta is not None and respuesta.get("afinidad") is not None:
            check(respuesta["afinidad"] == snap["afinidad"], f"{label}: afinidad en payload",
                  snap["afinidad"], respuesta["afinidad"])
    if "tags" in campos:
        check(sorted(run.get("tags_activos", [])) == snap["tags"], f"{label}: tags",
              snap["tags"], sorted(run.get("tags_activos", [])))
    if "limites" in campos:
        check(run.get("limites") == snap["limites"], f"{label}: limites",
              snap["limites"], run.get("limites"))
    if "variables" in campos:
        check(run.get("variables") == snap["variables"], f"{label}: variables",
              snap["variables"], run.get("variables"))
    if "mods" in campos:
        actuales = sorted(
            (m.get("tipo"), m.get("clave"), m.get("reduccion_porcentual"), m.get("fuente"))
            for m in run.get("modificadores_pasivos", [])
        )
        check(actuales == snap["mods"], f"{label}: modificadores pasivos", snap["mods"], actuales)
    if "cartas" in campos:
        check(sorted(run.get("cartas_en_mano", [])) == snap["cartas"], f"{label}: cartas en mano",
              snap["cartas"], sorted(run.get("cartas_en_mano", [])))
    if "adq" in campos:
        actuales = {k: (v or {}).get("mes") for k, v in (run.get("adquisiciones") or {}).items()}
        check(actuales == snap["adq"], f"{label}: adquisiciones", snap["adq"], actuales)


ALL_CAMPOS = ("recursos", "afinidad", "tags", "limites", "variables", "mods", "cartas", "adq")


# =============================================================================
# Juego por API
# =============================================================================

def jugar_escenario(nombre, char_ids, card_ids, meses, preferencias=None, date=DATE):
    """Juega una partida y audita setup, drafts, terminales y transiciones mensuales."""
    print(f"\n=== {nombre} (fecha {date}) ===")
    print(f"  corte={char_ids}")
    print(f"  cartas iniciales={card_ids}")
    api = Api()
    api.guest()
    setup = api.get(f"/api/narrative/partida/setup?date={date}")
    ofrecidos_p = {p["_id"] for p in setup["personajes_ofrecidos"]}
    ofrecidos_c = {c["_id"] for c in setup["cartas_ofrecidas"]}
    check(set(char_ids) <= ofrecidos_p, "setup: personajes elegidos estan en la oferta",
          sorted(ofrecidos_p), char_ids)
    check(set(card_ids) <= ofrecidos_c, "setup: cartas elegidas estan en la oferta",
          sorted(ofrecidos_c), card_ids)

    attrs = setup.get("atributos_iniciales") or {}
    inicio = api.post("/api/narrative/v2/partida/iniciar", {
        "date": date, "corte_elegida_ids": char_ids, "cartas_iniciales_ids": card_ids,
    })
    run = leer_run(api, date)
    check(inicio.get("motor") == "v2", "setup: motor v2", "v2", inicio.get("motor"))
    esperado = ref_setup(attrs, char_ids, card_ids)
    comparar_estado("setup", esperado, run, inicio, ALL_CAMPOS)
    print(f"  (setup) recursos={run.get('recursos')} afinidad={run.get('afinidad')}")
    print(f"  (setup) limites={run.get('limites')} tags={sorted(run.get('tags_activos', []))}")
    if run.get("variables"):
        print(f"  (setup) variables={run.get('variables')}")

    carta_actual = inicio
    mes = 1
    cobertura = set(card_ids)

    while mes <= meses:
        ofrecidas = [c["_id"] for c in carta_actual.get("cartas_draft_actual") or []]
        if not ofrecidas:
            print("  (sin cartas de draft: fin de partida)")
            break
        elegida = None
        for pref in (preferencias or {}).get(mes, []):
            if pref in ofrecidas:
                elegida = pref
                break
        if elegida is None:
            no_probadas = [c for c in ofrecidas if c not in cobertura]
            elegida = (no_probadas or ofrecidas)[0]

        run_antes = leer_run(api, date)
        rec_antes = dict(run_antes.get("recursos") or {})
        draft = api.post("/api/narrative/v2/partida/elegir-carta-mes", {"date": date, "carta_id": elegida})
        run_despues = leer_run(api, date)
        esperado = ref_draft(run_antes, elegida)
        comparar_estado(f"draft mes {mes} [{elegida}]", esperado, run_despues, draft, ALL_CAMPOS)
        cobertura.add(elegida)
        print(f"  (mes {mes}) carta elegida: {elegida}  delta={ {k: run_despues['recursos'][k] - rec_antes.get(k, 0) for k in run_despues.get('recursos', {})} }")

        grafo = draft.get("grafo_actual")
        if not grafo:
            print("  (sin grafo: fin o balance)")
            break

        # Recorrer el grafo hasta BALANCE_MES, auditando cada terminal.
        run_before = leer_run(api, date)
        pasos = 0
        while grafo and pasos < 40:
            pasos += 1
            nodo = grafo.get("nodo_actual") or {}
            if nodo.get("es_final"):
                tipo, gid, nid = grafo.get("tipo"), grafo.get("grafo_id"), nodo.get("id")
                esperado_term = ref_terminal(run_before, tipo, gid, nid)
                if esperado_term is None:
                    check(False, f"terminal {tipo}/{gid}/{nid}: grafo o nodo encontrado en DB")
                else:
                    # La respuesta del terminal ya trae el estado aplicado.
                    comparar_estado(
                        f"terminal {tipo}/{gid}/{nid}",
                        esperado_term, leer_run(api, date), grafo,
                        ("recursos", "afinidad", "tags"),
                    )
                cadena = grafo.get("conversacion_actual")
                if cadena:
                    decisiones = [d["opcion"] for d in cadena.get("decisiones") or []]
                    check(bool(decisiones), f"cadena {cadena.get('_id')}: decisiones presentes")
                    if not decisiones:
                        break
                    run_before = leer_run(api, date)
                    grafo = api.post("/api/narrative/v2/partida/avanzar-nodo", {
                        "date": date, "opcion_id": decisiones[0],
                    })
                    continue
                break

            if grafo.get("fase_actual") == "BALANCE_MES":
                break
            opciones = [o for o in nodo.get("opciones") or [] if o.get("disponible")]
            check(bool(opciones), f"nodo {nodo.get('id')}: opciones disponibles")
            if not opciones:
                break
            run_before = leer_run(api, date)
            grafo = api.post("/api/narrative/v2/partida/avanzar-nodo", {
                "date": date, "opcion_id": opciones[0]["id"],
            })

        if grafo is None or grafo.get("status") not in (None, "in_progress", "CONTINUA"):
            print(f"  (partida terminada: status={grafo.get('status') if grafo else '—'})")
            break

        run_balance = leer_run(api, date)
        if run_balance.get("fase_actual") != "BALANCE_MES":
            print(f"  (fase {run_balance.get('fase_actual')}: no se puede avanzar mes)")
            break
        if mes >= meses:
            break

        rec_antes_mes = dict(run_balance.get("recursos") or {})
        avance = api.post("/api/narrative/v2/partida/avanzar-mes", {"date": date})
        run_nuevo = leer_run(api, date)
        esperado = ref_month(run_balance, avance.get("mes_actual"))
        comparar_estado(f"avanzar-mes {mes}->{avance.get('mes_actual')}", esperado, run_nuevo, avance, ALL_CAMPOS)
        print(
            f"  (mes {mes}->{avance.get('mes_actual')}) pasivos antes={rec_antes_mes} "
            f"despues={run_nuevo.get('recursos')} "
            f"delta={ {k: run_nuevo['recursos'][k] - rec_antes_mes.get(k, 0) for k in run_nuevo.get('recursos', {})} }"
        )
        carta_actual = avance
        mes = avance.get("mes_actual") or mes + 1
        if avance.get("finalizacion") or avance.get("status") not in (None, "in_progress"):
            print("  (partida terminada tras avanzar mes)")
            break

    return cobertura


def main():
    print("Auditoria de efectos configurados contra la API real")
    print(f"  base={BASE} fecha={DATE} universo={UNIVERSO_ID}")
    print(f"  cartas={len(CARDS)} personajes={len(CHARS)} grafos={len(GRAPHS)} frecuencias={len(FREQS)}")

    cobertura = set()
    cobertura |= jugar_escenario(
        "S1 limites, porcentaje y min",
        ["pj_comandante_marcus", "pj_ladrona_sylvia", "pj_alquimista_vera"],
        ["card_bendicion_papal", "card_reserva_trigo", "card_escudo_hierro"],
        1,
    )
    cobertura |= jugar_escenario(
        "S2 amortiguacion simple y limite oro",
        ["pj_ladrona_sylvia", "pj_alquimista_vera", "pj_canciller_elena"],
        ["card_mercenarios", "card_reserva_trigo", "card_bendicion_papal"],
        2,
        preferencias={1: ["card_red_espias", "card_festival_cosecha"]},
    )
    cobertura |= jugar_escenario(
        "S3 pasivos mensuales (Marcus/Elena/Vera/diezmo)",
        ["pj_comandante_marcus", "pj_canciller_elena", "pj_alquimista_vera"],
        ["card_diezmo_comercial", "card_escudo_hierro", "card_bendicion_papal"],
        4,
    )
    cobertura |= jugar_escenario(
        "S4 cartas del pool mensual + pasivos combinados",
        ["pj_canciller_elena", "pj_comandante_marcus", "pj_ladrona_sylvia"],
        ["card_reserva_trigo", "card_mercenarios", "card_diezmo_comercial"],
        8,
        preferencias={
            1: ["card_red_espias", "card_sello_real", "card_carretas_logistica"],
            2: ["card_festival_cosecha", "card_tratado_paz", "card_remedio_herbario"],
        },
    )
    cobertura |= jugar_escenario(
        "S5 remedio sin clamp (pueblo bajo)",
        ["pj_comandante_marcus", "pj_ladrona_sylvia", "pj_alquimista_vera"],
        ["card_bendicion_papal", "card_escudo_hierro", "card_mercenarios"],
        2,
        preferencias={1: ["card_remedio_herbario", "card_festival_cosecha"], 2: ["card_remedio_herbario", "card_sello_real"]},
    )
    cobertura |= jugar_escenario(
        "S6 Tomas, sello_real y pasivos (otra fecha)",
        ["pj_comandante_marcus", "pj_obispo_tomas", "pj_alquimista_vera"],
        ["card_diezmo_comercial", "card_sello_real", "card_red_espias"],
        3,
        preferencias={1: ["card_remedio_herbario", "card_tratado_paz"], 2: ["card_festival_cosecha", "card_carretas_logistica"]},
        date="2026-12-31",
    )

    pool_total = set(CARDS)
    print("\n=== Cobertura de cartas ===")
    print(f"  probadas: {len(cobertura)}/{len(pool_total)}")
    print(f"  sin probar: {sorted(pool_total - cobertura)}")

    print("\n=== Resumen ===")
    print(f"  PASS={PASS} FAIL={FAIL}")

    fallos = [c for c in CHECKS if c[0] == "FAIL"]
    if fallos:
        print("\nFallos:")
        for f in fallos:
            print(f"  - {f[1]}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
