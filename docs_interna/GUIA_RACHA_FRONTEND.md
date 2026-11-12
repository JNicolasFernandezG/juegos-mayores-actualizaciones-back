# Racha diaria — contrato para el frontend

Estado: **backend listo; el frontend todavía no la consume**. El valor existe en `GET /api/economy/me` y `GET /api/auth/session`, pero el header sigue mostrando el snapshot local de `usuario`.

Desde el 2026-11-11 la racha mide **ingresos a la aplicación**, no desafíos completados. No se hizo backfill: la racha arranca de cero para todos.

---

## 1. Qué expone el backend

`GET /api/economy/me` (acepta Bearer o cookie HttpOnly) registra el ingreso del día y agrega tres campos:

```json
{
  "user_id": 42,
  "vidas": 5,
  "puntos": 1090,
  "racha": 4,
  "racha_ultima_fecha": "2026-11-11",
  "racha_hoy_ingresada": true,
  "suscripcion": "basica",
  "dias_desbloqueados": [],
  "costo_pista_puntos": 20
}
```

`GET /api/auth/session` hace lo mismo y devuelve los mismos tres campos junto al `user`:

```json
{
  "success": true,
  "authenticated": true,
  "user": { "...": "..." },
  "racha": 4,
  "racha_ultima_fecha": "2026-11-11",
  "racha_hoy_ingresada": true
}
```

| Campo | Tipo | Significado |
|---|---|---|
| `racha` | `int` | Días consecutivos con al menos un ingreso autenticado. `1` en el primer ingreso del día. |
| `racha_ultima_fecha` | `string \| null` | Último día con ingreso registrado (`YYYY-MM-DD`). `null` si nunca ingresó. |
| `racha_hoy_ingresada` | `bool` | `true` si ya registró el ingreso de hoy (zona ART). |

El cálculo está en [app/shared/streak.py](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/shared/streak.py#L49) sobre la colección `user_presence`, y se expone desde [lives.py](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/economy/lives.py#L52) y [router.py del auth](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/auth/router.py#L64). El schema está en [schemas.py](file:///C:/Users/nmonti/Desktop/proyectos/backend/mayores_actualizacionesSIPI-BACK/app/features/economy/schemas.py#L155).

---

## 2. Semántica

- **Un día cuenta una sola vez**, sin importar cuántas veces abra la app, cuántas pestañas o cuántas peticiones haga.
- **No manda un contador el cliente**: el backend guarda un documento por usuario y día (`user_presence`) y deriva la racha. No se puede inflar desde el front.
- **Primer ingreso del día = +1 día**. Repetir el ingreso el mismo día no suma.
- **Día salteado = racha cortada**: al volver después de un día sin abrir, la racha arranca en `1`.
- **Zona horaria**: el "hoy" es `America/Argentina/Buenos_Aires`; el día cambia a las **00:00 ART**.
- **Sesión persistente**: funciona igual con cookie HttpOnly que con Bearer. No hace falta que el usuario vuelva a escribir credenciales.
- **Leer la economía cuenta como ingreso**: si el front consulta `/api/economy/me` en el arranque, la apertura ya queda registrada. Lo mismo con `/api/auth/session`.
- **Completar desafíos no suma racha por sí mismo**. Esa señal dejó de usarse el 2026-11-11; lo que cuenta es el ingreso del día, que `POST /api/games/attempts` registra si aún no existía.
- **Invitados**: siguen con el valor local del front; no hay racha en servidor.

---

## 3. Qué NO cambia

- `POST /api/games/attempts` sigue tomando `user_id` de la sesión y **no devuelve `racha`**.
- No hay endpoint nuevo para jugar: el bonus se aplica dentro del mismo `POST /api/games/attempts`.
- `racha_hoy_jugada` **se reemplazó** por `racha_hoy_ingresada`; el nombre viejo ya no se devuelve.

---

## 4. Acciones en el frontend

Hoy `recargarEconomia` lee `/api/economy/me` pero descarta la racha, y el header lee un campo que nadie actualiza.

1. **Arranque con sesión persistida**: llamar `GET /api/auth/session` una vez al abrir la app. Es el camino que funciona cuando el token ya no está en `localStorage` pero la cookie HttpOnly sigue vigente. Alternativa: mantener el `GET /api/economy/me` actual del montaje.
2. **Estado**: agregar `racha` (y opcionalmente `rachaHoyIngresada`) a `PlayerEconomyState` en [playerEconomySlice.ts](file:///C:/Users/nmonti/Desktop/proyectos/frontend/src/store/playerEconomySlice.ts#L30), con default `0`.
3. **Dispatch**: en [PlayerEconomyContext.tsx:143](file:///C:/Users/nmonti/Desktop/proyectos/frontend/src/context/PlayerEconomyContext.tsx#L143), sumar `racha: userData.racha` y `rachaHoyIngresada: userData.racha_hoy_ingresada` al `actualizarEconomia`.
4. **Snapshot**: en [PlayerEconomyContext.tsx:148](file:///C:/Users/nmonti/Desktop/proyectos/frontend/src/context/PlayerEconomyContext.tsx#L148), copiar también `u.racha = userData.racha` (y `u.racha_hoy_ingresada`) antes de reescribir `localStorage`.
5. **Header**: [LoginHeader.tsx:249](file:///C:/Users/nmonti/Desktop/proyectos/frontend/src/VISTAS/LOGIN/LoginHeader.tsx#L249) muestra `usuario.racha ?? 1`. Dos opciones:
   - dejar que lea del snapshot y actualizar el snapshot como en el paso 4, o
   - leer `racha` del contexto de economía, que es la fuente sincronizada.
6. **Cero**: el `?? 1` actual convierte `racha: 0` en `1`. Con el valor real, definir si se muestra `0` o se oculta el ícono de llama; no mostrar `1` cuando la racha está cortada.

### Flujo esperado

```
Apertura de la app con sesión
  → GET /api/auth/session (o GET /api/economy/me)
  → backend registra user_presence del día y deriva la racha
  → front dispatch racha → header actualizado
```

---

## 5. Verificación rápida

```bash
curl -s http://localhost:8090/api/economy/me \
  -H "Authorization: Bearer <token>"
```

Casos para probar desde el front:

| Escenario | `racha` | `racha_hoy_ingresada` | `racha_ultima_fecha` |
|---|---|---|---|
| Usuario nuevo, primer arranque | `1` | `true` | hoy |
| Segundo arranque el mismo día | `1` | `true` | hoy |
| Ingresó ayer y hoy | `2` | `true` | hoy |
| No ingresó ayer, vuelve hoy | `1` | `true` | hoy |
| Dos pestañas a la vez | `1` | `true` | hoy |
| Completar un desafío sin haber ingresado antes hoy | `+1` (igual que abrir la app) | `true` | hoy |

---

## 6. Puntos por racha (implementado, sin trabajo en el front)

El operador configura tramos de racha (`bonus_racha` en `GET /api/economy/config`, editable por `PUT /api/admin/economy/config`) y el backend acredita el boost al completar un desafío diario, usando el ledger idempotente existente.

- **Porcentaje** (`modo: "porcentaje"`): `puntos_base * valor // 100`; **puntos fijos** (`modo: "puntos_fijos"`): `valor` puntos.
- Se aplica solo el tramo de mayor `dias` alcanzado; Wordle, Sudoku, Sopa y Crucigrama; el narrativo no lo recibe.
- `POST /api/games/attempts` agrega `bonus_racha_puntos` y `bonus_racha_dias`; `puntos_ganados` ya incluye el boost. El replay sigue en `puntos_ganados: 0`.
- El front no cambia: sigue leyendo `puntos_ganados`/`puntos_totales_usuario` del intento y `puntos`/`racha` de `/api/economy/me`. La racha que decide el tramo incluye el ingreso del día que se registra al completar el desafío.
