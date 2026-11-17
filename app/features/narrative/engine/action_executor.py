"""
action_executor.py
Ejecución de acciones y primitivas ECA sobre el estado en memoria de una partida narrativa.
"""

import logging
from typing import Any, Dict, Optional, Union

from app.features.narrative.engine.tag_state import quitar_origen, quitar_tag, registrar_tags
from app.features.narrative.enums import OperacionMatematicaEnum, TipoAccionEnum, TipoCalculoEnum
from app.features.narrative.schemas.rules_schemas import (
    AccionReferenciadaSchema,
    AccionSchema,
    PrimitivaOperacionEnum,
)

logger = logging.getLogger(__name__)


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
        accion_id = accion.tipo.value
        params = {
            "clave": accion.clave,
            "valor": accion.valor,
            "tipo_calculo": accion.tipo_calculo.value if accion.tipo_calculo else "fijo",
            "personaje_id": accion.personaje_id,
            "tag": accion.tag,
            "destino": "portador" if not accion.personaje_id else "personaje",
        }
    elif isinstance(accion, dict) and "tipo" in accion:
        accion_id = accion["tipo"]
        params = {
            "clave": accion.get("clave"),
            "valor": accion.get("valor", 0),
            "tipo_calculo": accion.get("tipo_calculo", "fijo"),
            "personaje_id": accion.get("personaje_id"),
            "tag": accion.get("tag"),
            "destino": "portador" if not accion.get("personaje_id") else "personaje",
        }
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
    actual = int(afinidades.get(personaje_target, 50))
    afinidades[personaje_target] = max(0, min(100, actual + int(float(params.get("valor") or 0))))


def _ejecutar_otorgar_tag(tag: Optional[str], run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    if not tag:
        return
    if duenio_id:
        registrar_tags(run_data, duenio_id, [tag])
        return
    tags = run_data.setdefault("tags_activos", [])
    if tag not in tags:
        tags.append(tag)


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


def _mutar_limite(
    ruta: str, op_mat: Any, valor_num: float, run_data: Dict[str, Any], recursos_definicion: Optional[Dict[str, Dict[str, Any]]]
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


def _mutar_afinidad(ruta: str, op_mat: Any, valor_num: float, run_data: Dict[str, Any], duenio_id: Optional[str]) -> None:
    target = ruta.split(".", 1)[1]
    afinidades = run_data.setdefault("afinidad", {})
    if target in ("portador", "self", "me"):
        if duenio_id not in afinidades:
            logger.warning("mutar_estado descartado: '%s' no es personaje de la corte y no hay portador valido.", ruta)
            return
        target = duenio_id
    if target and target in afinidades:
        nueva_af = _aplicar_operacion_matematica(float(afinidades[target]), op_mat, valor_num)
        afinidades[target] = max(0, min(100, int(round(nueva_af))))


def _ejecutar_mutar_estado(
    params: Dict[str, Any], run_data: Dict[str, Any], recursos_definicion: Optional[Dict[str, Dict[str, Any]]], duenio_id: Optional[str]
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
        actual = float(recursos[clave_rec])
        aplicar_delta_recurso(run_data, clave_rec, _aplicar_operacion_matematica(actual, op_mat, valor_num) - actual, recursos_definicion)
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
        adq = run_data.setdefault("adquisiciones", {})
        adq.setdefault(id_entidad, {"mes": run_data.get("mes_actual", 1), "tipo": "personaje"})
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
        _ejecutar_mutar_estado(params, run_data, recursos_definicion, duenio_id)
    elif primitiva == PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value:
        _ejecutar_mutar_estado_entidad(params, run_data, duenio_id)
