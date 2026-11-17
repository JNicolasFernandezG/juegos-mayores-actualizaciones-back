"""Racha de días consecutivos en que el usuario abrió la aplicación con sesión válida.

La racha se deriva de ``user_presence`` y no se guarda como contador: así no se
desincroniza por ingresos repetidos el mismo día, varias pestañas ni correcciones
posteriores. El día se decide en zona ART, igual que los desafíos diarios.

Si un día pasa sin ingreso la racha se corta y el próximo ingreso vuelve al día 1.
Cada día de ingreso acredita puntos según ``app.shared.streak_rewards``, una sola
vez por día gracias a la idempotencia del ledger.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.shared.clock import now_utc, today_art
from app.shared.ledger import LedgerKey, get_points_ledger
from app.shared.streak_rewards import puntos_por_dia_de_racha

logger = logging.getLogger("Streak")

PRESENCE_COLLECTION = "user_presence"
MOTIVO_RACHA_DIARIA = "racha_diaria"


@dataclass(frozen=True)
class Racha:
    actual: int
    ultima_fecha: Optional[str]
    hoy_ingresada: bool
    # Puntos diarios del día de racha en que está el usuario (el 1 si aún no tiene racha).
    puntos_dia: int = 0


async def registrar_ingreso(user_id: int, *, hoy: Optional[date] = None) -> None:
    """Registra el ingreso del día una sola vez, sin importar cuántas veces se llame.

    La identidad ya está validada por el servidor (cookie o Bearer); acá solo se
    deja constancia de que el usuario abrió la aplicación en la fecha ART actual.
    """
    fecha = (hoy or today_art()).isoformat()
    ahora = now_utc()
    try:
        await get_database()[PRESENCE_COLLECTION].update_one(
            {"user_id": int(user_id), "date": fecha},
            {
                "$setOnInsert": {"first_seen_at": ahora},
                "$set": {"last_seen_at": ahora},
            },
            upsert=True,
        )
    except DuplicateKeyError:
        # Dos pestañas abriendo a la vez: la otra ya insertó el día.
        pass


async def calcular_racha(user_id: int, *, hoy: Optional[date] = None) -> Racha:
    """Cuenta los días consecutivos de ingreso hacia atrás desde hoy o ayer (ART)."""
    hoy = hoy or today_art()
    ayer = hoy - timedelta(days=1)

    cursor = get_database()[PRESENCE_COLLECTION].find(
        {
            "user_id": int(user_id),
            "date": {"$lte": hoy.isoformat()},
        },
        {"_id": 0, "date": 1},
    ).sort("date", -1)

    ultima_fecha: Optional[str] = None
    esperada: Optional[date] = None
    actual = 0

    async for doc in cursor:
        fecha_str = doc.get("date")
        if not isinstance(fecha_str, str):
            continue
        try:
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            continue

        if ultima_fecha is None:
            ultima_fecha = fecha_str
            # Si el último ingreso es anterior a ayer, la racha ya se cortó.
            if fecha == hoy:
                esperada = hoy
            elif fecha == ayer:
                esperada = ayer
            else:
                break

        if fecha != esperada:
            break

        actual += 1
        esperada -= timedelta(days=1)

    return Racha(
        actual=actual,
        ultima_fecha=ultima_fecha,
        hoy_ingresada=ultima_fecha == hoy.isoformat(),
        puntos_dia=puntos_por_dia_de_racha(max(actual, 1)),
    )


async def _acreditar_puntos_del_dia(user_id: int, racha: Racha, fecha: date) -> None:
    """Suma los puntos del día de racha; reintentos el mismo día no vuelven a sumar."""
    if not racha.hoy_ingresada or racha.actual <= 0:
        return
    puntos = puntos_por_dia_de_racha(racha.actual)
    if puntos <= 0:
        return
    try:
        resultado = await get_points_ledger().credit(
            LedgerKey(
                user_id=int(user_id),
                motivo=MOTIVO_RACHA_DIARIA,
                game_id="login",
                date=fecha.isoformat(),
            ),
            puntos,
            metadata={"racha_dias": racha.actual, "date": fecha.isoformat()},
        )
        if resultado.applied:
            logger.info(f"[RACHA] Usuario {user_id} ganó {puntos} pts por el día {racha.actual} de racha.")
    except Exception as e:
        # Un fallo del ledger no debe impedir abrir la app ni calcular la racha.
        logger.warning(f"No se pudieron acreditar los puntos de racha de {user_id}: {e}")


async def registrar_ingreso_y_racha(user_id: int, *, hoy: Optional[date] = None) -> Racha:
    """Registra la apertura del día, acredita sus puntos y devuelve la racha actualizada."""
    fecha = hoy or today_art()
    await registrar_ingreso(user_id, hoy=fecha)
    racha = await calcular_racha(user_id, hoy=fecha)
    await _acreditar_puntos_del_dia(user_id, racha, fecha)
    return racha
