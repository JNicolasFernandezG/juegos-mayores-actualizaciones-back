"""
action_executor.py
Ejecución de acciones y primitivas ECA sobre el estado en memoria de una partida narrativa.
"""

import logging
from typing import Any, Dict, Optional

from app.features.narrative.engine.state_mutator import (
    _aplicar_operacion_matematica, _ejecutar_mutar_entidad_personaje, _ejecutar_mutar_estado,
    _ejecutar_mutar_estado_entidad, _ejecutar_otorgar_tag, _mutar_afinidad, _mutar_limite,
    clampear_afinidad,
)
from app.features.narrative.engine.tag_state import quitar_tag
from app.features.narrative.enums import TipoAccionEnum, TipoCalculoEnum
from app.features.narrative.schemas.rules_schemas import (
    AccionReferenciadaSchema, AccionSchema, PrimitivaOperacionEnum,
)

logger = logging.getLogger(__name__)


def _params_accion_legacy(accion: Any) -> Dict[str, Any]:
    getter = accion.get if isinstance(accion, dict) else lambda k, d=None: getattr(accion, k, d)
    tipo_calc = getter("tipo_calculo")
    personaje_id = getter("personaje_id")
    return {
        "clave": getter("clave"),
        "valor": getter("valor", 0),
        "tipo_calculo": tipo_calc.value if hasattr(tipo_calc, "value") else (tipo_calc or "fijo"),
        "personaje_id": personaje_id,
        "tag": getter("tag"),
        "destino": "portador" if not personaje_id else "personaje",
    }


def _extraer_primitiva_y_params(
    accion: Any,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    """Extrae primitiva ejecutable y parámetros desde AccionSchema o AccionReferenciadaSchema."""
    if isinstance(accion, AccionReferenciadaSchema):
        accion_id, params = accion.accion_id, accion.parametros.model_dump()
    elif isinstance(accion, dict) and "accion_id" in accion:
        accion_id, params = accion["accion_id"], accion.get("parametros", {})
    elif isinstance(accion, AccionSchema):
        accion_id, params = accion.tipo.value, _params_accion_legacy(accion)
    elif isinstance(accion, dict) and "tipo" in accion:
        accion_id, params = accion["tipo"], _params_accion_legacy(accion)
    elif isinstance(accion, dict) and "primitiva" in accion:
        accion_id = accion["primitiva"]
        raw_params = accion.get("parametros")
        params = raw_params if isinstance(raw_params, dict) else {k: v for k, v in accion.items() if k != "primitiva"}
    else:
        return "", {}

    primitiva = accion_id
    if catalogo_acciones and accion_id in catalogo_acciones:
        cat_item = catalogo_acciones[accion_id]
        primitiva = cat_item.get("primitiva") or cat_item.get("tipo_accion") or accion_id
    return str(primitiva), params


def _resolver_limites(
    run_data: Dict[str, Any],
    clave: str,
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[tuple[float, float]]:
    """Devuelve (min, max) aplicables a un recurso, priorizando los límites dinámicos del run."""
    limite_run = (run_data.get("limites") or {}).get(clave)
    base = (recursos_definicion or {}).get(clave, {})
    if isinstance(limite_run, dict) and ("min" in limite_run or "max" in limite_run):
        return (
            float(limite_run.get("min", base.get("min", 0))),
            float(limite_run.get("max", base.get("max", 100))),
        )
    return (float(base.get("min", 0)), float(base.get("max", 100))) if base else None


def aplicar_delta_recurso(
    run_data: Dict[str, Any],
    clave: str,
    delta: float,
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[int]:
    """Único punto de mutación de un recurso vivo de la partida (con amortiguación y clamping)."""
    recursos = run_data.setdefault("recursos", {})
    if clave not in recursos:
        logger.warning("Acción narrativa descartada: '%s' no es un recurso de la partida.", clave)
        return None

    delta_efectivo = float(delta)
    if delta_efectivo < 0:
        reduccion_dif = float(run_data.get("dificultad_reduccion") or 0)
        if 0 < reduccion_dif <= 100:
            delta_efectivo *= 1.0 - (reduccion_dif / 100.0)
        for mod in run_data.get("modificadores_pasivos", []):
            if mod.get("tipo") == "amortiguar_danio" and (not mod.get("clave") or mod.get("clave") == clave):
                reduccion = float(mod.get("reduccion_porcentual", 0))
                if 0 < reduccion <= 100:
                    delta_efectivo *= 1.0 - (reduccion / 100.0)

    nuevo_valor = float(recursos[clave]) + delta_efectivo
    limites = _resolver_limites(run_data, clave, recursos_definicion)
    if limites is not None:
        nuevo_valor = max(limites[0], min(limites[1], nuevo_valor))

    recursos[clave] = int(round(nuevo_valor))
    return recursos[clave]


def _ejecutar_modificar_recurso(
    params: Dict[str, Any], run_data: Dict[str, Any], recursos_definicion: Optional[Dict[str, Dict[str, Any]]]
) -> None:
    clave = params.get("clave")
    if not clave:
        return
    valor_actual = float(run_data.setdefault("recursos", {}).get(clave, 0))
    valor_num = float(params.get("valor") or 0)
    if params.get("tipo_calculo") in (TipoCalculoEnum.PORCENTUAL.value, "porcentual"):
        delta = valor_actual * (valor_num / 100.0)
    else:
        delta = valor_num
    aplicar_delta_recurso(run_data, clave, delta, recursos_definicion)


def _ejecutar_modificar_afinidad(params: Dict[str, Any], run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    afinidades = run_data.setdefault("afinidad", {})
    if params.get("destino", "personaje") == "portador":
        if duenio_id not in afinidades:
            logger.warning("modificar_afinidad descartada: el portador '%s' no es un personaje de la corte.", duenio_id)
            return
        personaje_target: Optional[str] = duenio_id
    else:
        personaje_target = params.get("personaje_id")
    if not personaje_target:
        return
    actual = float(afinidades.get(personaje_target, 50))
    afinidades[personaje_target] = clampear_afinidad(actual + float(params.get("valor") or 0))


def _ejecutar_amortiguar_danio(params: Dict[str, Any], run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    clave = params.get("clave")
    reduccion = float(params.get("valor") or params.get("porcentaje") or 0)
    mods = run_data.setdefault("modificadores_pasivos", [])
    existente = next(
        (m for m in mods if m.get("tipo") == "amortiguar_danio" and m.get("clave") == clave and m.get("fuente") == duenio_id),
        None,
    )
    if existente:
        existente["reduccion_porcentual"] = max(float(existente.get("reduccion_porcentual", 0)), reduccion)
        return
    mods.append({"tipo": "amortiguar_danio", "clave": clave, "reduccion_porcentual": reduccion, "fuente": duenio_id})


def ejecutar_accion(
    accion: Any,
    run_data: Dict[str, Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]] = None,
    duenio_id: Optional[str] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
) -> None:
    """Modifica el estado en memoria de run_data según el tipo o primitiva de acción."""
    primitiva, params = _extraer_primitiva_y_params(accion, catalogo_acciones)
    if not primitiva:
        return

    if primitiva in (TipoAccionEnum.MODIFICAR_RECURSO.value, PrimitivaOperacionEnum.MODIFICAR_RECURSO.value):
        _ejecutar_modificar_recurso(params, run_data, recursos_definicion)
    elif primitiva in (TipoAccionEnum.MODIFICAR_AFINIDAD.value, PrimitivaOperacionEnum.MODIFICAR_AFINIDAD.value):
        _ejecutar_modificar_afinidad(params, run_data, duenio_id)
    elif primitiva in (TipoAccionEnum.OTORGAR_TAG.value, PrimitivaOperacionEnum.OTORGAR_TAG.value):
        _ejecutar_otorgar_tag(params.get("tag"), run_data, duenio_id)
    elif primitiva == PrimitivaOperacionEnum.REMOVER_TAG.value:
        quitar_tag(run_data, params.get("tag"))
    elif primitiva in (TipoAccionEnum.AMORTIGUAR_DANIO.value, PrimitivaOperacionEnum.AMORTIGUAR_DANIO.value):
        _ejecutar_amortiguar_danio(params, run_data, duenio_id)
    elif primitiva == PrimitivaOperacionEnum.MUTAR_ESTADO.value:
        _ejecutar_mutar_estado(params, run_data, recursos_definicion, duenio_id, aplicar_delta_recurso)
    elif primitiva == PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value:
        _ejecutar_mutar_estado_entidad(params, run_data, duenio_id)


__all__ = [
    "_aplicar_operacion_matematica", "_ejecutar_mutar_entidad_personaje", "_ejecutar_mutar_estado",
    "_ejecutar_mutar_estado_entidad", "_extraer_primitiva_y_params", "_mutar_afinidad",
    "_mutar_limite", "_resolver_limites", "aplicar_delta_recurso", "clampear_afinidad", "ejecutar_accion",
]
