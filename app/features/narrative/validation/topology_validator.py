"""
topology_validator.py
Validación de topología DAG (alcanzabilidad, ciclos, hojas) y desenlaces de opciones en grafos V2.
"""

from typing import Any, Dict, List, Optional, Set

from app.features.narrative.validation.effects_validator import (
    Hallazgo,
    ResultadoValidacion,
    _as_dict,
)

_MODOS_BLOQUEO_VALIDOS = {"deshabilitada", "oculta"}


def _destinos(opt: Dict[str, Any]) -> List[str]:
    destinos: List[str] = []
    if opt.get("siguiente_nodo"):
        destinos.append(opt["siguiente_nodo"])
    for desenlace in opt.get("desenlaces") or []:
        destino = _as_dict(desenlace).get("nodo")
        if destino:
            destinos.append(destino)
    return destinos


def _detectar_ciclo(nodos: Dict[str, Dict[str, Any]], raiz: str) -> Optional[str]:
    """Devuelve el id de un nodo involucrado en un ciclo alcanzable, o None."""
    estado: Dict[str, int] = {}

    def visitar(nodo_id: str) -> Optional[str]:
        estado[nodo_id] = 1
        for opt in nodos[nodo_id].get("opciones") or []:
            for destino in _destinos(_as_dict(opt)):
                if destino not in nodos:
                    continue
                if estado.get(destino) == 1:
                    return destino
                if estado.get(destino, 0) == 0:
                    encontrado = visitar(destino)
                    if encontrado:
                        return encontrado
        estado[nodo_id] = 2
        return None

    return visitar(raiz) if raiz in nodos else None


def _alcanzables(nodos: Dict[str, Dict[str, Any]], raiz: str) -> Set[str]:
    if raiz not in nodos:
        return set()
    visitados: Set[str] = set()
    pendientes = [raiz]
    while pendientes:
        actual = pendientes.pop()
        if actual in visitados or actual not in nodos:
            continue
        visitados.add(actual)
        for opt in nodos[actual].get("opciones") or []:
            pendientes.extend(d for d in _destinos(_as_dict(opt)) if d in nodos)
    return visitados


def _validar_conectividad(nodos: Dict[str, Dict[str, Any]], raiz: str, resultado: ResultadoValidacion) -> None:
    if bool(nodos[raiz].get("es_final")):
        resultado.errores.append(Hallazgo("raiz_es_final", "El nodo raíz no puede ser un nodo final.", nodo_id=raiz))
    ciclo = _detectar_ciclo(nodos, raiz)
    if ciclo:
        resultado.errores.append(Hallazgo("ciclo_detectado", f"El grafo contiene un ciclo alcanzable en '{ciclo}'.", nodo_id=ciclo))
    alcanzables = _alcanzables(nodos, raiz)
    if not any(bool(nodos[n].get("es_final")) for n in alcanzables):
        resultado.errores.append(Hallazgo("sin_final_alcanzable", "No hay ningún nodo final alcanzable desde la raíz.", nodo_id=raiz))
    for nodo_id in sorted(set(nodos) - alcanzables):
        resultado.advertencias.append(Hallazgo("nodo_inalcanzable", "El nodo no es alcanzable desde la raíz.", nodo_id=nodo_id))


def _validar_desenlaces_opcion(
    clave: str,
    opcion_id: str,
    desenlaces: List[Dict[str, Any]],
    nodos: Dict[str, Dict[str, Any]],
    resultado: ResultadoValidacion,
) -> None:
    suma_pesos = 0.0
    for desenlace in desenlaces:
        destino = desenlace.get("nodo")
        if not destino:
            resultado.errores.append(Hallazgo("desenlace_sin_nodo", "Un desenlace no declara 'nodo'.", nodo_id=clave, opcion_id=opcion_id))
            continue
        if destino not in nodos:
            resultado.errores.append(Hallazgo("referencia_inexistente", f"El desenlace apunta a '{destino}', que no existe.", nodo_id=clave, opcion_id=opcion_id))
        try:
            peso = float(desenlace.get("peso", 1.0))
        except (TypeError, ValueError):
            resultado.errores.append(Hallazgo("peso_invalido", f"Peso no numérico para '{destino}'.", nodo_id=clave, opcion_id=opcion_id))
            continue
        if peso <= 0:
            resultado.errores.append(Hallazgo("peso_no_positivo", f"Peso no positivo para '{destino}'.", nodo_id=clave, opcion_id=opcion_id))
        else:
            suma_pesos += peso

    if suma_pesos <= 0:
        resultado.errores.append(Hallazgo(
            "desenlaces_sin_peso_positivo",
            "Ningún desenlace tiene peso positivo; el sorteo no puede resolverse.",
            nodo_id=clave,
            opcion_id=opcion_id,
        ))


def _validar_opcion(
    clave: str,
    opt: Dict[str, Any],
    nodos: Dict[str, Dict[str, Any]],
    opciones_vistas: Set[str],
    resultado: ResultadoValidacion,
) -> None:
    opcion_id = opt.get("id")
    if not opcion_id:
        resultado.errores.append(Hallazgo("opcion_sin_id", "Una opción no declara 'id'.", nodo_id=clave))
        return
    if opcion_id in opciones_vistas:
        resultado.errores.append(Hallazgo("opcion_duplicada", f"La opción '{opcion_id}' está repetida.", nodo_id=clave, opcion_id=opcion_id))
    opciones_vistas.add(opcion_id)

    siguiente = opt.get("siguiente_nodo")
    desenlaces = [_as_dict(d) for d in (opt.get("desenlaces") or [])]
    if not siguiente and not desenlaces:
        resultado.errores.append(Hallazgo("opcion_sin_destino", "La opción no apunta a ningún nodo.", nodo_id=clave, opcion_id=opcion_id))
    if siguiente and desenlaces:
        resultado.advertencias.append(Hallazgo(
            "opcion_con_destino_y_desenlaces",
            "La opción define 'siguiente_nodo' y 'desenlaces'; se usará el sorteo ponderado.",
            nodo_id=clave,
            opcion_id=opcion_id,
        ))
    if siguiente and siguiente not in nodos:
        resultado.errores.append(Hallazgo("referencia_inexistente", f"'siguiente_nodo' apunta a '{siguiente}', que no existe.", nodo_id=clave, opcion_id=opcion_id))
    if desenlaces:
        _validar_desenlaces_opcion(clave, opcion_id, desenlaces, nodos, resultado)

    modo = opt.get("bloqueo_modo", "deshabilitada")
    if modo not in _MODOS_BLOQUEO_VALIDOS:
        resultado.advertencias.append(Hallazgo(
            "bloqueo_modo_desconocido",
            f"bloqueo_modo '{modo}' desconocido; se tratará como 'deshabilitada'.",
            nodo_id=clave,
            opcion_id=opcion_id,
        ))
