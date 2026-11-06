# Auditoría: desconexión del motor de grafos con el despachador de efectos

**Fecha:** 5 de noviembre de 2026
**Rama analizada:** `feature/refactor-backend`
**Commits auditados:** `01f7f74` (desacople catálogo acciones/frecuencias), `1ff7cff` (EfectosEditor dinámico), `b2ad889` (`mutar_estado` + `condiciones_aparicion`), `25f4774` (impactos de grafos con amortiguadores y triggers reactivos)
**Suite al momento de la auditoría:** 276 passed, 18 deselected
**Método:** lectura de los diffs `01f7f74..HEAD`, rastreo de todos los call sites de `despachar_efectos`, y 9 sondas sobre el motor de reglas (las sondas fueron temporales y no quedaron en el árbol).

---

## 1. Resumen ejecutivo

El desacople de **nombres** quedó hecho: las acciones y las frecuencias se leen de Mongo y el panel las ofrece en selectores dinámicos. El desacople de **semántica** no: el catálogo no manda sobre cuándo dispara un efecto, ni sobre cómo se aplica un impacto de grafo, y ninguna de las dos capas valida lo que escribe el operador.

El punto más grave es estructural y es lo que motiva este documento: **el nodo terminal de un grafo V2 aplica sus impactos de recursos con aritmética propia, copiada del motor de reglas, en vez de pasar por el despachador.** Eso implica que la primitiva más potente del sistema (`mutar_estado`) y el catálogo de acciones no tienen ninguna influencia sobre el resultado de los eventos, y que cada cambio futuro en la aritmética de recursos hay que hacerlo dos veces.

Ninguno de los 9 defectos de la auditoría anterior fue corregido en estos tres commits, y se introdujeron 6 nuevos (J–O en §5).

---

## 2. Los tres caminos que mutan el estado

Hoy existen tres lugares que modifican `run` durante una partida narradora, con semánticas distintas:

| Camino | Archivo | ¿Usa `rule_engine`? | ¿Recibe catálogos? |
|---|---|---|---|
| Efectos de cartas/personajes (setup, turnos, avance de mes) | `game/setup_service.py`, `game/turn_service.py`, `game/transition_service.py` | Sí | Sí (`catalogo_acciones`, `catalogo_frecuencias`, `duenio_id`, `mes_actual`) |
| Impactos del nodo terminal de grafo V2 | `game/motor_v2/graph_engine.py:435-460` | **No** — aritmética duplicada | **No** (los consulta recién en el paso 1.5) |
| Efectos del desenlace en V1 | `game/motor_v1/turn_service.py:182` | Sí | **No** (llamada de 4 argumentos) |

`ejecutar_accion` (`engine/rule_engine.py:179`) es la única función que conoce las 6 primitivas, los amortiguadores, los límites dinámicos y `mutar_estado`. El grafo y V1 no la invocan para su parte central.

---

## 3. La desconexión: grafo vs despachador

### 3.1 Qué dice el commit y qué hace el código

`25f4774` se titula "conectar impactos de grafos con amortiguadores pasivos, límites dinámicos y triggers reactivos". Lo que conecta es **una copia** del bloque de amortiguación y clamping:

- `engine/rule_engine.py:203-231` — `modificar_recurso`: amortigua pérdidas, aplica `limites` de la run con fallback al mapa del universo, `round()` → clamp → `int()`.
- `game/motor_v2/graph_engine.py:439-460` — mismo algoritmo, reescrito: clamp → `round()` → `int()` en orden inverso.

No hay un llamado a `ejecutar_accion` ni a `despachar_efectos` para los impactos del nodo. La duplicación funciona hoy por casualidad: `int(max(a, min(b, round(x))))` y `round(x)` → `max/min` → `int()` coinciden en casi todos los valores, pero no son la misma expresión y no tienen por qué seguir coincidiendo.

### 3.2 Consecuencia 1 — `mutar_estado` es invisible para los eventos

`mutar_estado` puede escribir sobre `recursos.*`, `limites.*.min`, `limites.*.max`, `afinidad.*` y `variables.*` con seis operaciones matemáticas. Ninguna de esas rutas es alcanzable desde un nodo de grafo, porque el nodo no pasa por el motor de reglas. Un evento narrado no puede mover una variable del universo, ni ampliar el techo de un recurso, ni aplicar un divisor.

El sentido inverso tampoco existe: los `impactos_recursos` de un nodo no pueden amortiguarse por una primitiva nueva que se agregue después en `rule_engine`, salvo que alguien recuerde copiar el bloque a `graph_engine`.

### 3.3 Consecuencia 2 — el disparo reactivo se apoya en una señal incompleta

`game/motor_v2/graph_engine.py:465`:

```python
net_delta = sum(imp.delta for imp in siguiente_nodo.impactos_recursos)
```

`net_delta` **sólo mira recursos**. Un nodo que sólo modifica afinidad o otorga tags produce `net_delta == 0` → `disparador_reactivo = None` → ningún efecto reactivo de cartas ni de corte se ejecuta, aunque la decisión del jugador haya sido claramente negativa o positiva.

Además el orden del pipeline está mal para el caso reactivo:

```
435  paso 1   aplica impactos de recursos
462  paso 1.5 dispara EN_EVENTO_POSITIVO / NEGATIVO   <-- acá
495  paso 2   aplica impactos de afinidad
503  paso 2.5 aplica impactos de tags
```

Cuando se evalúan las `condiciones` de los efectos reactivos, la afinidad y los tags del nodo **todavía no se aplicaron**. Una condición del tipo "si este evento me dejó enemistado con el canciller" o "si el reino perdió el tag `paz_interna`" lee el estado viejo, y el efecto dispara o no dispara según el mes anterior, no según la decisión que se está resolviendo.

### 3.4 Consecuencia 3 — dos formas de tratar un recurso que no está en la run

- Grafo (`:438`): `if rec_clave in recursos:` → un nodo que impacta una clave inexistente **no hace nada**, en silencio.
- `mutar_estado` (`:285-287`): `recursos[clave_rec] = int(round(nuevo_num))` → **crea la clave**.

La asimetría no es sólo estética: combined con `verificar_colapso_recursos` (`game/endings_service.py:38-42`), que itera *todos* los recursos contra su mínimo, una ruta mal escrita genera una clave con valor 0 y eso es derrota inmediata. Ver §5 J.

### 3.5 Consecuencia 4 — el catálogo de frecuencias no puede nombrar el evento reactivo

Aunque el grafo despacha `en_evento_positivo` / `en_evento_negativo`, `_frecuencia_coincide` (`engine/rule_engine.py:362-420`) **sólo consulta el catálogo dentro de dos ramas**:

```python
if disp_valor == "al_obtener":        # :388  consulta catalogo_frecuencias
if disp_valor in ("cada_mes", "inicio_mes"):  # :396 consulta catalogo_frecuencias
...
return False                          # :420 cualquier otro evento, incluido el reactivo
```

Es decir: una frecuencia configurada como `{"id": "tras_desastre", "evento_motor": "en_evento_negativo"}` **nunca dispara**. El único modo de que un efecto reactivo funcione es que el operador escriba como `frecuencia_id` la cadena literal `"en_evento_negativo"` (que coincide por el atajo legacy de `:378-381`), que es exactamente lo que el desacople prometía eliminar.

`EVENTOS_MOTOR` (`admin/actions_crud_service.py:82`) anuncia únicamente `al_obtener` e `inicio_mes`, así que el panel ni siquiera ofrece el evento que el motor sí dispara. `al_final_partida` existe en el enum y en `rules_catalog.py` pero ningún call site lo despacha jamás: una frecuencia con ese `evento_motor` se guarda bien y queda inerte para siempre.

### 3.6 Consecuencia 5 — V1 ve la misma carta distinto

`game/motor_v1/turn_service.py:182`:

```python
despachar_efectos(DisparadorEnum.AL_OBTENER, run, efectos_res, recursos_mapa)
```

Sin `catalogo_acciones`, sin `catalogo_frecuencias`, sin `duenio_id`, sin `mes_actual`. Sobre ese camino:

- Toda acción referenciada cae en el fallback `primitiva = accion_id` (`engine/rule_engine.py:171`) y sólo "funciona" si el id del catálogo coincide con el nombre de la primitiva. Los seeds actuales escriben `_id: "mutar_estado"` y `_id: "modificar_recurso"`, o sea **el catálogo es un espejo de las primitivas**: mientras así sea, el desacople no se prueba a sí mismo y los ids personalizados quedan sin cobertura.
- Toda frecuencia relativa cae en la rama `else` (`:417-418`), que cuenta desde el inicio de partida en vez de desde la adquisición.

Resultado: idéntica configuración de carta produce efectos distintos según el motor que la resuelva.

---

## 4. Hallazgos de la auditoría anterior: ninguno corregido

| # | Defecto | Estado | Evidencia |
|---|---|---|---|
| A | `accion_id` inexistente o desactivado → no-op silencioso, sin error ni log | Persiste | `engine/rule_engine.py:171` |
| B | Bypass hardcodeado: editar `mensual.cada` no cambia nada | Persiste | `engine/rule_engine.py:397` |
| C | `evento_motor` es `str` libre; un valor inválido se guarda y el efecto queda inerte | Persiste | `ItemFrecuenciaSchema` sin validación |
| D | Efecto sin `frecuencia_id` ni `disparador` se guarda y nunca dispara | Persiste | `engine/rule_engine.py:384` |
| E | `amortiguar_danio` apila modificadores sin dedupe por fuente | Persiste | `engine/rule_engine.py:268` |
| F | `parametros_requeridos` nunca se valida por el motor ni por el admin | Persiste | `CATALOGO_PRIMITIVAS` es decorativo |
| G | Mismo `_id` de acción en otro universo → `DuplicateKeyError` (HTTP 500, no 409) | Persiste | `admin/actions_crud_service.py:116` |
| H | GET `/frecuencias` escribe un documento default (contaminación por `universo_id` con typo) | Persiste | `admin/actions_crud_service.py:252` |
| I | Acción global (`universo_id: None`) invisible para cualquier universo | Persiste | `engine/catalog_loader.py:15` |

---

## 5. Hallazgos nuevos (J–O), con la evidencia de las sondas

**J. `mutar_estado` puede crear recursos fantasma y eso provoca derrota instantánea.**
Sonda: run con `recursos {oro: 50}` y acción `mutar_estado` con `ruta: "recursos.orro"`, `sumar`, `valor 0` → `run["recursos"]` termina con la clave `orro` en 0. `verificar_colapso_recursos` itera todos los recursos contra su mínimo (0 por defecto) y detecta un agotamiento; la partida se cierra por un recurso que no existe en ningún universo.
Código: `engine/rule_engine.py:285-287`, `engine/rule_engine.py:315` (escritura del recurso sin verificar que la clave exista en el mapa del universo). El panel permite este caso: `EfectosEditor.jsx:100` ofrece el tipo `manual` para la ruta.

**K. `"portador"` resuelve contra el id del dueño, aunque el dueño sea una carta.**
Sonda: `modificar_afinidad` con `destino` default (`"portador"` en `ParametrosAccionSchema`) despachada con `duenio_id="carta_escudo_real"` → `run["afinidad"]["carta_escudo_real"] == 60`.
Código: `engine/rule_engine.py:239` (`personaje_target = duenio_id`), call sites `game/setup_service.py:260` y `game/turn_service.py:79` (pasan id de carta). `mutar_estado` con `ruta: "afinidad.portador"` tiene el mismo comportamiento (`:344-345`).
Impacto: la afinidad contaminada entra a `_detectar_cruces_afinidad`, a los umbrales de lealtad/traición, a la condición `AFINIDAD_PERSONAJE` y a la respuesta que consume el frontend.

**L. El catálogo no puede definir frecuencias reactivas ni de fin de partida.** Detallado en §3.5. Sonda: frecuencia `{"id": "tras_desastre", "evento_motor": "en_evento_negativo"}` → el efecto no dispara; el mismo efecto con `frecuencia_id: "en_evento_negativo"` → dispara.

**M. Los eventos que sólo mueven afinidad o tags no disparan efectos reactivos.** Detallado en §3.3. Evidencia: `game/motor_v2/graph_engine.py:465`.

**N. Los límites dinámicos no tienen invariantes.**
Sonda: `mutar_estado` sobre `limites.pueblo.min` con `fijar 90` se acepta sin controles. Nada impide `min > max` ni valores fuera del rango del universo; en ese caso el reclamp (`:333-339`) `max(cur_min, min(cur_max, val))` devuelve `cur_min`, o sea **sube** el recurso. Combinado con `verificar_colapso_recursos`, una partida puede perderse con el recurso lleno, o volverse inviable de forma permanente, desde una sola acción mal escrita en el panel.

**O. El nodo terminal ahora hace N+1 consultas.** `game/motor_v2/graph_engine.py:463-493`: una consulta de catálogos + una por carta en mano + una por **cada** clave de `afinidad`, sin proyección de campos y sin cachear. Antes, resolver un nodo no leía cartas ni personajes. Nota: sobre la contaminación de K, ese loop itera también los ids de carta que quedaron en `afinidad`, con lo que las consultas fantasma se multiplican.

**P. `condiciones_aparicion` se degrada en silencio.** `game/setup_service.py:122-128`: el filtro de elegibles se descarta si quedan menos de 3 personajes o cartas (`if len(p_elegibles) >= 3`). Es decir, una condición de aparición del operador puede simplemente no respetarse sin ningún aviso, y el caso en que más importaría (pool chico, requisitos difíciles) es justamente el que se ignora. Además, en la evaluación previa al sorteo (`:110-128`) el estado se arma con `corte_activa: []` y `tags_activos: []`, así que cualquier condición por tag o por personaje es falsa en el setup.

---

## 6. Lo que sí quedó bien

- `mutar_estado` con `variables.*` es genuinamente extensible sin deploy: una variable nueva del universo no requiere código nuevo.
- Los límites dinámicos están conectados de punta a punta: `setup` siembra `run["limites"]` (`game/setup_service.py:232-235`), `modificar_recurso` reclama contra ellos, y el colapso usa el piso dinámico (`game/endings_service.py:38-42`).
- `run["limites"]` y `run["variables"]` se inicializan al crear la partida, lo que hace el estado explícito y proyectable.
- El `EfectosEditor` del panel lee ambos catálogos desde Mongo, arma el formulario según la primitiva elegida y compone la ruta desde selectores de recurso/limite/afinidad/variable; es el avance más concreto del lado operador.
- Los cuatro call sites V2 (setup, turno, avance de mes, grafo) ya pasan los catálogos completos al despachar.

---

## 7. Plan de cierre recomendado

Orden por relación impacto/riesgo. Nada de esto se implementó.

1. **Un único punto de aplicación para los impactos del grafo.** Convertir `impactos_recursos` / `impactos_afinidad` / `impactos_tags` del nodo en acciones del motor y resolverlas con `ejecutar_accion`, o en su defecto extraer una función compartida (`aplicar_delta_recurso`) que usen ambos. Borra la duplicación y hace que amortiguadores, límites y `mutar_estado` rijan también sobre los eventos. Es el cambio que más estructura.
2. **Corregir el orden y la señal del disparo reactivo.** Aplicar afinidad y tags **antes** del paso 1.5, y calcular `net_delta` incluyendo afinidad y tags (o definir explícitamente que los reactivos sólo miran recursos y documentarlo).
3. **Mover el match de frecuencia a `evento_motor` contra el catálogo** para cualquier valor, eliminar el atajo `("cada_mes", "mensual")` (`:397`) y sincronizar `EVENTOS_MOTOR` con los eventos que realmente despacha el motor. Decidir `al_final_partida`: se despacha o se saca del enum.
4. **Validar al salvar.** `guardar_item_catalogo` (`admin/crud_service.py:59-60`) hoy es un `replace_one` pelado: sin OCC y sin control semántico. Agregar validaciones de catálogo antes de persistir una carta/personaje: `accion_id` existente y activo, `frecuencia_id` existente, `ruta` dentro del whitelist y referenciando recursos del universo, `destino: portador` sólo en personajes, `min <= max` en límites, `evento_motor` en `EVENTOS_MOTOR`. Es la única forma de que el operador no pueda romper una partida desde el panel.
5. **Dedupe de amortiguadores** por `(fuente, clave)` guardando el máximo, no acumulando.
6. **V1**: o le pasa los catálogos a `despachar_efectos` en `game/motor_v1/turn_service.py:182`, o se retira formalmente. Es decisión de producto, no técnica.
7. G, H, I y el cacheo del catálogo por request.

---

## 8. Decisiones pendientes para el operador/producto

- Si los efectos reactivos deben existir como frecuencias configurables (implica el punto 3) o si `en_evento_positivo/negativo` quedan como eventos de código con ids literales. En ese caso hay que sacarlos de `rules_catalog.py` para que el panel no ofrezca algo inexistente.
- Si `al_final_partida` se despacha o se elimina del enum.
- Si un nodo de grafo puede crear un recurso que el universo no define (hoy el grafo dice que no, `mutar_estado` dice que sí).
- La semántica de `condiciones_aparicion` cuando el filtro deja menos de 3 candidatos: respetar la condición aunque el pool quede vacío, o mantener el fallback actual.
- El destino de V1 (decisión ya pendiente de `v2-replaces-v1-migration`).

---

## 9. Cómo reproducir

Las 9 sondas que produjeron §4 y §5 fueron temporales y **no quedaron en el repositorio** (se borraron antes de cerrar la auditoría; el working tree quedó limpio). Reconstruirlas es directo, todas son puras sobre `rule_engine`:

```python
from app.features.narrative.engine.rule_engine import despachar_efectos, ejecutar_accion
from app.features.narrative.schemas.rules_schemas import (
    EfectoSchema, AccionReferenciadaSchema, ParametrosAccionSchema,
)

# J: ruta inventada crea recurso fantasma
run = {"recursos": {"oro": 50}, "limites": {"oro": {"min": 0, "max": 100}}}
ejecutar_accion(
    AccionReferenciadaSchema(accion_id="mutar_estado",
        parametros=ParametrosAccionSchema(ruta="recursos.orro", valor=0)),
    run,
)
assert "orro" in run["recursos"]          # pasa → y eso es derrota por colapso

# K: portador contamina afinidad con un id de carta
run = {"afinidad": {"canciller": 50}}
despachar_efectos("al_obtener", run,
    [EfectoSchema(frecuencia_id="al_obtener",
        acciones=[AccionReferenciadaSchema(accion_id="modificar_afinidad",
                parametros=ParametrosAccionSchema(valor=10))])],
    duenio_id="carta_escudo_real")
assert "carta_escudo_real" in run["afinidad"]   # pasa

# L: frecuencia reactiva del catálogo es inerte
cat = {"tras_desastre": {"id": "tras_desastre", "evento_motor": "en_evento_negativo",
                         "cada": 1, "desfase": 0, "conteo_desde": "adquisicion", "activo": True}}
run = {"recursos": {"oro": 50}}
despachar_efectos("en_evento_negativo", run,
    [EfectoSchema(frecuencia_id="tras_desastre",
        acciones=[AccionReferenciadaSchema(accion_id="otorgar_tag",
                parametros=ParametrosAccionSchema(tag="marca"))])],
    catalogo_frecuencias=cat)
assert "marca" not in run.get("tags_activos", [])   # pasa → el catálogo no puede definir el evento

# B: el catálogo de frecuencias no manda
cat = {"mensual": {"id": "mensual", "evento_motor": "inicio_mes", "cada": 3,
                   "desfase": 0, "conteo_desde": "adquisicion", "activo": True}}
run = {"recursos": {"oro": 10}, "adquisiciones": {"carta_x": {"mes": 1, "tipo": "carta"}}}
ef = EfectoSchema(frecuencia_id="mensual",
    acciones=[AccionReferenciadaSchema(accion_id="modificar_recurso",
        parametros=ParametrosAccionSchema(clave="oro", valor=1))])
for mes in (2, 3, 4):
    despachar_efectos("cada_mes", run, [ef], duenio_id="carta_x",
                      mes_actual=mes, catalogo_frecuencias=cat)
assert run["recursos"]["oro"] == 13        # pasa → disparó 3 veces con cada=3 configurado

# E: amortiguadores apilados
run = {"recursos": {"pueblo": 100}, "modificadores_pasivos": []}
amort = AccionReferenciadaSchema(accion_id="amortiguar_danio",
    parametros=ParametrosAccionSchema(clave="pueblo", valor=50))
for _ in range(3):
    ejecutar_accion(amort, run, duenio_id="escudo")
ejecutar_accion(AccionReferenciadaSchema(accion_id="modificar_recurso",
    parametros=ParametrosAccionSchema(clave="pueblo", valor=-10)), run)
assert run["recursos"]["pueblo"] == 99     # pasa → 10 * 0.5^3 ≈ 1
```

Referencias de código citadas en este documento:

- `app/features/narrative/engine/rule_engine.py:171`, `:203-231`, `:239`, `:268`, `:285-287`, `:315`, `:333-339`, `:344-345`, `:362-420`
- `app/features/narrative/game/motor_v2/graph_engine.py:435-460`, `:462-493`, `:495-507`
- `app/features/narrative/game/motor_v1/turn_service.py:182`
- `app/features/narrative/game/endings_service.py:38-42`
- `app/features/narrative/game/setup_service.py:110-128`, `:232-235`, `:260`
- `app/features/narrative/game/turn_service.py:79`
- `app/features/narrative/admin/actions_crud_service.py:82`, `:116`, `:252`
- `app/features/narrative/admin/crud_service.py:59-60`
- `app/features/narrative/engine/catalog_loader.py:15`
- `frontend/admin_src/narrative/EfectosEditor.jsx:80-100`, `:218-236`

---

## 10. Cierre (2026-11-05): tramos 1-6 ejecutados

Estado de cada punto del plan de §7 y de la tabla A-I. Las líneas citadas arriba corresponden al estado *anterior* a estos cambios.

| Punto | Estado | Dónde quedó |
|---|---|---|
| 1. Único punto de aplicación de impactos | **Hecho** | `aplicar_delta_recurso` en `engine/rule_engine.py` es la única aritmética; `graph_engine` la llama para `impactos_recursos`. Amortiguadores, límites dinámicos y recursos inexistentes ahora rigen también en el grafo. |
| 2. Orden y señal del disparo reactivo | **Hecho** | Orden del nodo terminal: impactos -> afinidad -> tags -> efectos del desenlace -> reactivos -> `cruces_afinidad`. `_senal_desenlace` usa `NodoNarrativoSchema.tipo_desenlace` si el autor lo declaró y si no infiere por el balance de recursos (compatibilidad con contenido previo). |
| 3. Match de frecuencia gobernado por el catálogo | **Hecho** | `_frecuencia_coincide` resuelve `evento_motor` contra `catalogo_frecuencias`; se borró el bypass `("cada_mes", "mensual")`. Una frecuencia ausente del catálogo **no dispara**. `al_final_partida` quedó fuera de `rules_catalog` y de `EVENTOS_MOTOR`; se agregó `al_desenlace`. |
| 4. Validar al salvar | **Hecho** | `hallazgos_de_efectos` (`validation/graph_validator.py`) es el mismo control para grafos, cartas y personajes. `guardar_grafo_v2` y `guardar_item_con_efectos` (`admin/crud_service.py`) responden 422 con la lista de hallazgos. Códigos: `efecto_sin_evento`, `evento_no_despachado`, `efecto_sin_acciones`, `accion_sin_id`, `accion_desconocida`, `recurso_inexistente`, `afinidad_sin_personaje`. |
| 5. Dedupe de amortiguadores | **Hecho** (tramo 1) | Se conserva el máximo por `(fuente, clave)` en lugar de acumular. |
| 6. Destino de V1 | **En curso** | Retiro aprobado; la cobertura de contenido ya está sembrada (ver abajo), falta la eliminación de endpoints y motores. |

Hallazgos de la tabla A-I: **A, B, C, D, E, G, H quedaron corregidos**. G: `crear_accion` responde 409 nombrando el universo que ocupa el `_id`. H: el GET de frecuencias ya no escribe (devuelve defaults con `version=0`) y el upsert ahora guarda `universo_id`, sin lo cual el documento quedaba invisible para `obtener_catalogos_universo`. **I persiste** (acción global `universo_id: None` sigue siendo invisible por universo).

Hallazgos nuevos: **J corregido** (`aplicar_delta_recurso` y `mutar_estado` rechazan recursos que el universo no define; la validación también lo marca al salvar). **K, L, M, N, O y P sin cambios** — L y M quedaron resueltos de hecho por los puntos 2 y 3; N y P siguen abiertos y requieren decisión de semántica.

### Brecha de paridad V1/V2 cerrada: modificadores de probabilidad

Al medir el contenido real de dev se encontró que V1 expresa algo que V2 no podía: 24 de 60 `resultados_posibles` llevan `modificadores_probabilidad` (condiciones `tiene_personaje` / `tiene_tag` con `delta_peso`), y 12 opciones son `es_secreta`. Sin eso, cualquier conversión mecánica habría destruido balance escrito a mano.

- `DesenlaceNodoSchema.modificadores_probabilidad` (`schemas/v2_graph_schemas.py`), resuelto por `GraphTraversalEngine._pesos_desenlaces` reutilizando `evaluar_condicion`.
- El suelo se mantuvo en `0.0` (peso anulado = no se sortea), que es lo que ya garantizaba el test de caracterización `test_v2_peso_cero_no_se_sortea_y_terminal_conserva_perdidas_tags_y_cero`. V1 usa `0.1`; la diferencia es irrelevante y la coherencia interna pesa más. **Divergencia documentada, no corregida.**
- `bloqueo_modo: "oculta"` reproduce las opciones secretas de V1.

### Conversión de contenido V1 a grafos V2

`app/scripts/convertir_v1_a_v2.py` (no corre en el arranque; se ejecuta a mano, `--dry-run` primero, con `--universo`, `--suffix`, `--force`, `--eventos`, `--conversaciones`).

Antes, en dev: 12 eventos / 16 conversaciones V1 contra 7 / 6 V2 escritos a mano. Después de la conversión: 19 eventos y 22 conversaciones V2 (12 y 16 derivados con sufijo `_v2c`). Los ids derivados no pisan los grafos escritos a mano y la escritura es `$setOnInsert`, así que re-ejecutar no borra ediciones del operador.

El conversor valida cada grafo con la misma barrera del guardado: 28/28 aceptados, 0 rechazados. Un test unitario cubre la mecánica (`tests/unit/test_convertir_v1_a_v2.py`), incluida la trampa que detectó un bug real: las `condiciones` de las opciones secretas se estaban descartando, lo que habría dejado visibles 12 opciones ocultas.

### Efecto secundario útil de la barrera

`validar_grafos_almacenados` sobre dev (51 grafos) detectó uno injugable **escrito a mano antes de que existiera la barrera**: `evt_secta_cometa_v2` tiene el nodo `paso_8` marcado `es_final=True` con una opción que vuelve a `inicio_secta` (`nodo_final_con_opciones` + `ciclo_detectado`), y está referenciado como desenlace de `opt_asesinato_silencioso`. Es un stub de contenido incompleto; resolverlo significa escribir texto narrativo o eliminar la rama, así que queda como decisión de contenido y no se tocó.
