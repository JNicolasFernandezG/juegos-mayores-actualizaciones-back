"""Pipeline de agregación MongoDB para el resumen de perfil."""

from typing import Any, Dict, List

from app.shared.clock import ART

JUEGOS_CON_MEDALLAS = ("wordle", "sopa_letras", "sudoku", "crucigrama")
CALIFICACIONES = ("S", "A", "B", "C", "F")
ESTADOS_TERMINADOS = ("completed", "won", "failed")
ESTADOS_COMPLETADOS = ("completed", "won")


def _condicion_tiempo_valido() -> Dict[str, Any]:
    return {
        "$and": [
            {"$in": ["$status", list(ESTADOS_COMPLETADOS)]},
            {"$ne": [{"$ifNull": ["$time_taken_seconds", None]}, None]},
        ]
    }


def _fecha_de_juego() -> Dict[str, Any]:
    """Día ART del cierre del intento; cae a updated_at/created_at/date si falta."""
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


def _group_medallas() -> Dict[str, Any]:
    return {
        "$group": {
            "_id": {"juego": "$game_id", "grade": "$grade"},
            "n": {"$sum": 1},
        }
    }


def _suma_completadas() -> Dict[str, Any]:
    return {"$sum": {"$cond": [{"$in": ["$status", list(ESTADOS_COMPLETADOS)]}, 1, 0]}}


def _pipeline_resumen(
    user_id: int,
    inicio_mes: str,
    fin_mes: str,
    inicio_ventana: str,
    desde: str,
    hasta: str,
) -> List[Dict[str, Any]]:
    """Construye el pipeline $facet para medallas, rendimiento y actividad diaria."""
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
                    _group_medallas(),
                ],
                "historico": [_group_medallas()],
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
                            "completadas": _suma_completadas(),
                            "mejor_tiempo": {
                                "$min": {"$cond": [tiempo_valido, "$time_taken_seconds", None]}
                            },
                            "promedio_tiempo": {
                                "$avg": {"$cond": [tiempo_valido, "$time_taken_seconds", None]}
                            },
                            "ultima_fecha": {"$max": "$_fecha_juego"},
                        }
                    }
                ],
                "por_dia": [
                    {"$match": {"_fecha_juego": {"$gte": desde, "$lte": hasta}}},
                    {"$group": {"_id": "$_fecha_juego", "n": _suma_completadas()}},
                ],
            }
        },
    ]
