# KingsCourt — conversación encadenada y avance de mes

Documento de traspaso para el desarrollador del frontend del juego narrativo.
Base analizada: `origin/main` del repo frontend, commit `0b8e5ab`.
Backend: motor de grafos V2 (`/api/narrative/v2/partida/*`).

---

## 1. Síntoma reportado en producción

Al llegar a un mes intermedio de la partida, la pantalla muestra:

> El mes avanzó localmente, pero no se pudieron cargar las nuevas cartas.
> La partida no se encuentra en fase de balance mensual.

El error aparece de forma intermitente (no en todos los meses ni en todas las partidas) y la
partida, a nivel visual, queda un mes adelantada respecto del servidor.

---

## 2. Causa: el front descarta la conversación encadenada

El backend encadena un segundo grafo en dos casos:

- **Conversación incidental**: tras resolver un evento, con 40 % de probabilidad se sortea una
  conversación de corte (solo si no hay un evento especial pendiente).
- **Evento especial de afinidad**: cuando un personaje cruza un umbral de lealtad o traición.

En ambos casos, la respuesta de `POST /api/narrative/v2/partida/avanzar-nodo` cambia de fase a
`RESOLVER_CONVERSACION` y **agrega un bloque nuevo en el nivel superior**:
`conversacion_actual`. El `grafo_id`, `tipo`, `titulo` y `nodo_actual` siguen describiendo el
grafo que se acaba de resolver (el evento), porque el evento todavía tiene que mostrarse como
resultado.

### 2.1 Contrato observable real (nodo terminal que encadena)

```json
{
  "fase_actual": "RESOLVER_CONVERSACION",
  "grafo_id": "evt_cometa",
  "tipo": "evento",
  "titulo": "El cometa",
  "imagen": "/assets/narrative/eventos/default.webp",
  "nodo_actual": {
    "id": "opt_financiar",
    "hablante_id": "narrador",
    "texto": "Decidiste financiar la expedición.",
    "es_final": true,
    "opciones": [],
    "resultado_texto": "La corte respira aliviada.",
    "impactos_recursos": [{ "recurso": "oro", "delta": -10 }],
    "impactos_afinidad": [],
    "impactos_tags": []
  },
  "recursos": { "oro": 40, "pueblo": 50, "ejercito": 50, "fe": 50 },
  "afinidad": { "vera": 65 },
  "status": "CONTINUA",
  "conversacion_actual": {
    "_id": "conv_tesoro",
    "nodo_id": "avistamiento",
    "titulo": "El tesoro de la torre",
    "imagen": "/assets/narrative/conversaciones/default.webp",
    "requisitos": [{ "personajeId": "vera" }],
    "frases": [{ "personajeId": "vera", "texto": "Hay algo bajo la torre." }],
    "decisiones": [
      { "opcion": "opt_enviar_guardia", "texto": "Enviar la guardia", "resultado_texto": "", "impacto_afinidad": [] }
    ]
  }
}
```

Puntos clave:

| Campo | Valor cuando encadena | Valor cuando NO encadena |
| --- | --- | --- |
| `fase_actual` | `RESOLVER_CONVERSACION` | `BALANCE_MES` |
| `grafo_id` | El grafo resuelto (el evento), **no** el encadenado | El grafo resuelto |
| `conversacion_actual` | DTO del grafo encadenado (conversación **o** evento especial) | `null` |
| `nodo_actual.es_final` | `true` | `true` |

El DTO de `conversacion_actual` tiene la misma forma tanto si el grafo encadenado es una
conversación como si es un evento especial (`tipo` destino queda solo en el `grafo_activo`
interno del servidor).

Referencias backend:

- [app/features/narrative/game/motor_v2/graph_engine.py:638](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/narrative/game/motor_v2/graph_engine.py#L638)
  — disparo del evento especial pendiente y de la conversación incidental.
- [app/features/narrative/game/motor_v2/graph_engine.py:661](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/narrative/game/motor_v2/graph_engine.py#L661)
  — armado del DTO de `conversacion_actual` y actualización de `grafo_activo`.
- [app/features/narrative/game/motor_v2/graph_engine.py:706](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/narrative/game/motor_v2/graph_engine.py#L706)
  — respuesta final: mantiene `grafo_id` del grafo resuelto y agrega `conversacion_actual`.
- [app/features/narrative/schemas/v2_graph_schemas.py:240](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/narrative/schemas/v2_graph_schemas.py#L240)
  — definición del campo en el esquema.

### 2.2 Recorrido del bug en el front actual

1. `avanzarNodo` compara `grafo.grafo_id !== grafoAnteriorId`
   ([narrativeService.ts:347](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/narrativeService.ts#L347)).
   En el encadenamiento real ambos IDs son iguales (el evento), así que **no** se cumple la
   condición y no se vuelve a pedir `/estado`: se pasa la respuesta directo al adaptador.
2. `EstadoGrafoApi` no declara `conversacion_actual`
   ([narrativeService.ts:100](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/narrativeService.ts#L100)).
   El adaptador arma la base con `conversacion_actual: null` y la rama terminal
   ([narrativeService.ts:136](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/narrativeService.ts#L136))
   solo agrega `resultado_actual`: el diálogo encadenado se pierde.
3. `mostrarEstado`
   ([KingsCourt.tsx:171](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/KingsCourt.tsx#L171))
   entra por la rama de `resultado_actual`, pero encuentra `conversacion_actual` en `null`, así
   que no deja nada pendiente en `conversacionPendiente`.
4. Al continuar, `continuarTrasResultado`
   ([KingsCourt.tsx:298](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/KingsCourt.tsx#L298))
   llama directamente a `avanzarMes`.
5. `avanzarMes` despacha `avanzarMesLocal()` **antes** del POST
   ([KingsCourt.tsx:291](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/KingsCourt.tsx#L291)).
   El backend responde 400 porque la partida está en `RESOLVER_CONVERSACION`, y el jugador ve el
   error con el mes ya corrido localmente.

---

## 3. Solución mínima (front)

Dos líneas de cambio en `src/VISTAS/JUEGOS/NARRATIVO/narrativeService.ts`.

### 3.1 Declarar el campo en el tipo de la respuesta del grafo

```diff
 export interface EstadoGrafoApi {
   ...
   recursos?: Record<string, number> | null;
   afinidad?: Record<string, number> | null;
   finalizacion?: FinalizacionApi | null;
+  conversacion_actual?: ConversacionApi | null;
   status: string;
 }
```

### 3.2 Conservarlo en la rama terminal del adaptador

```diff
   if (nodo.es_final) return {
     ...base,
+    conversacion_actual: grafo.conversacion_actual ?? null,
     resultado_actual: {
       titulo: grafo.titulo, texto: [nodo.texto, nodo.resultado_texto].filter(Boolean).join('\n\n'),
       imagen, tipo_resultado: 'neutro',
       efectos: nodo.impactos_recursos.map(({ recurso, delta }) => ({ accion: { clave: recurso, valor: delta } })),
     },
   };
```

Con esto, `mostrarEstado` ya hace lo correcto sin tocar nada más: muestra el resultado y deja
`conversacionPendiente` cargado; `continuarTrasResultado` presenta el diálogo encadenado antes
de intentar cerrar el mes.

No hace falta modificar `avanzarNodo`: el adaptador recibe el mismo objeto de la respuesta
(`{ grafo_actual: grafo, fase_actual: grafo.fase_actual }`), por lo que lee
`grafo.conversacion_actual` directamente.

### 3.3 Refuerzo opcional de recuperación

Si `avanzarMes` falla, conviene reconciliar con el servidor en lugar de dejar el mes avanzado
solo en pantalla. `recuperarFase` ya existe
([KingsCourt.tsx:186](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/KingsCourt.tsx#L186)):

```diff
   const avanzarMes = async () => {
     dispatch(avanzarMesLocal());
     const data = await pedir(() => avisarAvanceMes(date), 'El mes avanzo localmente, pero no se pudieron cargar las nuevas cartas.');
-    if (data) await mostrarEstado(data);
+    if (data) await mostrarEstado(data);
+    else await recuperarFase();
   };
```

---

## 4. Cambio de backend ya aplicado (idempotencia)

Además del fix del front, se endureció `POST /api/narrative/v2/partida/avanzar-mes` para que un
**segundo POST después de un avance exitoso** no devuelva 400:

- Si la partida ya está en `DRAFT_MENSUAL`, responde `200` con el `mes_actual`, los `recursos`
  y las mismas 3 cartas del draft vigente.
- Si la partida ya está en `FINALIZADA`, responde `200` con la `finalizacion` ya calculada
  (`puntos_ganados` llega en `null` porque los puntos ya se acreditaron en el avance original;
  el cliente no debe volver a acreditar nada).
- Las fases de grafo (`TOMA_DECISION_EVENTO`, `RESOLVER_CONVERSACION`) siguen devolviendo `400`,
  porque ahí el avance de mes es realmente inválido.

Referencia: [app/features/narrative/game/transition_service.py:64](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/narrative/game/transition_service.py#L64).

Esto evita que un reintento del cliente (doble click, reintento tras timeout o una llamada
tardía de StrictMode) destruya una partida válida. **No reemplaza el fix del front**: con el
front actual el jugador igual se salta la conversación encadenada y sufre un desfase de pantalla.

---

## 5. Tests del front

### 5.1 El test existente no reproduce el contrato real

`narrativeGraphs.test.ts:110` (`recupera recursos y afinidades cuando el backend encadena una
conversación u otro evento`) mockea el primer POST con un grafo cuyo `grafo_id` es
`conv_tesoro` (el encadenado), mientras que el `grafoAnteriorId` es `evt_cometa`. Como los IDs
difieren, el test cae en la rama de re-fetch a `/estado` y nunca ejercita el caso real. Ese test
debería reescribirse para el contrato de la sección 2.1.

### 5.2 Test sugerido para el nodo terminal encadenado

```ts
it('conserva la conversación encadenada del nodo terminal sin volver a pedir /estado', async () => {
  const respuesta = {
    ...grafo({ fase_actual: 'RESOLVER_CONVERSACION' }),
    nodo_actual: {
      ...grafo().nodo_actual,
      id: 'opt_financiar',
      es_final: true,
      opciones: [],
      resultado_texto: 'La corte respira aliviada.',
    },
    conversacion_actual: {
      _id: 'conv_tesoro',
      nodo_id: 'avistamiento',
      titulo: 'El tesoro de la torre',
      imagen: '/assets/narrative/conversaciones/default.webp',
      requisitos: [{ personajeId: 'vera' }],
      frases: [{ personajeId: 'vera', texto: 'Hay algo bajo la torre.' }],
      decisiones: [{ opcion: 'opt_enviar_guardia', texto: 'Enviar la guardia', resultado_texto: '', impacto_afinidad: [] }],
    },
  };
  vi.mocked(fetch).mockResolvedValue(responder(respuesta));
  const api = await import('./narrativeService');

  const estado = await api.avanzarNodo(date, 'opt_financiar', 'evt_cometa');

  expect(estado.resultado_actual).not.toBeNull();
  expect(estado.conversacion_actual?._id).toBe('conv_tesoro');
  expect(fetch).toHaveBeenCalledTimes(1);
});
```

Además conviene un test de `mostrarEstado`/`continuarTrasResultado` que verifique que, con
resultado + `conversacion_actual`, no se llama a `avanzar-mes` hasta resolver el diálogo.

---

## 6. Recuperación tras F5

Mientras la partida está encadenada, el servidor mantiene el grafo encadenado como activo. Dos
lecturas permiten restaurar la pantalla:

- `GET /api/narrative/v2/partida/grafo-actual?date=YYYY-MM-DD` → devuelve el grafo activo
  (la conversación o el evento especial encadenado).
- `GET /api/narrative/v2/partida/estado?date=YYYY-MM-DD` → devuelve `grafo_actual` ya proyectado
  junto con `resultado_actual`.

El adaptador del front sabe reconstruir la conversación desde `grafo_actual` cuando el grafo
activo es de tipo `conversacion` y el nodo no es terminal (rama
[narrativeService.ts:144](file:///C:/Users/nmonti/Desktop/proyectos/frontend-main/src/VISTAS/JUEGOS/NARRATIVO/narrativeService.ts#L144)).
El caso que hoy falla es únicamente el de la **respuesta directa de `avanzar-nodo`** con nodo
terminal encadenado.

---

## 7. Contraste V1 / V2

- En V1 cada etapa se resolvía con endpoints separados (`responder-evento`,
  `responder-conversacion`) y el cliente sabía de antemano en qué pantalla estaba.
- En V2 evento y conversación comparten `avanzar-nodo`, y el servidor decide el encadenamiento
  en el mismo paso. Por eso el contrato de V2 agrega `conversacion_actual` en el nivel superior:
  es la señal de "todavía hay un grafo pendiente, no cierres el mes".
- El front actual (origin/main) ya soporta `conversacion_actual` en `EstadoPartida` y en
  `mostrarEstado`; lo único que falta es no descartarlo al adaptar la respuesta de
  `avanzar-nodo`.

---

## 8. Checklist de verificación

1. Partida nueva, mes 1. Resolver un evento que encadene conversación (o forzar afinidad de
   lealtad/traición).
2. Verificar que se muestra el resultado y, al continuar, la conversación — **sin** llamar a
   `avanzar-mes`.
3. Al terminar la conversación, recién ahí debe dispararse `avanzar-mes` y aparecer el draft del
   mes siguiente.
4. Repetir con un evento especial de afinidad.
5. Recargar (F5) en medio de la conversación encadenada: debe restaurarse.
6. Repetir `POST avanzar-mes` dos veces seguidas: la segunda responde 200 con el mismo draft.
