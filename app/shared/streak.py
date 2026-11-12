"""Racha de días consecutivos en que el usuario abrió la aplicación con sesión válida.

La racha se deriva de ``user_presence`` y no se guarda como contador: así no se
desincroniza por ingresos repetidos el mismo día, varias pestañas ni correcciones
posteriores. El día se decide en zona ART, igual que los desafíos diarios.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.shared.clock import now_utc, today_art

PRESENCE_COLLECTION = "user_presence"


@dataclass(frozen=True)
class Racha:
    actual: int
    ultima_fecha: Optional[str]
    hoy_ingresada: bool


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
    )


async def registrar_ingreso_y_racha(user_id: int, *, hoy: Optional[date] = None) -> Racha:
    """Registra la apertura del día y devuelve la racha ya actualizada."""
    fecha = hoy or today_art()
    await registrar_ingreso(user_id, hoy=fecha)
    return await calcular_racha(user_id, hoy=fecha)
