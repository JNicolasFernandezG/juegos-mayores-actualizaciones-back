"""
Contenido adicional del catálogo narrativo V2 para `corte_medieval`.

Reúne tres cosas, todas insert-only:
- 12 eventos propios (`_v2d`) con categoría y tono explícitos.
- 12 eventos ya validados en desarrollo (`_v2c`), exportados a `data/eventos_v2c.json`.
- 10 cartas y 5 personajes para ampliar el pool del draft y la corte.

Los eventos se siembran desde `seed_narrative_v2_graphs.py`; las cartas y los
personajes solo se insertan con `expand_narrative_catalog.py`, porque son
contenido del operador y no deben sembrarse en cada arranque.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.features.narrative.enums import TipoResultadoEnum
from app.features.narrative.schemas.catalog_schemas import (
    CartaCreateRequest,
    PersonajeCreateRequest,
)
from app.features.narrative.schemas.v2_graph_schemas import (
    EventoV2GrafoSchema,
    ImpactoAfinidadSchema,
    ImpactoRecursoSchema,
    NodoNarrativoSchema,
    OpcionNodoSchema,
)

UNIVERSO_ID = "corte_medieval"
IMAGEN_EVENTO = "/assets/narrative/eventos/default.webp"
IMAGEN_CARTA = "/assets/narrative/cartas/default.webp"
IMAGEN_PERSONAJE = "/assets/narrative/personajes/default.webp"

DATA_V2C = Path(__file__).parent / "data" / "eventos_v2c.json"


def _cond_pj(personaje_id: str) -> Dict[str, Any]:
    return {
        "tipo": "tiene_personaje",
        "clave": None,
        "operador": None,
        "valor": None,
        "personaje_id": personaje_id,
        "carta_id": None,
        "tag": None,
    }


def _final(spec: Dict[str, Any]) -> NodoNarrativoSchema:
    return NodoNarrativoSchema(
        id=spec["id"],
        hablante_id="narrador",
        texto=spec["texto"],
        es_final=True,
        resultado_texto=spec["resultado"],
        impactos_recursos=[
            ImpactoRecursoSchema(recurso=clave, delta=delta)
            for clave, delta in (spec.get("recursos") or {}).items()
        ],
        impactos_afinidad=[
            ImpactoAfinidadSchema(personaje_id=pj, delta=delta)
            for pj, delta in (spec.get("afinidad") or {}).items()
        ],
        tipo_desenlace=TipoResultadoEnum(spec["tipo"]),
    )


def _evento(spec: Dict[str, Any]) -> EventoV2GrafoSchema:
    nodos: Dict[str, NodoNarrativoSchema] = {}
    opciones: List[OpcionNodoSchema] = []
    for opcion in spec["opciones"]:
        final = _final(opcion["final"])
        nodos[final.id] = final
        opciones.append(
            OpcionNodoSchema(
                id=opcion["id"],
                texto=opcion["texto"],
                siguiente_nodo=final.id,
                condiciones=[_cond_pj(opcion["requiere_pj"])] if opcion.get("requiere_pj") else [],
                bloqueo_modo="oculta" if opcion.get("requiere_pj") else "deshabilitada",
            )
        )
    nodos["nodo_inicio"] = NodoNarrativoSchema(
        id="nodo_inicio",
        hablante_id="narrador",
        texto=spec["inicio"],
        opciones=opciones,
    )
    return EventoV2GrafoSchema(
        _id=spec["id"],
        universo_id=UNIVERSO_ID,
        titulo=spec["titulo"],
        descripcion=spec["descripcion"],
        imagen=IMAGEN_EVENTO,
        peso_base=spec.get("peso_base", 90.0),
        tags_tematicos=spec["tags"],
        categoria=spec["categoria"],
        tono=spec["tono"],
        nodo_raiz="nodo_inicio",
        nodos=nodos,
    )


EVENTOS_NUEVOS: List[Dict[str, Any]] = [
    {
        "id": "evt_leva_forzosa_v2d",
        "titulo": "La Leva de la Frontera",
        "descripcion": "La frontera norte exige refuerzos y el mariscal propone reclutar a la fuerza entre los campesinos.",
        "categoria": "Ejército",
        "tono": "negativo",
        "tags": ["militar", "pueblo", "frontera"],
        "peso_base": 90.0,
        "inicio": "El mariscal Aldric advierte que las murallas del norte necesitan hombres antes de la próxima luna. Los alguaciles ya recorren las aldeas con listas de reclutamiento.",
        "opciones": [
            {
                "id": "opt_leva_obligatoria",
                "texto": "Autorizar la leva obligatoria en las aldeas",
                "final": {
                    "id": "fin_leva_cumplida",
                    "texto": "Los carros parten al norte",
                    "resultado": "Los regimientos se completan, pero las familias campesinas maldicen el nombre de la corona.",
                    "tipo": "negativo",
                    "recursos": {"ejercito": 15, "pueblo": -15},
                    "afinidad": {"pj_comandante_marcus": 10, "pj_canciller_elena": -5},
                },
            },
            {
                "id": "opt_mercenarios",
                "texto": "Pagar mercenarios con el tesoro real",
                "final": {
                    "id": "fin_mercenarios_pagados",
                    "texto": "Lanzas extranjeras en la muralla",
                    "resultado": "Las compañías libres llegan a tiempo, aunque su precio vacía parte del tesoro.",
                    "tipo": "neutro",
                    "recursos": {"oro": -18, "ejercito": 10},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
            {
                "id": "opt_voluntarios_iglesia",
                "texto": "Pedir voluntarios a las parroquias",
                "requiere_pj": "pj_obispo_tomas",
                "final": {
                    "id": "fin_voluntarios_parroquia",
                    "texto": "La fe marcha al norte",
                    "resultado": "El obispo predica una cruzada defensiva y cientos de fieles se alistan por convicción.",
                    "tipo": "positivo",
                    "recursos": {"ejercito": 8, "fe": 5, "pueblo": -5},
                    "afinidad": {"pj_obispo_tomas": 12},
                },
            },
        ],
    },
    {
        "id": "evt_desfile_veteranos_v2d",
        "titulo": "El Regreso de los Veteranos",
        "descripcion": "Los veteranos del Paso regresan mutilados pero victoriosos, y la ciudad espera honrarlos.",
        "categoria": "Ejército",
        "tono": "positivo",
        "tags": ["militar", "honor", "pueblo"],
        "peso_base": 85.0,
        "inicio": "Una columna de veteranos entra por la puerta sur. Traen estandartes rotos, heridas abiertas y la victoria en los ojos. La multitud aguarda en silencio.",
        "opciones": [
            {
                "id": "opt_desfile_pensiones",
                "texto": "Ofrecer desfile triunfal y pensiones vitalicias",
                "final": {
                    "id": "fin_desfile_glorioso",
                    "texto": "La plaza estalla en vítores",
                    "resultado": "Los veteranos desfilan bajo lluvia de flores y el pueblo siente suya la victoria.",
                    "tipo": "positivo",
                    "recursos": {"pueblo": 10, "oro": -12},
                    "afinidad": {"pj_comandante_marcus": 12},
                },
            },
            {
                "id": "opt_tierras_frontera",
                "texto": "Entregarles tierras en la frontera",
                "final": {
                    "id": "fin_tierras_veteranas",
                    "texto": "Nuevas aldeas de soldados",
                    "resultado": "Los veteranos fundan colonias armadas que custodian el paso y trabajan la tierra.",
                    "tipo": "positivo",
                    "recursos": {"pueblo": 8, "ejercito": 8, "oro": -5},
                    "afinidad": {"pj_comandante_marcus": 10, "pj_canciller_elena": 5},
                },
            },
            {
                "id": "opt_disolver_compania",
                "texto": "Disolver la compañía sin honores",
                "final": {
                    "id": "fin_compania_disuelta",
                    "texto": "Silencio en el cuartel",
                    "resultado": "Los soldados entregan las armas en silencio; la guarnición pierde su mejor espada.",
                    "tipo": "negativo",
                    "recursos": {"ejercito": -12, "pueblo": -10},
                    "afinidad": {"pj_comandante_marcus": -15},
                },
            },
        ],
    },
    {
        "id": "evt_tribunal_guerra_v2d",
        "titulo": "El Tribunal del Vado",
        "descripcion": "Tras la derrota en el vado, el consejo de guerra exige un culpable antes del amanecer.",
        "categoria": "Ejército",
        "tono": "neutro",
        "tags": ["militar", "justicia", "corte"],
        "peso_base": 85.0,
        "inicio": "El vado se perdió y con él tres estandartes. Los capitanes discuten en el salón de guerra mientras la corte espera un veredicto.",
        "opciones": [
            {
                "id": "opt_culpar_capitan",
                "texto": "Culpar al capitán y reorganizar la guardia",
                "final": {
                    "id": "fin_capitan_culpable",
                    "texto": "Un chivo expiatorio útil",
                    "resultado": "El capitán es degradado y la guardia se reorganiza, aunque algunos oficiales murmuran.",
                    "tipo": "neutro",
                    "recursos": {"ejercito": -8, "pueblo": 5},
                    "afinidad": {"pj_comandante_marcus": -8},
                },
            },
            {
                "id": "opt_asumir_derrota",
                "texto": "Asumir la derrota ante la corte",
                "final": {
                    "id": "fin_derrota_asumida",
                    "texto": "El peso de la corona",
                    "resultado": "El rey reconoce el error en público; la corte respeta la honestidad pero duda del mando.",
                    "tipo": "negativo",
                    "recursos": {"ejercito": -8, "pueblo": -5},
                    "afinidad": {"pj_comandante_marcus": 10},
                },
            },
            {
                "id": "opt_informe_sylvia",
                "texto": "Escuchar el informe de la ladrona",
                "requiere_pj": "pj_ladrona_sylvia",
                "final": {
                    "id": "fin_informe_espia",
                    "texto": "La verdad del vado",
                    "resultado": "Sylvia revela que el vado cayó por una traición interna; la guardia caza al traidor.",
                    "tipo": "positivo",
                    "recursos": {"ejercito": 10, "oro": -5},
                    "afinidad": {"pj_ladrona_sylvia": 15},
                },
            },
        ],
    },
    {
        "id": "evt_boda_dinastica_v2d",
        "titulo": "La Boda de los Dos Linajes",
        "descripcion": "La Casa de Valoria propone un matrimonio que uniría a dos linajes rivales.",
        "categoria": "Nobleza",
        "tono": "positivo",
        "tags": ["nobleza", "diplomacia", "dote"],
        "peso_base": 90.0,
        "inicio": "Los heraldos de Valoria traen un contrato matrimonial sellado con cera azul. La dote es generosa; las intenciones, menos claras.",
        "opciones": [
            {
                "id": "opt_aceptar_boda",
                "texto": "Aceptar la boda y la dote",
                "final": {
                    "id": "fin_boda_celebrada",
                    "texto": "Campanas y contratos",
                    "resultado": "El enlace sella la paz entre los linajes y llena las arcas con una dote considerable.",
                    "tipo": "positivo",
                    "recursos": {"oro": 15, "pueblo": 10},
                    "afinidad": {"pj_canciller_elena": 10},
                },
            },
            {
                "id": "opt_rechazar_orgullo",
                "texto": "Rechazar la oferta por orgullo",
                "final": {
                    "id": "fin_boda_rechazada",
                    "texto": "Heridas abiertas",
                    "resultado": "Valoria retira a sus embajadores y la corte queda aislada de buena parte de la nobleza.",
                    "tipo": "negativo",
                    "recursos": {"fe": -10, "pueblo": -5},
                    "afinidad": {"pj_canciller_elena": -12},
                },
            },
            {
                "id": "opt_torneo_abierto",
                "texto": "Celebrar con un torneo abierto al pueblo",
                "final": {
                    "id": "fin_torneo_boda",
                    "texto": "Fiesta en el campo",
                    "resultado": "La boda se celebra con justas y pan gratis; el pueblo celebra, el tesoro paga.",
                    "tipo": "neutro",
                    "recursos": {"pueblo": 8, "oro": -8},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
        ],
    },
    {
        "id": "evt_herencia_disputada_v2d",
        "titulo": "El Condado en Disputa",
        "descripcion": "Dos primos reclaman el condado del sur y han movilizado a sus mesnadas.",
        "categoria": "Nobleza",
        "tono": "negativo",
        "tags": ["nobleza", "justicia", "feudo"],
        "peso_base": 85.0,
        "inicio": "Los primos de Arvenia acampan a ambos lados del río con sus mesnadas. Cada uno exige el sello del condado y amenaza con tomarlo.",
        "opciones": [
            {
                "id": "opt_fallar_mayor",
                "texto": "Fallar a favor del primogénito",
                "final": {
                    "id": "fin_mayor_favorecido",
                    "texto": "La ley del linaje",
                    "resultado": "El mayor recibe el condado y disuelve su mesnada; el menor se retira humillado.",
                    "tipo": "neutro",
                    "recursos": {"ejercito": 8, "pueblo": -12},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
            {
                "id": "opt_dividir_condado",
                "texto": "Dividir el condado en dos",
                "final": {
                    "id": "fin_condado_dividido",
                    "texto": "Dos señores, un río",
                    "resultado": "La partición evita la guerra pero deja dos feudos empobrecidos y rencorosos.",
                    "tipo": "negativo",
                    "recursos": {"oro": -10, "ejercito": -5},
                    "afinidad": {"pj_canciller_elena": -5},
                },
            },
            {
                "id": "opt_comprar_pleito",
                "texto": "Comprar el pleito con oro de la corona",
                "final": {
                    "id": "fin_pleito_comprado",
                    "texto": "La paz tiene precio",
                    "resultado": "Un acuerdo secreto satisface a ambos primos y evita el derramamiento de sangre.",
                    "tipo": "positivo",
                    "recursos": {"oro": -18, "pueblo": 8},
                    "afinidad": {"pj_canciller_elena": 12},
                },
            },
        ],
    },
    {
        "id": "evt_auditoria_tesoro_v2d",
        "titulo": "Las Cuentas del Reino",
        "descripcion": "El contador real detecta faltantes en las cuentas de la corte y teme por su vida.",
        "categoria": "Oro",
        "tono": "neutro",
        "tags": ["oro", "cuentas", "corte"],
        "peso_base": 85.0,
        "inicio": "El contador real llega pálido con libros bajo el brazo. Hay faltantes en las cuentas de la corte y nombres ilustres en los márgenes.",
        "opciones": [
            {
                "id": "opt_auditoria_publica",
                "texto": "Ordenar una auditoría pública",
                "final": {
                    "id": "fin_auditoria_publica",
                    "texto": "Cuentas claras",
                    "resultado": "La auditoría recupera parte del oro y enfurece a los nobles señalados.",
                    "tipo": "positivo",
                    "recursos": {"oro": 12, "pueblo": -8},
                    "afinidad": {"pj_canciller_elena": -8},
                },
            },
            {
                "id": "opt_encubrir_nobles",
                "texto": "Encubrir a los nobles implicados",
                "final": {
                    "id": "fin_encubrimiento",
                    "texto": "Silencio comprado",
                    "resultado": "Los nobles conservan sus privilegios y el tesoro sigue sangrando en silencio.",
                    "tipo": "negativo",
                    "recursos": {"oro": -12, "fe": 5},
                    "afinidad": {"pj_canciller_elena": 8},
                },
            },
            {
                "id": "opt_delegar_elena",
                "texto": "Delegar la revisión en la canciller",
                "final": {
                    "id": "fin_revision_elena",
                    "texto": "La mano de Elena",
                    "resultado": "Elena revisa los libros con frialdad y recupera fondos sin escándalo público.",
                    "tipo": "positivo",
                    "recursos": {"oro": 8, "pueblo": 5},
                    "afinidad": {"pj_canciller_elena": 10},
                },
            },
        ],
    },
    {
        "id": "evt_falsificadores_moneda_v2d",
        "titulo": "Moneda Falsa",
        "descripcion": "Circulan monedas falsas con el sello real y los mercaderes empiezan a desconfiar.",
        "categoria": "Oro",
        "tono": "negativo",
        "tags": ["oro", "comercio", "fraude"],
        "peso_base": 85.0,
        "inicio": "Un mercader muerde una moneda en el mercado y la escupe. El sello real se desprende como hojalata. La noticia corre más rápido que la guardia.",
        "opciones": [
            {
                "id": "opt_refundir_moneda",
                "texto": "Retirar y refundir la moneda falsa",
                "final": {
                    "id": "fin_moneda_refundida",
                    "texto": "El sello recupera su valor",
                    "resultado": "La corona asume el costo de la refundición y los mercaderes recuperan la confianza.",
                    "tipo": "positivo",
                    "recursos": {"oro": -10, "pueblo": 10},
                    "afinidad": {"pj_canciller_elena": 10},
                },
            },
            {
                "id": "opt_colgar_falsificadores",
                "texto": "Colgar a los falsificadores en la plaza",
                "final": {
                    "id": "fin_falsificadores_colgados",
                    "texto": "Ejemplo público",
                    "resultado": "El pueblo aplaude la mano dura, pero el clero condena la ejecución sin juicio.",
                    "tipo": "neutro",
                    "recursos": {"pueblo": 8, "fe": -8},
                    "afinidad": {"pj_obispo_tomas": -10},
                },
            },
            {
                "id": "opt_ignorar_fraude",
                "texto": "Ignorar el problema hasta que pase",
                "final": {
                    "id": "fin_fraude_ignorado",
                    "texto": "La confianza se rompe",
                    "resultado": "Los precios se disparan y el comercio del reino se paraliza por desconfianza.",
                    "tipo": "negativo",
                    "recursos": {"oro": -15, "pueblo": -10},
                    "afinidad": {"pj_canciller_elena": -10},
                },
            },
        ],
    },
    {
        "id": "evt_tregua_pirata_v2d",
        "titulo": "La Tregua de los Corsarios",
        "descripcion": "Los piratas de la costa ofrecen una tregua a cambio de un tributo anual.",
        "categoria": "Diplomacia",
        "tono": "positivo",
        "tags": ["diplomacia", "costa", "tributo"],
        "peso_base": 85.0,
        "inicio": "Una chalupa negra se acerca al puerto con bandera de parlamento. Los corsarios ofrecen dejar de saquear a cambio de un tributo anual.",
        "opciones": [
            {
                "id": "opt_aceptar_tributo",
                "texto": "Aceptar la tregua y pagar el tributo",
                "final": {
                    "id": "fin_tregua_pagada",
                    "texto": "Paz en la costa",
                    "resultado": "Los ataques cesan y los pescadores vuelven a hacerse a la mar, aunque el tesoro lo paga.",
                    "tipo": "positivo",
                    "recursos": {"oro": -10, "pueblo": 12},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
            {
                "id": "opt_armar_corsarios",
                "texto": "Rechazar y armar corsarios propios",
                "final": {
                    "id": "fin_corsarios_armados",
                    "texto": "Lobo contra lobo",
                    "resultado": "La corona arma sus propios corsarios; el mar se vuelve una guerra de sombras.",
                    "tipo": "neutro",
                    "recursos": {"oro": -12, "ejercito": 10},
                    "afinidad": {"pj_comandante_marcus": 8},
                },
            },
            {
                "id": "opt_infiltrar_espia",
                "texto": "Aceptar la tregua y infiltrar espías",
                "requiere_pj": "pj_ladrona_sylvia",
                "final": {
                    "id": "fin_tregua_infiltrada",
                    "texto": "La tregua como trampa",
                    "resultado": "Sylvia penetra la flota pirata y la corona conoce cada uno de sus movimientos.",
                    "tipo": "positivo",
                    "recursos": {"ejercito": 8, "oro": -5},
                    "afinidad": {"pj_ladrona_sylvia": 12},
                },
            },
        ],
    },
    {
        "id": "evt_mediacion_concilio_v2d",
        "titulo": "El Concilio del Río",
        "descripcion": "Dos reinos vecinos piden a la corte que medie en su disputa por el río.",
        "categoria": "Diplomacia",
        "tono": "neutro",
        "tags": ["diplomacia", "concilio", "vecinos"],
        "peso_base": 80.0,
        "inicio": "Dos delegaciones llegan al mismo tiempo y se niegan a compartir el salón. Ambos reinos exigen que la corona elija un bando.",
        "opciones": [
            {
                "id": "opt_mediar_neutral",
                "texto": "Mediar con neutralidad y garantías",
                "final": {
                    "id": "fin_mediacion_neutral",
                    "texto": "Árbitro respetado",
                    "resultado": "La corte gana prestigio como árbitro justo, aunque sin beneficios inmediatos.",
                    "tipo": "positivo",
                    "recursos": {"fe": 8, "pueblo": 5},
                    "afinidad": {"pj_obispo_tomas": 8},
                },
            },
            {
                "id": "opt_apoyar_fuerte",
                "texto": "Apoyar al reino más fuerte",
                "final": {
                    "id": "fin_apoyo_interesado",
                    "texto": "Alianza rentable",
                    "resultado": "El reino favorecido paga con oro y el otro jura venganza a largo plazo.",
                    "tipo": "negativo",
                    "recursos": {"oro": 10, "pueblo": -10},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
            {
                "id": "opt_cobrar_mediacion",
                "texto": "Cobrar por la mediación",
                "final": {
                    "id": "fin_mediacion_cobrada",
                    "texto": "El precio de la paz",
                    "resultado": "Ambos reinos pagan los honorarios del arbitraje; nadie queda del todo satisfecho.",
                    "tipo": "neutro",
                    "recursos": {"oro": 12, "fe": -5},
                    "afinidad": {"pj_canciller_elena": 5},
                },
            },
        ],
    },
    {
        "id": "evt_reliquia_robada_v2d",
        "titulo": "La Reliquia Robada",
        "descripcion": "La reliquia del santo patrón desapareció del claustro y la ciudad teme un castigo divino.",
        "categoria": "Fe",
        "tono": "positivo",
        "tags": ["fe", "reliquia", "clero"],
        "peso_base": 85.0,
        "inicio": "La vitrina del claustro está vacía. El hermano portero jura no haber oído nada, pero el pueblo ya habla de milagros perdidos y castigos.",
        "opciones": [
            {
                "id": "opt_buscar_ladrones",
                "texto": "Buscar a los ladrones por toda la ciudad",
                "final": {
                    "id": "fin_reliquia_recuperada",
                    "texto": "La reliquia vuelve al altar",
                    "resultado": "La guardia recupera la reliquia en un sótano del puerto y la fe se reaviva.",
                    "tipo": "positivo",
                    "recursos": {"fe": 10, "oro": -8},
                    "afinidad": {"pj_obispo_tomas": 12},
                },
            },
            {
                "id": "opt_reemplazar_secreto",
                "texto": "Reemplazarla en secreto por una copia",
                "final": {
                    "id": "fin_reliquia_falsa",
                    "texto": "Un milagro de yeso",
                    "resultado": "La copia engaña al pueblo por ahora, pero el clero sospecha y calla.",
                    "tipo": "negativo",
                    "recursos": {"fe": -10, "oro": 5},
                    "afinidad": {"pj_obispo_tomas": -12},
                },
            },
            {
                "id": "opt_investigar_sylvia",
                "texto": "Encargar la investigación a la ladrona",
                "requiere_pj": "pj_ladrona_sylvia",
                "final": {
                    "id": "fin_reliquia_por_sylvia",
                    "texto": "Ladrona contra ladrones",
                    "resultado": "Sylvia rastrea a los culpables en dos noches y devuelve la reliquia sin alboroto.",
                    "tipo": "positivo",
                    "recursos": {"fe": 12, "pueblo": 5},
                    "afinidad": {"pj_ladrona_sylvia": 12, "pj_obispo_tomas": 8},
                },
            },
        ],
    },
    {
        "id": "evt_caravana_perdida_v2d",
        "titulo": "La Caravana Perdida",
        "descripcion": "La caravana de especias no llegó al puerto y se teme un asalto en el bosque.",
        "categoria": "Comercio",
        "tono": "negativo",
        "tags": ["comercio", "caravana", "bosque"],
        "peso_base": 85.0,
        "inicio": "La caravana de especias debía llegar al alba. Solo llega un carretero herido que habla de flechas entre los árboles.",
        "opciones": [
            {
                "id": "opt_enviar_guardia",
                "texto": "Enviar la guardia a buscarla",
                "final": {
                    "id": "fin_guardia_bosque",
                    "texto": "Operativo en el bosque",
                    "resultado": "La guardia recupera parte de la carga, pero el despliegue cuesta oro y hombres.",
                    "tipo": "neutro",
                    "recursos": {"oro": -8, "pueblo": 5, "ejercito": -3},
                    "afinidad": {"pj_comandante_marcus": 5},
                },
            },
            {
                "id": "opt_asumir_perdida",
                "texto": "Asumir la pérdida y castigar al gremio",
                "final": {
                    "id": "fin_perdida_asumida",
                    "texto": "El gremio paga",
                    "resultado": "El gremio absorbe la pérdida, pero los precios suben y el pueblo protesta.",
                    "tipo": "negativo",
                    "recursos": {"oro": -15, "pueblo": -8},
                    "afinidad": {"pj_canciller_elena": -5},
                },
            },
            {
                "id": "opt_rescate_bandidos",
                "texto": "Negociar el rescate con los bandidos",
                "final": {
                    "id": "fin_rescate_caravana",
                    "texto": "Trato con forajidos",
                    "resultado": "Los bandidos entregan la carga a cambio de oro y un salvoconducto tácito.",
                    "tipo": "positivo",
                    "recursos": {"oro": -8, "pueblo": 10},
                    "afinidad": {"pj_ladrona_sylvia": 6},
                },
            },
        ],
    },
    {
        "id": "evt_observatorio_real_v2d",
        "titulo": "El Observatorio de Vera",
        "descripcion": "Vera propone construir un observatorio para predecir sequías y tormentas.",
        "categoria": "Ciencia",
        "tono": "positivo",
        "tags": ["ciencia", "astros", "alquimia"],
        "peso_base": 80.0,
        "inicio": "Vera despliega planos sobre la mesa del consejo: una torre de lentes que anticiparía sequías y tormentas. Los nobles bostezan, el obispo frunce el ceño.",
        "opciones": [
            {
                "id": "opt_financiar_observatorio",
                "texto": "Financiar el observatorio real",
                "final": {
                    "id": "fin_observatorio_erigido",
                    "texto": "La torre de los astros",
                    "resultado": "La torre se alza y sus pronósticos salvan la cosecha del año siguiente.",
                    "tipo": "positivo",
                    "recursos": {"oro": -15, "pueblo": 10},
                    "afinidad": {"pj_alquimista_vera": 15},
                },
            },
            {
                "id": "opt_descartar_herejia",
                "texto": "Descartar el proyecto como herejía",
                "final": {
                    "id": "fin_observatorio_descartado",
                    "texto": "Los planos al fuego",
                    "resultado": "Los planos arden y Vera se encierra en su laboratorio durante semanas.",
                    "tipo": "negativo",
                    "recursos": {"pueblo": -10, "fe": 5},
                    "afinidad": {"pj_alquimista_vera": -15, "pj_obispo_tomas": 5},
                },
            },
            {
                "id": "opt_fondos_iglesia",
                "texto": "Construirlo con fondos de la Iglesia",
                "final": {
                    "id": "fin_observatorio_eclesiastico",
                    "texto": "Ciencia con bendición",
                    "resultado": "La Iglesia financia la mitad de la torre y supervisa cada lente instalada.",
                    "tipo": "neutro",
                    "recursos": {"oro": -5, "fe": 5},
                    "afinidad": {"pj_alquimista_vera": 5, "pj_obispo_tomas": 5},
                },
            },
        ],
    },
]


CARTAS_NUEVAS: List[Dict[str, Any]] = [
    {
        "id": "card_guardia_palaciega",
        "categoria": "item",
        "nombre": "Guardia Palaciega",
        "descripcion": "Una compañía de alabarderos leales a la corona custodia los salones del palacio.",
        "tags": ["seguridad", "militar", "lealtad"],
    },
    {
        "id": "card_archivo_real",
        "categoria": "item",
        "nombre": "Archivo Real",
        "descripcion": "Legajos, cartas y genealogías que revelan deudas, pactos y parentescos ocultos.",
        "tags": ["inteligencia", "noble", "archivo"],
    },
    {
        "id": "card_pozo_artesano",
        "categoria": "bonus",
        "nombre": "Pozo de los Artesanos",
        "descripcion": "Un pozo nuevo abastece al barrio gremial y calma los ánimos durante las sequías.",
        "tags": ["pueblo", "obra", "agua"],
    },
    {
        "id": "card_cofre_limosnas",
        "categoria": "item",
        "nombre": "Cofre de Limosnas",
        "descripcion": "El cofre de la catedral acumula donaciones que la corona puede administrar con cuidado.",
        "tags": ["fe", "caridad", "oro"],
    },
    {
        "id": "card_mercenarios_norte",
        "categoria": "item",
        "nombre": "Compañía del Norte",
        "descripcion": "Veteranos endurecidos por la nieve que combaten por paga y reputación.",
        "tags": ["militar", "mercenarios", "frontera"],
    },
    {
        "id": "card_contrato_sal",
        "categoria": "bonus",
        "nombre": "Contrato de la Sal",
        "descripcion": "Un contrato exclusivo con las salinas asegura ingresos estables al tesoro.",
        "tags": ["comercio", "sal", "oro"],
    },
    {
        "id": "card_telescopio",
        "categoria": "item",
        "nombre": "Telescopio de Vera",
        "descripcion": "Lentes pulidas a mano que permiten leer el cielo y anticipar las tormentas.",
        "tags": ["ciencia", "astros", "pronostico"],
    },
    {
        "id": "card_cancion_protesta",
        "categoria": "bonus",
        "nombre": "Copla de los Barrios",
        "descripcion": "Una canción popular que circula por tabernas y plazas; dice en verso lo que el pueblo calla.",
        "tags": ["pueblo", "rumor", "cultura"],
    },
    {
        "id": "card_embajada_iliria",
        "categoria": "item",
        "nombre": "Embajada de Iliria",
        "descripcion": "Una legación permanente del reino vecino, con tratados y regalos protocolares.",
        "tags": ["diplomacia", "tratado", "iliria"],
    },
    {
        "id": "card_coronas_vasallas",
        "categoria": "item",
        "nombre": "Coronas Vasallas",
        "descripcion": "Cinco coronas menores que simbolizan los juramentos de lealtad de los señores del reino.",
        "tags": ["nobleza", "lealtad", "corona"],
    },
]


PERSONAJES_NUEVOS: List[Dict[str, Any]] = [
    {
        "id": "pj_mariscal_aldric",
        "nombre": "Aldric de la Marca",
        "titulo": "Mariscal de la Frontera",
        "descripcion": "Comandante curtido en el Paso, obsesionado con la disciplina y la defensa del norte.",
        "pros": ["Inspira lealtad en la tropa y endurece la guarnición.", "Conoce cada paso y vado de la frontera."],
        "cons": ["Desprecia la vida cortesana y los rodeos diplomáticos."],
        "tags": ["militar", "frontera", "disciplina"],
    },
    {
        "id": "pj_dama_isolda",
        "nombre": "Isolda de Arvenia",
        "titulo": "Dama de la Casa Real",
        "descripcion": "Prima del rey y memoria viva de los linajes; maneja genealogías, dotes y rencores.",
        "pros": ["Anticipa los movimientos de la nobleza.", "Sabe qué boda evita una guerra."],
        "cons": ["Nunca olvida una ofensa y cobra cada favor."],
        "tags": ["nobleza", "intriga", "linaje"],
    },
    {
        "id": "pj_maestre_otton",
        "nombre": "Maestre Otton",
        "titulo": "Maestre de la Casa de la Moneda",
        "descripcion": "Contador meticuloso que vigila el peso de cada moneda y el humor de cada gremio.",
        "pros": ["Detecta fraudes y recupera fondos perdidos.", "Negocia con los gremios sin perder la calma."],
        "cons": ["Su celo auditor enfurece a los nobles acostumbrados al margen."],
        "tags": ["oro", "comercio", "cuentas"],
    },
    {
        "id": "pj_hermana_clara",
        "nombre": "Hermana Clara",
        "titulo": "Sanadora del Claustro",
        "descripcion": "Herborista del claustro, respetada por el pueblo y escuchada por el obispo.",
        "pros": ["Contiene brotes de enfermedad en los barrios.", "Media entre la corona y las parroquias."],
        "cons": ["Se niega a bendecir guerras o ejecuciones públicas."],
        "tags": ["fe", "pueblo", "salud"],
    },
    {
        "id": "pj_embajador_ilirio",
        "nombre": "Cassio de Iliria",
        "titulo": "Embajador del Reino de Iliria",
        "descripcion": "Diplomático elegante y paciente que ofrece tratados, comercio y una amistad interesada.",
        "pros": ["Abre rutas comerciales y mediaciones ventajosas.", "Conoce la política de las cortes vecinas."],
        "cons": ["Sus favores siempre esconden una cláusula secreta."],
        "tags": ["diplomacia", "iliria", "comercio"],
    },
]


def construir_eventos_extra() -> List[EventoV2GrafoSchema]:
    """Devuelve los 24 eventos adicionales, ya validados por el esquema V2."""
    importados = [EventoV2GrafoSchema(**doc) for doc in json.loads(DATA_V2C.read_text(encoding="utf-8"))]
    propios = [_evento(spec) for spec in EVENTOS_NUEVOS]
    return propios + importados


def construir_cartas() -> List[Dict[str, Any]]:
    return [
        CartaCreateRequest(
            _id=spec["id"],
            universo_id=UNIVERSO_ID,
            categoria=spec["categoria"],
            nombre=spec["nombre"],
            descripcion=spec["descripcion"],
            imagen=IMAGEN_CARTA,
            tags=spec["tags"],
        ).model_dump(by_alias=True)
        for spec in CARTAS_NUEVAS
    ]


def construir_personajes() -> List[Dict[str, Any]]:
    return [
        PersonajeCreateRequest(
            _id=spec["id"],
            universo_id=UNIVERSO_ID,
            nombre=spec["nombre"],
            titulo=spec["titulo"],
            descripcion=spec["descripcion"],
            imagen=IMAGEN_PERSONAJE,
            pros=spec["pros"],
            cons=spec["cons"],
            tags=spec["tags"],
        ).model_dump(by_alias=True)
        for spec in PERSONAJES_NUEVOS
    ]
