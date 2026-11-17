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
from app.shared.clock import ART, today_art

from .consejos import consejos_para_perfil
from .schemas import (
    MedallasBloque,
    MedallasMes,
    PerfilResumenResponse,
    PeriodoPerfil,
    RendimientoJuego,
)

JUEGOS_CON_MEDALLAS = ("wordle", "sopa_letras", "sudoku", "crucigrama")
CALIFICACIONES = ("S", "A", "B", "C", "F")
ESTADOS_TERMINADOS = ("completed", "won", "failed")
ESTADOS_COMPLETADOS = ("completed", "won")
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
        juego = clave.get("juego")
        calificacion = clave.get("grade")
        if juego in destino and calificacion in CALIFICACIONES:
            destino[juego][calificacion] = int(fila.get("n", 0))


def _volcar_por_mes(
    filas: List[Dict[str, Any]], destino: Dict[str, Dict[str, Dict[str, int]]]
) -> None:
    for fila in filas:
        clave = fila.get("_id") or {}
        mes = clave.get("mes")
        juego = clave.get("juego")
        calificacion = clave.get("grade")
        if not isinstance(mes, str) or len(mes) != 7:
            continue
        if juego not in JUEGOS_CON_MEDALLAS or calificacion not in CALIFICACIONES:
            continue
        bloque = destino.setdefault(mes, _bloque_de_medallas())
        bloque[juego][calificacion] = int(fila.get("n", 0))


def _rendimiento_vacio() -> Dict[str, RendimientoJuego]:
    return {juego: RendimientoJuego() for juego in JUEGOS_CON_MEDALLAS}


def _volcar_rendimiento(
    filas: List[Dict[str, Any]], destino: Dict[str, RendimientoJuego]
) -> None:
    for fila in filas:
        juego = fila.get("_id")
        if juego not in destino:
            continue
        promedio = fila.get("promedio_tiempo")
        destino[juego] = RendimientoJuego(
            completadas=int(fila.get("completadas", 0)),
            mejor_tiempo_segundos=_entero_o_nulo(fila.get("mejor_tiempo")),
            promedio_tiempo_segundos=_entero_o_nulo(promedio),
            ultima_fecha=fila.get("ultima_fecha"),
        )


def _entero_o_nulo(valor: Optional[float]) -> Optional[int]:
    if valor is None:
        return None
    return int(round(float(valor)))


def _condicion_tiempo_valido() -> Dict[str, Any]:
    return {
        "$and": [
            {"$in": ["$status", list(ESTADOS_COMPLETADOS)]},
            {"$ne": [{"$ifNull": ["$time_taken_seconds", None]}, None]},
        ]
    }


def _fecha_de_juego() -> Dict[str, Any]:
    """Día ART del cierre del intento: una partida de octubre jugada en noviembre cae en noviembre.

    ``completed_at`` lo escriben los flujos de guardado al cerrar el intento; los
    documentos previos caen a ``updated_at`` y, si tampoco lo tienen, a la fecha
    del desafío (única referencia disponible en el histórico viejo).
    """
    return {
        "$ifNull": [
            {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": {
                        "$convert": {
                            "input": {
                                "$ifNull": ["$completed_at", "$updated_at", "$created_at"]
                            },
                            "to": "date",
                            "onError": None,
                            "onNull": None,
                        }
                    },
                    "timezone": ART.key,
                    "onNull": None,
                }
            },
            "$date",
        ]
    }


def _completadas_por_dia(filas: List[Dict[str, Any]]) -> Dict[str, int]:
    completadas: Dict[str, int] = {}
    for fila in filas:
        fecha = fila.get("_id")
        cantidad = int(fila.get("n", 0))
        if isinstance(fecha, str) and cantidad > 0:
            completadas[fecha] = cantidad
    return completadas


def _pipeline_resumen(
    user_id: int,
    inicio_mes: str,
    fin_mes: str,
    inicio_ventana: str,
    desde: str,
    hasta: str,
) -> List[Dict[str, Any]]:
    tiempo_valido = _condicion_tiempo_valido()
    return [
        {
            "$match": {
                "user_id": user_id,
                "status": {"$in": list(ESTADOS_TERMINADOS)},
                "grade": {"$in": list(CALIFICACIONES)},
            }
        },
        {"$addFields": {"_fecha_juego": _fecha_de_juego()}},
        {
            "$facet": {
                "mes_actual": [
                    {"$match": {"_fecha_juego": {"$gte": inicio_mes, "$lte": fin_mes}}},
                    {
                        "$group": {
                            "_id": {"juego": "$game_id", "grade": "$grade"},
                            "n": {"$sum": 1},
                        }
                    },
                ],
                "historico": [
                    {
                        "$group": {
                            "_id": {"juego": "$game_id", "grade": "$grade"},
                            "n": {"$sum": 1},
                        }
                    }
                ],
                "por_mes": [
                    {"$match": {"_fecha_juego": {"$gte": inicio_ventana}}},
                    {
                        "$group": {
                            "_id": {
                                "mes": {"$substrBytes": ["$_fecha_juego", 0, 7]},
                                "juego": "$game_id",
                                "grade": "$grade",
                            },
                            "n": {"$sum": 1},
                        }
                    },
                ],
                "rendimiento": [
                    {
                        "$group": {
                            "_id": "$game_id",
                            "completadas": {
                                "$sum": {
                                    "$cond": [
                                        {"$in": ["$status", list(ESTADOS_COMPLETADOS)]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "mejor_tiempo": {
                                "$min": {
                                    "$cond": [tiempo_valido, "$time_taken_seconds", None]
                                }
                            },
                            "promedio_tiempo": {
                                "$avg": {
                                    "$cond": [tiempo_valido, "$time_taken_seconds", None]
                                }
                            },
                            "ultima_fecha": {"$max": "$_fecha_juego"},
                        }
                    }
                ],
                "por_dia": [
                    {"$match": {"_fecha_juego": {"$gte": desde, "$lte": hasta}}},
                    {
                        "$group": {
                            "_id": "$_fecha_juego",
                            "n": {
                                "$sum": {
                                    "$cond": [
                                        {"$in": ["$status", list(ESTADOS_COMPLETADOS)]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                ],
            }
        },
    ]


def _periodo(hoy: date) -> tuple[PeriodoPerfil, str, str]:
    inicio_mes = hoy.replace(day=1)
    fin_mes = hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])
    desde = hoy - timedelta(days=VENTANA_ACTIVIDAD_DIAS - 1)
    periodo = PeriodoPerfil(
        mes=f"{hoy.year:04d}-{hoy.month:02d}",
        desde=desde.isoformat(),
        hasta=hoy.isoformat(),
    )
    return periodo, inicio_mes.isoformat(), fin_mes.isoformat()


def _inicio_ventana_meses(hoy: date, cantidad: int) -> str:
    indice = hoy.year * 12 + (hoy.month - 1) - (cantidad - 1)
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}-01"


async def obtener_resumen_de_perfil(
    user_id: int, *, hoy: Optional[date] = None
) -> PerfilResumenResponse:
    """Arma el resumen con una sola pasada de agregación por usuario."""
    fecha_hoy = hoy or today_art()
    periodo, inicio_mes, fin_mes = _periodo(fecha_hoy)
    inicio_ventana = _inicio_ventana_meses(fecha_hoy, VENTANA_MESES_MEDALLAS)
    db = get_database()

    pipeline = _pipeline_resumen(
        int(user_id),
        inicio_mes,
        fin_mes,
        inicio_ventana,
        periodo.desde,
        periodo.hasta,
    )
    filas = await db["user_attempts"].aggregate(pipeline).to_list(length=1)
    facetas = filas[0] if filas else {}

    medallas_mes = _bloque_de_medallas()
    medallas_historico = _bloque_de_medallas()
    _volcar_conteos(facetas.get("mes_actual", []), medallas_mes)
    _volcar_conteos(facetas.get("historico", []), medallas_historico)

    por_mes: Dict[str, Dict[str, Dict[str, int]]] = {
        periodo.mes: _bloque_de_medallas()
    }
    _volcar_por_mes(facetas.get("por_mes", []), por_mes)
    meses = [
        MedallasMes(mes=mes, juegos=por_mes[mes]) for mes in sorted(por_mes, reverse=True)
    ]

    rendimiento = _rendimiento_vacio()
    _volcar_rendimiento(facetas.get("rendimiento", []), rendimiento)

    actividad = await _actividad(db, int(user_id), periodo)
    completadas_por_dia = _completadas_por_dia(facetas.get("por_dia", []))
    consejos = await consejos_para_perfil()

    return PerfilResumenResponse(
        periodo=periodo,
        medallas=MedallasBloque(
            mes_actual=medallas_mes,
            historico=medallas_historico,
        ),
        meses=meses,
        rendimiento=rendimiento,
        actividad=actividad,
        completadas_por_dia=completadas_por_dia,
        consejos=consejos,
    )


async def _actividad(db, user_id: int, periodo: PeriodoPerfil) -> List[str]:
    docs = await db["user_presence"].find(
        {
            "user_id": user_id,
            "date": {"$gte": periodo.desde, "$lte": periodo.hasta},
        },
        {"_id": 0, "date": 1},
    ).sort("date", 1).to_list(length=VENTANA_ACTIVIDAD_DIAS)

    return [doc["date"] for doc in docs if isinstance(doc.get("date"), str)]
