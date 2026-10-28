# Análisis comparativo de payloads V1 vs V2 — Eventos y Conversaciones

> Comparación ejemplo a ejemplo de los JSON de request/response entre el motor
> clásico (V1, `event_director.py`) y el motor de grafos (V2, `graph_engine.py`).
> Los ejemplos usan IDs reales de los seeds `seed_narrative.py` (V1) y
> `seed_narrative_v2_graphs.py` (V2).

---

## 0. Contrato de ciclo (cómo se navega)

| | V1 (clásico) | V2 (grafos) |
|---|---|---|
| Evento | 2 requests → `elegir-carta-mes` + `decidir-evento` | N requests → `elegir-carta-mes` + `avanzar-nodo` × (profundidad) |
| Selección de opción | `decidir-evento {opcion_id}` (1 sola vez, resuelve todo) | `avanzar-nodo {opcion_id}` por cada nodo recorrido |
| Conversación | `responder-conversacion {opcion_numero:int}` | `avanzar-nodo {opcion_id:str}` (es un grafo) |
| Desenlaces | Expuestos como `probabilidades[].porcentaje` | **Ocultos** (anti-spoiler): solo ves el nodo que tocó |

---

## 1. EVENTO — Paso inicial (mismo endpoint, respuesta distinta)

`POST /api/narrative/v2/partida/elegir-carta-mes` → `{ date, carta_id }`

**V1 — `ElegirCartaMesV2Response` con `evento_actual` poblado:**

```jsonc
{
  "fase_actual": "toma_decision_evento",
  "recursos": { "oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50 },
  "evento_actual": {
    "id": "evt_helada_cosechas",
    "titulo": "La Gran Helada en el Valle",
    "descripcion": "Una ola de frío polar congeló los campos de trigo...",
    "imagen": "/assets/narrative/events/helada.webp",
    "opciones": [
      {
        "id": "op_a",
        "texto": "Enviar patrullas a custodiar y racionar graneros",
        "es_secreta": false,
        "bloqueada": false,
        "probabilidades": [
          { "resultado_id": "res_suministros_asegurados", "titulo": "Graneros Protegidos con Disciplina", "porcentaje": 66.7, "explicaciones": ["+35% por liderazgo del Comandante Marcus", "+15% por carretas organizadas"] },
          { "resultado_id": "res_emboscada_y_perdida", "titulo": "Patrulla Derrotada en el Camino", "porcentaje": 33.3, "explicaciones": [] }
        ]
      },
      {
        "id": "op_b",
        "texto": "Comprar grano de emergencia a mercaderes extranjeros",
        "es_secreta": false,
        "bloqueada": false,
        "probabilidades": [
          { "resultado_id": "res_grano_comprado_justo", "titulo": "Cargamentos de Trigo en Palacio", "porcentaje": 69.2, "explicaciones": ["+30% por negociación de la Canciller Elena"] },
          { "resultado_id": "res_estafa_mercaderes", "titulo": "Sacos de Arena y Grano Rancio", "porcentaje": 30.8, "explicaciones": [] }
        ]
      },
      {
        "id": "op_c",
        "texto": "[Secreto] Decretar requisa general amparado en el Sello Real",
        "es_secreta": true,
        "bloqueada": false,
        "probabilidades": [
          { "resultado_id": "res_cosecha_salvada_decreto", "titulo": "Decreto Real Acatado sin Resistencia", "porcentaje": 100.0, "explicaciones": [] }
        ]
      }
    ]
  },
  "finalizacion": null
}
```

**V2 — la MISMA `ElegirCartaMesV2Response`, pero con `grafo_actual` (y `evento_actual: null`):**

```jsonc
{
  "fase_actual": "toma_decision_evento",
  "recursos": { "oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50 },
  "evento_actual": null,
  "grafo_actual": {
    "fase_actual": "toma_decision_evento",
    "grafo_id": "evt_cometa_caido_v2",
    "tipo": "evento",
    "titulo": "El Cometa de la Frontera",
    "imagen": "/assets/narrative/eventos/default.webp",
    "nodo_actual": {
      "id": "nodo_avistamiento",
      "hablante_id": "narrador",
      "texto": "Una bola de fuego celestial surca el cielo nocturno y se estrella en los bosques del norte...",
      "imagen": null,
      "es_final": false,
      "opciones": [
        { "id": "opt_enviar_guardia", "texto": "Enviar a la guardia a acordonar la zona del cráter", "disponible": true, "motivo_bloqueo": null },
        { "id": "opt_enviar_alquimista", "texto": "Enviar a Vera la Alquimista a recolectar muestras del mineral", "disponible": true, "motivo_bloqueo": null }
      ],
      "resultado_texto": "",
      "impactos_recursos": [],
      "impactos_afinidad": [],
      "impactos_tags": []
    },
    "status": "CONTINUA"
  },
  "finalizacion": null
}
```

**Diff clave del paso 1:**

- V1 expone **los desenlaces y sus porcentajes** (`probabilidades[]`). V2 no: solo muestra las opciones sanitizadas (`id`, `texto`, `disponible`, `motivo_bloqueo`).
- V1 marca la opción secreta solo con `bloqueada`. V2, cuando la opción tiene `bloqueo_modo:"oculta"`, **se omite directamente** del array `opciones` (ver `to_cliente_schema`, `v2_graph_schemas.py:113`).

---

## 2. EVENTO — Resolución

**V1 — `POST .../decidir-evento` `{ date, opcion_id:"op_a" }`** (una sola llamada, todo resuelto):

```jsonc
// DecidirEventoV2Response
{
  "fase_actual": "balance_mes",           // ← o "resolver_conversacion" si tocó el 40%
  "recursos": { "oro": 50, "pueblo": 60, "ejercito": 50, "fe": 50 },
  "resultado_actual": {
    "_id": "res_suministros_asegurados",
    "universo_id": "corte_medieval",
    "titulo": "Graneros Protegidos con Disciplina",
    "texto": "Las patrullas de Marcus sellaron los silos...",
    "imagen": "/assets/narrative/resultados/default.webp",
    "tipo_resultado": "positivo",
    "efectos": [
      { "disparador": "al_obtener", "condiciones": [], "accion": { "tipo": "modificar_recurso", "clave": "pueblo", "valor": 10 } }
    ],
    "impacto_afinidad": [ { "personaje_id": "pj_comandante_marcus", "delta": 10 } ]
  },
  "conversacion_actual": null,            // ← ConversacionResponse si 40%
  "finalizacion": null
}
```

**V2 — `POST .../avanzar-nodo` `{ date, opcion_id }`**, paso intermedio primero:

```jsonc
// EstadoGrafoV2Response (nodo intermedio, es_final=false)
{
  "fase_actual": "toma_decision_evento",
  "grafo_id": "evt_cometa_caido_v2",
  "tipo": "evento",
  "titulo": "El Cometa de la Frontera",
  "imagen": "/assets/narrative/eventos/default.webp",
  "nodo_actual": {
    "id": "nodo_analisis_alquimico",
    "hablante_id": "pj_alquimista_vera",
    "texto": "Vera regresa fascinada: 'Majestad, la roca emite un calor perpetuo...'",
    "imagen": null,
    "es_final": false,
    "opciones": [
      { "id": "opt_financiar_laboratorio", "texto": "Financiar el laboratorio secreto de Vera con 15 de oro", "disponible": true, "motivo_bloqueo": null },
      { "id": "opt_donar_a_catedral", "texto": "Entregar la roca a la catedral...", "disponible": true, "motivo_bloqueo": null }
    ],
    "resultado_texto": "",
    "impactos_recursos": [],
    "impactos_afinidad": [],
    "impactos_tags": []
  },
  "status": "CONTINUA"
  // ⚠️ sin "afinidad" ni "recursos": todavía no hubo impacto
}
```

…y **cuando se llega al nodo terminal** (`opt_financiar_laboratorio` → `cierre_ciencia_cometa`):

```jsonc
// EstadoGrafoV2Response (nodo final, es_final=true)
{
  "fase_actual": "balance_mes",           // ← ya devuelto al ciclo, o encadena conversación/especial
  "grafo_id": "evt_cometa_caido_v2",
  "tipo": "evento",
  "titulo": "El Cometa de la Frontera",
  "imagen": "/assets/narrative/eventos/default.webp",
  "nodo_actual": {
    "id": "cierre_ciencia_cometa",
    "hablante_id": "narrador",
    "texto": "Vera destila esencias alquímicas puras...",
    "imagen": null,
    "es_final": true,
    "opciones": [],
    "resultado_texto": "El progreso científico trajo bienestar popular (-15 Oro, +20 Pueblo).",
    "impactos_recursos": [
      { "recurso": "oro", "delta": -15 },
      { "recurso": "pueblo", "delta": 20 }
    ],
    "impactos_afinidad": [
      { "personaje_id": "pj_alquimista_vera", "delta": 15 },
      { "personaje_id": "pj_canciller_elena", "delta": -10 }
    ],
    "impactos_tags": []
  },
  "afinidad": { "pj_alquimista_vera": 65, "pj_canciller_elena": 40 },
  "recursos": { "oro": 35, "pueblo": 70, "ejercito": 50, "fe": 50 },
  "status": "CONTINUA"
}
```

**Diff clave del paso 2:**

- V1 resuelve en **1 request**: el `resultado_actual` referencia un documento aparte (`narrative_results`) con `efectos` genéricos (`modificar_recurso`). Los impactos viven en esa colección.
- V2 resuelve en **N requests**; los impactos están **inline en el nodo terminal** (`impactos_recursos`/`impactos_afinidad`/`impactos_tags`). No existe colección de resultados.
- V1 devuelve `afinidad`/`recursos` **siempre** tras decidir; V2 solo los incluye (nullable) **en nodo final**. En nodo intermedio van ausentes.
- V2 el desenlace sorteado (cuando hay `desenlaces` ponderados) se revela **después** de aplicar: el cliente nunca ve `siguiente_nodo` ni `desenlaces`.

---

## 3. CONVERSACIÓN

**V1 — `POST .../responder-conversacion` `{ date, opcion_numero: 1 }`** (índice numérico):

```jsonc
// ResponderConversacionV2Response
{
  "fase_actual": "balance_mes",
  "afinidad": { "pj_comandante_marcus": 60, "pj_canciller_elena": 50 },
  "resultado_texto": "Asignas el oro a la guarnición. Marcus asiente; Elena anota el déficit.",
  "impacto_afinidad": [
    { "personaje_id": "pj_comandante_marcus", "delta": 10 },
    { "personaje_id": "pj_canciller_elena", "delta": -5 }
  ]
}
```

La conversación V1 venía serializada dentro de `DecidirEventoV2Response.conversacion_actual` como `ConversacionResponse`:

```jsonc
{
  "_id": "conv_disputa_tesoro_militar",
  "universo_id": "corte_medieval",
  "titulo": "Disputa por el Presupuesto de Campaña",
  "imagen": "/assets/narrative/conversaciones/default.webp",
  "requisitos": [
    { "personajeId": "pj_canciller_elena" },
    { "personajeId": "pj_comandante_marcus" }
  ],
  "frases": [
    { "personajeId": "pj_comandante_marcus", "texto": "Mis hombres necesitan mejores armaduras..." },
    { "personajeId": "pj_canciller_elena", "texto": "Si desviamos más oro a la guarnición..." }
  ],
  "decisiones": [
    { "opcion": 1, "texto": "Priorizar la defensa", "condiciones": [], "resultado_texto": "...", "impacto_afinidad": [ ... ] },
    { "opcion": 2, "texto": "Respaldar a Elena", "condiciones": [], "resultado_texto": "...", "impacto_afinidad": [ ... ] }
  ]
}
```

**V2 — `POST .../avanzar-nodo` `{ date, opcion_id:"opt_escuchar_marcus" }`** (es un grafo, mismo endpoint que el evento):

La conversación V2 (`conv_disputa_tesoro_militar_v2`) se inicia igual que un evento, devolviendo `EstadoGrafoV2Response` con `tipo:"conversacion"`:

```jsonc
{
  "fase_actual": "toma_decision_conversacion",
  "grafo_id": "conv_disputa_tesoro_militar_v2",
  "tipo": "conversacion",
  "titulo": "Disputa por el Presupuesto de Campaña",
  "imagen": "/assets/narrative/conversaciones/default.webp",
  "nodo_actual": {
    "id": "elena_intro",
    "hablante_id": "pj_canciller_elena",
    "texto": "Majestad, las arcas del reino están bajo una fuerte presión...",
    "imagen": null,
    "es_final": false,
    "opciones": [
      { "id": "opt_escuchar_marcus", "texto": "Escuchar la réplica del Comandante Marcus ➔", "disponible": true, "motivo_bloqueo": null }
    ],
    "resultado_texto": "",
    "impactos_recursos": [],
    "impactos_afinidad": [],
    "impactos_tags": []
  },
  "status": "CONTINUA"
}
```

…tras recorrer `marcus_planteo` → `marcus_detalles_estrategicos`, el nodo final:

```jsonc
{
  "fase_actual": "balance_mes",
  "grafo_id": "conv_disputa_tesoro_militar_v2",
  "tipo": "conversacion",
  "titulo": "Disputa por el Presupuesto de Campaña",
  "imagen": "/assets/narrative/conversaciones/default.webp",
  "nodo_actual": {
    "id": "cierre_fortificacion_total",
    "hablante_id": "pj_comandante_marcus",
    "texto": "Marcus golpea su coraza con orgullo: '¡La guardia no os fallará, Majestad!'...",
    "es_final": true,
    "opciones": [],
    "resultado_texto": "La frontera quedó fortificada...",
    "impactos_recursos": [ { "recurso": "oro", "delta": -20 }, { "recurso": "ejercito", "delta": 15 } ],
    "impactos_afinidad": [
      { "personaje_id": "pj_comandante_marcus", "delta": 15 },
      { "personaje_id": "pj_canciller_elena", "delta": -10 }
    ],
    "impactos_tags": []
  },
  "afinidad": { "pj_comandante_marcus": 65, "pj_canciller_elena": 40 },
  "recursos": { "oro": 30, "pueblo": 50, "ejercito": 65, "fe": 50 },
  "status": "CONTINUA"
}
```

**Diff clave del paso 3:**

- Selector: `opcion_numero: int` (posición `1..n`) en V1 vs `opcion_id: str` (ID semántico) en V2.
- V1: diálogo = `frases[]` (guión plano) + `decisiones[]` (respuestas numeradas); `requisitos` usa `{personajeId}`.
- V2: diálogo = **grafo** (`nodos{}` con `hablante_id` por paso); `requisitos` es un array plano de strings.
- V1 devuelve el efecto en un objeto aparte `ResponderConversacionV2Response{afinidad, resultado_texto, impacto_afinidad}`; V2 devuelve el mismo `EstadoGrafoV2Response` que un evento, con impactos inline y `afinidad`/`recursos` en el nodo final.

---

## Resumen

**V1 = one-shot con probabilidades expuestas y resultados en colección aparte**;
**V2 = recorrido por grafos anti-spoiler con impactos inline en nodos terminales, y un único endpoint `avanzar-nodo` para eventos y conversaciones por igual.**
