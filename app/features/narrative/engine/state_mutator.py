"""
state_mutator.py
Mutaciones dinámicas sobre rutas de estado (`mutar_estado`) y altas/bajas de entidades
(`mutar_estado_entidad`) en una partida narrativa en memoria.
"""

import logging
from typing import Any, Callable, Dict, Optional, Union

from app.features.narrative.engine.tag_state import quitar_origen, quitar_tag, registrar_tags
from app.features.narrative.enums import OperacionMatematicaEnum

logger = logging.getLogger(__name__)


def clampear_afinidad(valor: float) -> int:
    """Acota cualquier afinidad al rango válido [0, 100]."""
    return max(0, min(100, int(round(valor))))


def _aplicar_operacion_matematica(
    actual: float,
    operacion: Optional[Union[OperacionMatematicaEnum, str]],
    valor: float,
) -> float:
    """Aplica sumar, restar, multiplicar, dividir (con salvaguarda /0), porcentual o fijar."""
    op = operacion.value if hasattr(operacion, "value") else str(operacion or "sumar").lower()
    if op == "sumar":
        return actual + valor
    if op == "restar":
        return actual - valor
    if op == "multiplicar":
        return actual * valor
    if op == "dividir":
        if valor == 0:
            logger.warning("División por cero detectada en mutar_estado; se mantiene el valor actual.")
            return actual
        return actual / valor
    if op == "porcentual":
        return actual + (actual * (valor / 100.0))
    if op == "fijar":
        return valor
    return actual + valor


def _ejecutar_otorgar_tag(tag: Optional[str], run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    if not tag:
        return
    if duenio_id:
        registrar_tags(run_data, duenio_id, [tag])
        return
    tags = run_data.setdefault("tags_activos", [])
    if tag not in tags:
        tags.append(tag)


def _mutar_limite(
    ruta: str, op_mat: Any, valor_num: float, run_data: Dict[str, Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    partes = ruta.split(".")
    if len(partes) < 3:
        return
    clave_rec, sub_lim = partes[1], partes[2]
    lim_dict = run_data.setdefault("limites", {}).setdefault(clave_rec, {})
    base_def = (recursos_definicion or {}).get(clave_rec, {})
    default_lim = base_def.get(sub_lim, 0 if sub_lim == "min" else 100)

    nuevo_lim = int(round(_aplicar_operacion_matematica(float(lim_dict.get(sub_lim, default_lim)), op_mat, valor_num)))
    otro = "max" if sub_lim == "min" else "min"
    valor_otro = lim_dict.get(otro) if lim_dict.get(otro) is not None else base_def.get(otro)
    if valor_otro is not None:
        nuevo_lim = min(nuevo_lim, int(valor_otro)) if sub_lim == "min" else max(nuevo_lim, int(valor_otro))
    lim_dict[sub_lim] = nuevo_lim

    recursos = run_data.setdefault("recursos", {})
    if clave_rec in recursos:
        cur_min = float(lim_dict.get("min", base_def.get("min", 0)))
        cur_max = float(lim_dict.get("max", base_def.get("max", 100)))
        recursos[clave_rec] = int(max(cur_min, min(cur_max, float(recursos[clave_rec]))))


def _mutar_afinidad(
    ruta: str, op_mat: Any, valor_num: float, run_data: Dict[str, Any], duenio_id: Optional[str]
) -> None:
    target = ruta.split(".", 1)[1]
    afinidades = run_data.setdefault("afinidad", {})
    if target in ("portador", "self", "me"):
        if duenio_id not in afinidades:
            logger.warning("mutar_estado descartado: '%s' no es personaje de la corte y no hay portador valido.", ruta)
            return
        target = duenio_id
    if target and target in afinidades:
        afinidades[target] = clampear_afinidad(_aplicar_operacion_matematica(float(afinidades[target]), op_mat, valor_num))


def _ejecutar_mutar_estado(
    params: Dict[str, Any], run_data: Dict[str, Any],
    recursos_definicion: Optional[Dict[str, Dict[str, Any]]], duenio_id: Optional[str],
    aplicar_delta_fn: Optional[Callable[..., Optional[int]]] = None,
) -> None:
    ruta = params.get("ruta") or params.get("clave")
    if not ruta:
        return
    op_mat = params.get("operacion_matematica", OperacionMatematicaEnum.SUMAR.value)
    valor_num = float(params.get("valor") or 0.0)

    if ruta.startswith("recursos.") or (recursos_definicion and ruta in recursos_definicion):
        clave_rec = ruta.split(".", 1)[1] if ruta.startswith("recursos.") else ruta
        recursos = run_data.get("recursos", {})
        if clave_rec not in recursos:
            logger.warning("mutar_estado descartado: la ruta '%s' no apunta a un recurso del universo.", ruta)
            return
        if aplicar_delta_fn is None:
            from app.features.narrative.engine.action_executor import aplicar_delta_recurso
            aplicar_delta_fn = aplicar_delta_recurso
        actual = float(recursos[clave_rec])
        aplicar_delta_fn(run_data, clave_rec, _aplicar_operacion_matematica(actual, op_mat, valor_num) - actual, recursos_definicion)
    elif ruta.startswith("limites."):
        _mutar_limite(ruta, op_mat, valor_num, run_data, recursos_definicion)
    elif ruta.startswith("afinidad."):
        _mutar_afinidad(ruta, op_mat, valor_num, run_data, duenio_id)
    elif ruta.startswith("variables."):
        var_clave = ruta.split(".", 1)[1]
        variables = run_data.setdefault("variables", {})
        variables[var_clave] = round(_aplicar_operacion_matematica(float(variables.get(var_clave, 0.0)), op_mat, valor_num), 4)


def _ejecutar_mutar_entidad_personaje(operacion: str, id_entidad: str, run_data: Dict[str, Any]) -> None:
    corte = run_data.setdefault("corte_activa", [])
    afinidades = run_data.setdefault("afinidad", {})
    if operacion in ("alta", "agregar"):
        if id_entidad not in corte:
            corte.append(id_entidad)
        afinidades.setdefault(id_entidad, 50)
        run_data.setdefault("adquisiciones", {}).setdefault(
            id_entidad, {"mes": run_data.get("mes_actual", 1), "tipo": "personaje"}
        )
    elif operacion in ("baja", "eliminar", "remover"):
        if id_entidad in corte:
            corte.remove(id_entidad)
        afinidades.pop(id_entidad, None)
        mods = run_data.get("modificadores_pasivos", [])
        run_data["modificadores_pasivos"] = [m for m in mods if m.get("fuente") != id_entidad]
        quitar_origen(run_data, id_entidad)


def _ejecutar_mutar_estado_entidad(params: Dict[str, Any], run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    entidad = (params.get("entidad") or "").lower()
    operacion = (params.get("operacion") or "").lower()
    id_entidad = params.get("id_entidad") or params.get("tag") or params.get("personaje_id")
    if not id_entidad:
        return
    if entidad == "tag":
        if operacion in ("alta", "agregar"):
            _ejecutar_otorgar_tag(id_entidad, run_data, duenio_id)
        elif operacion in ("baja", "eliminar", "remover"):
            quitar_tag(run_data, id_entidad)
    elif entidad == "personaje":
        _ejecutar_mutar_entidad_personaje(operacion, id_entidad, run_data)
