"""
condition_evaluator.py
Evaluación pura de condiciones ECA contra el estado vivo de una partida narrativa.
"""

import operator
from typing import Any, Callable, Dict, List, Optional

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
        corte = list(run_data.get("afinidad", {}).keys()) or run_data.get("corte_activa", [])
        return condicion.personaje_id in corte

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
