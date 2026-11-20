"""
endings_service.py
Gestión de desenlaces de partida (victoria en Mes 12 o derrota por colapso de recursos)
y fachada compatible hacia `settlement_service`.
"""

import logging
from typing import Any, Dict, Optional

from app.core.database import get_database
from app.features.narrative.constants import COLL_ENDINGS, COLL_SETTINGS
from app.features.narrative.enums import RunPhaseEnum, TipoFinalizacionEnum
from app.features.narrative.game.settlement_service import (
    ESTRELLAS_POR_RANGO,
    calificar_intento,
    estrellas_por_rango,
    registrar_intento_narrativo,
    sincronizar_intento_usuario,
)

logger = logging.getLogger(__name__)


async def _construir_epilogo_derrota(
    universo_id: Optional[str], recurso_agotado: str, mes_caida: int
) -> Dict[str, Any]:
    db = get_database()
    fin_doc = await db[COLL_ENDINGS].find_one({"universo_id": universo_id, "recurso_clave": recurso_agotado})
    universo_doc = await db[COLL_SETTINGS].find_one({"_id": universo_id})
    universo_nombre = universo_doc.get("nombre", universo_id) if universo_doc else universo_id
    recurso_meta = next(
        (r for r in universo_doc.get("recursos", []) if r.get("clave") == recurso_agotado), None
    ) if universo_doc else None
    recurso_nombre = recurso_meta.get("nombre", recurso_agotado.capitalize()) if recurso_meta else recurso_agotado.capitalize()

    if not fin_doc:
        fin_doc = {
            "_id": f"fin_{universo_id}_{recurso_agotado}_cero",
            "universo_id": universo_id,
            "recurso_clave": recurso_agotado,
            "tipo": TipoFinalizacionEnum.DERROTA_RECURSO.value,
            "titulo": f"Colapso por {recurso_nombre} ({universo_nombre})",
            "texto": f"El recurso '{recurso_nombre}' ha llegado a cero en {universo_nombre}, provocando el fin irreversible de tu partida.",
            "imagen": "/assets/narrative/finalizaciones/default.webp",
            "rango": "F",
        }
    return {
        "_id": fin_doc.get("_id"),
        "universo_id": universo_id,
        "recurso_clave": recurso_agotado,
        "tipo": fin_doc.get("tipo", TipoFinalizacionEnum.DERROTA_RECURSO.value),
        "titulo": fin_doc.get("titulo", f"Derrota en {universo_nombre}"),
        "texto": fin_doc.get("texto", ""),
        "imagen": fin_doc.get("imagen", "/assets/narrative/finalizaciones/default.webp"),
        "rango": fin_doc.get("rango", "F"),
        "mes_derrota": mes_caida,
    }


async def verificar_colapso_recursos(run_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Verifica si algún recurso vital llegó a <= su mínimo (0 por defecto).
    En tal caso, asocia la finalización correspondiente, marca 'game_over' y 'FINALIZADA'.
    """
    recursos = run_doc.get("recursos", {})
    limites = run_doc.get("limites", {})
    recurso_agotado = None
    for k, val in recursos.items():
        limite_min = float(limites[k]["min"]) if isinstance(limites.get(k), dict) and "min" in limites[k] else 0.0
        if val is not None and float(val) <= limite_min:
            recurso_agotado = k
            break

    if not recurso_agotado:
        return None

    finalizacion_data = await _construir_epilogo_derrota(
        run_doc.get("universo_id"), recurso_agotado, run_doc.get("mes_actual", 1)
    )
    run_doc["status"] = "game_over"
    run_doc["fase_actual"] = RunPhaseEnum.FINALIZADA.value
    run_doc["finalizacion"] = finalizacion_data
    return finalizacion_data


def calcular_finalizacion_victoria(
    run_data: Dict[str, Any],
    universo_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calcula el epílogo y rango de victoria (S, A, B, C) al sobrevivir los 12 meses."""
    recursos = run_data.get("recursos", {})
    promedio = sum(recursos.values()) / max(1, len(recursos))
    nombre_u = universo_doc.get("nombre", "este reino") if universo_doc else "este reino"
    universo_id = run_data.get("universo_id", "corte_medieval")

    if promedio >= 75:
        rango, titulo = "S", "Era Dorada y Prosperidad Suprema"
        texto = f"Tus sabias decisiones y admirable gestión permitieron que {nombre_u} alcanzara su máximo esplendor histórico."
    elif promedio >= 55:
        rango, titulo = "A", "Gran Estabilidad y Triunfo"
        texto = f"Superaste las crisis con solvencia y aseguraste un porvenir seguro y próspero en {nombre_u}."
    elif promedio >= 35:
        rango, titulo = "B", "Tiempos Difíciles pero Superados"
        texto = f"El ciclo anual fue duro y las pérdidas se hicieron sentir, pero lograste salir adelante en {nombre_u}."
    else:
        rango, titulo = "C", "Supervivencia Crítica"
        texto = f"Apenas lograste sostener el control en {nombre_u}. Las tensiones acumuladas amenazan lo poco que pudiste preservar."

    return {
        "_id": f"fin_{universo_id}_victoria",
        "universo_id": universo_id,
        "recurso_clave": None,
        "tipo": TipoFinalizacionEnum.VICTORIA_TIEMPO.value,
        "titulo": titulo,
        "texto": texto,
        "imagen": "/assets/narrative/finalizaciones/default.webp",
        "rango": rango,
    }


__all__ = [
    "ESTRELLAS_POR_RANGO",
    "estrellas_por_rango",
    "calificar_intento",
    "registrar_intento_narrativo",
    "sincronizar_intento_usuario",
    "verificar_colapso_recursos",
    "calcular_finalizacion_victoria",
]
