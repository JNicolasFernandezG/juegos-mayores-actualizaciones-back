"""
rule_engine.py
Orquestador de reglas ECA (despacho de frecuencias y efectos) y fachada compatible
de evaluación de condiciones y ejecución de acciones.
"""

from typing import Any, Dict, Iterable, List, Optional

from app.features.narrative.engine.action_executor import (
    _aplicar_operacion_matematica,
    _extraer_primitiva_y_params,
    _resolver_limites,
    aplicar_delta_recurso,
    ejecutar_accion,
)
from app.features.narrative.engine.condition_evaluator import (
    _comparar_valores,
    evaluar_condicion,
    evaluar_condiciones,
    generar_motivo_bloqueo,
    primer_motivo_bloqueo,
)
from app.features.narrative.schemas.rules_schemas import EfectoSchema

# Único alias histórico del motor: el ciclo mensual se disparaba como 'cada_mes'
# y el catálogo de frecuencias lo nombra 'inicio_mes'.
_ALIAS_EVENTOS_MOTOR: Dict[str, str] = {
    "al_obtener": "al_obtener",
    "cada_mes": "inicio_mes",
    "mensual": "inicio_mes",
    "inicio_mes": "inicio_mes",
}


def _normalizar_evento_motor(valor: Any) -> str:
    crudo = valor.value if hasattr(valor, "value") else str(valor)
    return _ALIAS_EVENTOS_MOTOR.get(crudo, crudo)


def _resolver_evento_motor(
    frec_id: str,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Devuelve el evento del motor al que pertenece una frecuencia. El catálogo del
    universo manda: una frecuencia ausente o inactiva no dispara nada.
    """
    if catalogo_frecuencias is not None:
        item = catalogo_frecuencias.get(frec_id)
        if not item:
            return None
        return item.get("evento_motor")
    return _ALIAS_EVENTOS_MOTOR.get(frec_id)


def _frecuencia_coincide(
    efecto: EfectoSchema,
    disparador: Any,
    run_data: Dict[str, Any],
    duenio_id: Optional[str] = None,
    mes_actual: Optional[int] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> bool:
    """Determina si un efecto debe ejecutarse según el disparador y la periodicidad relativa."""
    disp_valor = _normalizar_evento_motor(disparador)

    if efecto.disparador and _normalizar_evento_motor(efecto.disparador) == disp_valor:
        return True

    frec_id = efecto.frecuencia_id
    if not frec_id:
        return False

    evento = _resolver_evento_motor(frec_id, catalogo_frecuencias)
    if evento is None or _normalizar_evento_motor(evento) != disp_valor:
        return False

    if disp_valor != "inicio_mes":
        return True

    frec_item = (catalogo_frecuencias or {}).get(frec_id) or {}
    cada = max(1, int(frec_item.get("cada", 1) or 1))
    desfase = int(frec_item.get("desfase", 0) or 0)
    conteo_desde = frec_item.get("conteo_desde", "adquisicion")
    cur_mes = int(mes_actual or run_data.get("mes_actual", 1))

    if conteo_desde == "adquisicion" and duenio_id:
        mes_adq = int(run_data.get("adquisiciones", {}).get(duenio_id, {}).get("mes", 1))
        delta = cur_mes - mes_adq
        return delta > 0 and (delta - desfase) >= 0 and ((delta - desfase) % cada == 0)

    return (cur_mes - desfase) > 0 and ((cur_mes - desfase) % cada == 0)


def despachar_efectos(
    disparador: Any,
    run_data: Dict[str, Any],
    efectos: List[Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
    duenio_id: Optional[str] = None,
    mes_actual: Optional[int] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> None:
    """Filtra efectos por disparador, evalúa sus condiciones y ejecuta sus acciones."""
    for efecto_raw in efectos:
        efecto = EfectoSchema(**efecto_raw) if isinstance(efecto_raw, dict) else efecto_raw
        if not _frecuencia_coincide(
            efecto, disparador, run_data, duenio_id, mes_actual, catalogo_frecuencias
        ):
            continue
        if not evaluar_condiciones(efecto.condiciones, run_data):
            continue

        acciones = efecto.acciones or ([efecto.accion] if efecto.accion else [])
        for accion in acciones:
            ejecutar_accion(
                accion,
                run_data,
                recursos_definicion,
                duenio_id=duenio_id,
                catalogo_acciones=catalogo_acciones,
            )


def despachar_efectos_entidades_activas(
    disparador: Any,
    run_data: Dict[str, Any],
    entidades: Iterable[Dict[str, Any]],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    mes_actual: Optional[int] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
) -> None:
    """Despacha efectos de un conjunto de cartas o personajes usando su `_id` como dueño."""
    for entidad in entidades:
        efectos = entidad.get("efectos") or []
        if not efectos:
            continue
        despachar_efectos(
            disparador,
            run_data,
            [EfectoSchema(**e) for e in efectos],
            recursos_definicion,
            duenio_id=str(entidad["_id"]),
            mes_actual=mes_actual,
            catalogo_acciones=catalogo_acciones,
            catalogo_frecuencias=catalogo_frecuencias,
        )


__all__ = [
    "evaluar_condicion",
    "evaluar_condiciones",
    "generar_motivo_bloqueo",
    "primer_motivo_bloqueo",
    "_comparar_valores",
    "_aplicar_operacion_matematica",
    "_extraer_primitiva_y_params",
    "_resolver_limites",
    "aplicar_delta_recurso",
    "ejecutar_accion",
    "despachar_efectos",
    "despachar_efectos_entidades_activas",
]
