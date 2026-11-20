"""Resumen del perfil: medallas, rendimiento y actividad del propio jugador.

Todo sale de un único aggregate sobre ``user_attempts`` (matched por ``user_id``,
cubierto por el índice existente) más una lectura acotada de ``user_presence``.

Las medallas y los conteos por día se atribuyen al día ART en que se cerró el
intento, no a la fecha del desafío resuelto: un desafío de octubre jugado en
noviembre suma para noviembre.
"""

import calendar
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.core.database import get_database
from app.shared.clock import today_art

from .aggregation import (  # noqa: F401
    CALIFICACIONES,
    ESTADOS_COMPLETADOS,
    ESTADOS_TERMINADOS,
    JUEGOS_CON_MEDALLAS,
    _condicion_tiempo_valido,
    _fecha_de_juego,
    _pipeline_resumen,
)
from .consejos import consejos_para_perfil
from .schemas import (
    MedallasBloque,
    MedallasMes,
    PerfilResumenResponse,
    PeriodoPerfil,
    RendimientoJuego,
)

VENTANA_ACTIVIDAD_DIAS = 84
VENTANA_MESES_MEDALLAS = 12


def _bloque_de_medallas() -> Dict[str, Dict[str, int]]:
    return {
        juego: {calificacion: 0 for calificacion in CALIFICACIONES}
        for juego in JUEGOS_CON_MEDALLAS
    }


def _volcar_conteos(filas: List[Dict[str, Any]], destino: Dict[str, Dict[str, int]]) -> None:
    for fila in filas:
        clave = fila.get("_id") or {}
        juego, calificacion = clave.get("juego"), clave.get("grade")
        if juego in destino and calificacion in CALIFICACIONES:
            destino[juego][calificacion] = int(fila.get("n", 0))


def _volcar_por_mes(
    filas: List[Dict[str, Any]], destino: Dict[str, Dict[str, Dict[str, int]]]
) -> None:
    for fila in filas:
        clave = fila.get("_id") or {}
        mes, juego, calificacion = clave.get("mes"), clave.get("juego"), clave.get("grade")
        if not isinstance(mes, str) or len(mes) != 7:
            continue
        if juego not in JUEGOS_CON_MEDALLAS or calificacion not in CALIFICACIONES:
            continue
        destino.setdefault(mes, _bloque_de_medallas())[juego][calificacion] = int(fila.get("n", 0))


def _rendimiento_vacio() -> Dict[str, RendimientoJuego]:
    return {juego: RendimientoJuego() for juego in JUEGOS_CON_MEDALLAS}


def _entero_o_nulo(valor: Optional[float]) -> Optional[int]:
    return None if valor is None else int(round(float(valor)))


def _volcar_rendimiento(
    filas: List[Dict[str, Any]], destino: Dict[str, RendimientoJuego]
) -> None:
    for fila in filas:
        juego = fila.get("_id")
        if juego not in destino:
            continue
        destino[juego] = RendimientoJuego(
            completadas=int(fila.get("completadas", 0)),
            mejor_tiempo_segundos=_entero_o_nulo(fila.get("mejor_tiempo")),
            promedio_tiempo_segundos=_entero_o_nulo(fila.get("promedio_tiempo")),
            ultima_fecha=fila.get("ultima_fecha"),
        )


def _completadas_por_dia(filas: List[Dict[str, Any]]) -> Dict[str, int]:
    completadas: Dict[str, int] = {}
    for fila in filas:
        fecha = fila.get("_id")
        cantidad = int(fila.get("n", 0))
        if isinstance(fecha, str) and cantidad > 0:
            completadas[fecha] = cantidad
    return completadas


def _month_date_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _periodo(hoy: date) -> tuple[PeriodoPerfil, str, str]:
    inicio_mes, fin_mes = _month_date_bounds(hoy.year, hoy.month)
    desde = hoy - timedelta(days=VENTANA_ACTIVIDAD_DIAS - 1)
    periodo = PeriodoPerfil(
        mes=f"{hoy.year:04d}-{hoy.month:02d}",
        desde=desde.isoformat(),
        hasta=hoy.isoformat(),
    )
    return periodo, inicio_mes, fin_mes


def _inicio_ventana_meses(hoy: date, cantidad: int) -> str:
    indice = hoy.year * 12 + (hoy.month - 1) - (cantidad - 1)
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}-01"


async def _actividad(db, user_id: int, periodo: PeriodoPerfil) -> List[str]:
    docs = await db["user_presence"].find(
        {"user_id": user_id, "date": {"$gte": periodo.desde, "$lte": periodo.hasta}},
        {"_id": 0, "date": 1},
    ).sort("date", 1).to_list(length=VENTANA_ACTIVIDAD_DIAS)
    return [doc["date"] for doc in docs if isinstance(doc.get("date"), str)]


async def obtener_resumen_de_perfil(
    user_id: int, *, hoy: Optional[date] = None
) -> PerfilResumenResponse:
    """Arma el resumen con una sola pasada de agregación por usuario."""
    fecha_hoy = hoy or today_art()
    periodo, inicio_mes, fin_mes = _periodo(fecha_hoy)
    inicio_ventana = _inicio_ventana_meses(fecha_hoy, VENTANA_MESES_MEDALLAS)
    db = get_database()

    pipeline = _pipeline_resumen(
        int(user_id), inicio_mes, fin_mes, inicio_ventana, periodo.desde, periodo.hasta
    )
    filas = await db["user_attempts"].aggregate(pipeline).to_list(length=1)
    facetas = filas[0] if filas else {}

    medallas_mes, medallas_historico = _bloque_de_medallas(), _bloque_de_medallas()
    _volcar_conteos(facetas.get("mes_actual", []), medallas_mes)
    _volcar_conteos(facetas.get("historico", []), medallas_historico)

    por_mes: Dict[str, Dict[str, Dict[str, int]]] = {periodo.mes: _bloque_de_medallas()}
    _volcar_por_mes(facetas.get("por_mes", []), por_mes)
    meses = [MedallasMes(mes=mes, juegos=por_mes[mes]) for mes in sorted(por_mes, reverse=True)]

    rendimiento = _rendimiento_vacio()
    _volcar_rendimiento(facetas.get("rendimiento", []), rendimiento)

    return PerfilResumenResponse(
        periodo=periodo,
        medallas=MedallasBloque(mes_actual=medallas_mes, historico=medallas_historico),
        meses=meses,
        rendimiento=rendimiento,
        actividad=await _actividad(db, int(user_id), periodo),
        completadas_por_dia=_completadas_por_dia(facetas.get("por_dia", [])),
        consejos=await consejos_para_perfil(),
    )
