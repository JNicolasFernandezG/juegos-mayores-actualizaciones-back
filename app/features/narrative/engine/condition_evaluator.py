"""
condition_evaluator.py
Evaluación pura de condiciones ECA y generación de motivos de bloqueo en UI.
"""

import operator
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.features.narrative.engine.tag_state import personajes_activos
from app.features.narrative.enums import OperadorEnum, TipoCondicionEnum
from app.features.narrative.schemas.rules_schemas import CondicionSchema

_OPERADORES: Dict[OperadorEnum, Callable[[float, float], bool]] = {
    OperadorEnum.MAYOR_IGUAL: operator.ge,
    OperadorEnum.MENOR_IGUAL: operator.le,
    OperadorEnum.MAYOR: operator.gt,
    OperadorEnum.MENOR: operator.lt,
    OperadorEnum.IGUAL: operator.eq,
    OperadorEnum.DISTINTO: operator.ne,
}


def _comparar_valores(actual: float, operador: Optional[OperadorEnum], objetivo: float) -> bool:
    """Compara dos valores flotantes utilizando el operador relacional provisto."""
    if operador is None:
        return False
    comparador = _OPERADORES.get(operador)
    return comparador(actual, objetivo) if comparador is not None else False


def _campo_condicion(cond: Any, nombre: str, default: Any = None) -> Any:
    return cond.get(nombre, default) if isinstance(cond, dict) else getattr(cond, nombre, default)


def evaluar_condicion(condicion: Any, run_data: Dict[str, Any]) -> bool:
    """
    Evalúa una condición individual contra el estado vivo de la partida.
    Acepta tanto una instancia de CondicionSchema como un dict de MongoDB.
    """
    if isinstance(condicion, dict):
        condicion = CondicionSchema(**condicion)

    tipo = condicion.tipo
    if tipo == TipoCondicionEnum.COMPARAR_RECURSO:
        if not condicion.clave:
            return False
        valor_actual = float(run_data.get("recursos", {}).get(condicion.clave, 0))
        return _comparar_valores(valor_actual, condicion.operador, float(condicion.valor or 0))

    if tipo == TipoCondicionEnum.TIENE_PERSONAJE:
        return condicion.personaje_id in personajes_activos(run_data)

    if tipo == TipoCondicionEnum.AFINIDAD_PERSONAJE:
        if not condicion.personaje_id:
            return False
        afinidad_actual = float(run_data.get("afinidad", {}).get(condicion.personaje_id, 50))
        return _comparar_valores(afinidad_actual, condicion.operador, float(condicion.valor or 0))

    if tipo == TipoCondicionEnum.TIENE_TAG:
        return condicion.tag in run_data.get("tags_activos", [])

    if tipo == TipoCondicionEnum.TIENE_CARTA:
        return condicion.carta_id in run_data.get("cartas_en_mano", [])

    return False


def evaluar_condiciones(condiciones: List[Any], run_data: Dict[str, Any]) -> bool:
    """Evalúa una lista de condiciones bajo operador lógico AND (True si está vacía)."""
    if not condiciones:
        return True
    return all(evaluar_condicion(c, run_data) for c in condiciones)


def generar_motivo_bloqueo(cond: Any) -> str:
    """Genera un mensaje explicativo amigable para el jugador sobre el requisito faltante."""
    tipo = _campo_condicion(cond, "tipo")
    if isinstance(tipo, str):
        try:
            tipo = TipoCondicionEnum(tipo)
        except ValueError:
            pass

    op = _campo_condicion(cond, "operador", ">=") or ">="
    op_str = getattr(op, "value", str(op))
    val = _campo_condicion(cond, "valor", 0)

    if tipo == TipoCondicionEnum.COMPARAR_RECURSO:
        clave = (_campo_condicion(cond, "clave", "recurso") or "recurso").capitalize()
        return f"Requiere {clave} {op_str} {val}"
    if tipo == TipoCondicionEnum.TIENE_PERSONAJE:
        return f"Requiere a {_campo_condicion(cond, 'personaje_id', 'personaje')} en la corte"
    if tipo == TipoCondicionEnum.AFINIDAD_PERSONAJE:
        pj = _campo_condicion(cond, "personaje_id", "personaje")
        return f"Requiere afinidad {op_str} {val} con {pj}"
    if tipo == TipoCondicionEnum.TIENE_TAG:
        return f"Requiere atributo '{_campo_condicion(cond, 'tag', 'atributo')}'"
    if tipo == TipoCondicionEnum.TIENE_CARTA:
        return f"Requiere poseer la carta '{_campo_condicion(cond, 'carta_id', 'objeto')}'"
    return "Requisitos no cumplidos"


def primer_motivo_bloqueo(
    condiciones: Sequence[Any],
    run_data: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Devuelve el motivo legible de la primera condición incumplida, o None si todas cumplen."""
    if run_data is None or not condiciones:
        return None
    for cond in condiciones:
        cond_dict = cond.model_dump() if hasattr(cond, "model_dump") else cond
        if not evaluar_condicion(cond_dict, run_data):
            return generar_motivo_bloqueo(cond)
    return None
