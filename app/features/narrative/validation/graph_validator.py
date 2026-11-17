"""
graph_validator.py
Validación estática de grafos narrativos V2: referencias, hojas, pesos y ciclos.

No toca la base de datos en ``validar_grafo``: recibe el documento y devuelve hallazgos.
``validar_grafos_almacenados`` es el adaptador para revisar las colecciones completas.
"""

from typing import Any, Dict, List, Optional, Sequence, Set

from app.features.narrative.constants import (
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.validation.effects_validator import (
    Hallazgo,
    ResultadoValidacion,
    _as_dict,
    _cargar_contexto_universo,
    _crudo,
    hallazgos_de_efectos,
    hallazgos_de_tags_referenciados,
    validar_efectos_almacenables,
)

TIPOS_VALIDOS = ("evento", "conversacion", "evento_especial")

_COLECCION_POR_TIPO = {
    "evento": COLL_V2_EVENTS,
    "conversacion": COLL_V2_CONVERSATIONS,
    "evento_especial": COLL_V2_EVENTOS_ESPECIALES,
}

_DIRECCIONES_VALIDAS = {"lealtad", "traicion"}
_MODOS_BLOQUEO_VALIDOS = {"deshabilitada", "oculta"}
_TIPOS_DESENLACE_VALIDOS = {"positivo", "negativo", "neutro"}


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


def _validar_cabecera_y_nodos(
    doc: Dict[str, Any], tipo: str, grafo_id: Optional[str], resultado: ResultadoValidacion
) -> Optional[Dict[str, Dict[str, Any]]]:
    if tipo not in TIPOS_VALIDOS:
        resultado.errores.append(Hallazgo("tipo_invalido", f"Tipo de grafo desconocido: '{tipo}'."))
        return None
    if tipo == "evento_especial":
        if not (doc.get("personaje_id") or "").strip():
            resultado.errores.append(Hallazgo("personaje_id_ausente", "Un evento especial requiere 'personaje_id'."))
        direccion = doc.get("direccion")
        if direccion not in _DIRECCIONES_VALIDAS:
            resultado.errores.append(Hallazgo("direccion_invalida", f"Dirección inválida: '{direccion}'. Esperado lealtad o traicion."))
    if tipo == "evento" and grafo_id and grafo_id in (doc.get("requisitos_eventos_previos") or []):
        resultado.errores.append(Hallazgo("requisito_autorreferente", "El evento se exige a sí mismo como requisito previo."))

    nodos_crudos = doc.get("nodos") or {}
    if not isinstance(nodos_crudos, dict) or not nodos_crudos:
        resultado.errores.append(Hallazgo("nodos_vacios", "El grafo no tiene nodos."))
        return None

    nodos: Dict[str, Dict[str, Any]] = {}
    for clave, nodo_crudo in nodos_crudos.items():
        nodo = _as_dict(nodo_crudo)
        nodos[str(clave)] = nodo
        nodo_id = nodo.get("id")
        if not nodo_id:
            resultado.errores.append(Hallazgo("nodo_sin_id", f"El nodo '{clave}' no declara 'id'.", nodo_id=str(clave)))
        elif nodo_id != clave:
            resultado.errores.append(Hallazgo("id_nodo_inconsistente", f"La clave '{clave}' no coincide con el id '{nodo_id}'.", nodo_id=str(clave)))

    raiz = doc.get("nodo_raiz")
    if not raiz:
        resultado.errores.append(Hallazgo("nodo_raiz_ausente", "El grafo no declara 'nodo_raiz'."))
    elif raiz not in nodos:
        resultado.errores.append(Hallazgo("nodo_raiz_inexistente", f"El nodo raíz '{raiz}' no existe.", nodo_id=raiz))
    return nodos


def _validar_desenlaces_opcion(
    clave: str, opcion_id: str, desenlaces: List[Dict[str, Any]], nodos: Dict[str, Dict[str, Any]], resultado: ResultadoValidacion
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
        resultado.errores.append(Hallazgo("desenlaces_sin_peso_positivo", "Ningún desenlace tiene peso positivo; el sorteo no puede resolverse.", nodo_id=clave, opcion_id=opcion_id))


def _validar_opcion(
    clave: str, opt: Dict[str, Any], nodos: Dict[str, Dict[str, Any]], opciones_vistas: Set[str], resultado: ResultadoValidacion
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
        resultado.advertencias.append(Hallazgo("opcion_con_destino_y_desenlaces", "La opción define 'siguiente_nodo' y 'desenlaces'; se usará el sorteo ponderado.", nodo_id=clave, opcion_id=opcion_id))
    if siguiente and siguiente not in nodos:
        resultado.errores.append(Hallazgo("referencia_inexistente", f"'siguiente_nodo' apunta a '{siguiente}', que no existe.", nodo_id=clave, opcion_id=opcion_id))
    if desenlaces:
        _validar_desenlaces_opcion(clave, opcion_id, desenlaces, nodos, resultado)

    modo = opt.get("bloqueo_modo", "deshabilitada")
    if modo not in _MODOS_BLOQUEO_VALIDOS:
        resultado.advertencias.append(Hallazgo("bloqueo_modo_desconocido", f"bloqueo_modo '{modo}' desconocido; se tratará como 'deshabilitada'.", nodo_id=clave, opcion_id=opcion_id))


def _validar_impactos_y_efectos_nodo(
    clave: str,
    nodo: Dict[str, Any],
    es_final: bool,
    resultado: ResultadoValidacion,
    *,
    recursos_validos: Optional[Set[str]],
    catalogo_acciones: Optional[Dict[str, Any]],
    catalogo_frecuencias: Optional[Dict[str, Any]],
    tags_validos: Optional[Set[str]],
) -> None:
    for impacto in (_as_dict(i) for i in (nodo.get("impactos_recursos") or [])):
        recurso = _crudo(impacto.get("recurso"))
        if recurso and recursos_validos is not None and recurso.lower() not in recursos_validos:
            resultado.errores.append(Hallazgo("recurso_inexistente", f"'{recurso}' no es un recurso del universo; el motor descarta el impacto.", nodo_id=clave))

    for tag in (nodo.get("impactos_tags") or []):
        for hallazgo in hallazgos_de_tags_referenciados([tag], tags_validos=tags_validos):
            resultado.errores.append(Hallazgo(hallazgo.codigo, hallazgo.mensaje, nodo_id=clave))

    efectos = [_as_dict(e) for e in (nodo.get("efectos") or [])]
    if efectos and not es_final:
        resultado.errores.append(Hallazgo("efectos_en_nodo_no_final", "Los efectos sólo se despachan en el nodo final; acá quedarían inactivos.", nodo_id=clave))
    resultado.errores.extend(hallazgos_de_efectos(
        efectos, recursos_validos=recursos_validos, catalogo_acciones=catalogo_acciones,
        catalogo_frecuencias=catalogo_frecuencias, tags_validos=tags_validos, nodo_id=clave,
    ))


def _validar_nodo(
    clave: str,
    nodo: Dict[str, Any],
    nodos: Dict[str, Dict[str, Any]],
    opciones_vistas: Set[str],
    resultado: ResultadoValidacion,
    *,
    recursos_validos: Optional[Set[str]],
    catalogo_acciones: Optional[Dict[str, Any]],
    catalogo_frecuencias: Optional[Dict[str, Any]],
    tags_validos: Optional[Set[str]],
) -> None:
    es_final = bool(nodo.get("es_final"))
    opciones = [_as_dict(o) for o in (nodo.get("opciones") or [])]
    if es_final and opciones:
        resultado.errores.append(Hallazgo("nodo_final_con_opciones", "Un nodo final no puede ofrecer opciones.", nodo_id=clave))
    if not es_final and not opciones:
        resultado.errores.append(Hallazgo("nodo_sin_opciones", "Un nodo no final debe ofrecer al menos una opción.", nodo_id=clave))
    if es_final and not (nodo.get("resultado_texto") or "").strip():
        resultado.advertencias.append(Hallazgo("nodo_final_sin_texto", "El nodo final no tiene resultado_texto.", nodo_id=clave))

    desenlace = _crudo(nodo.get("tipo_desenlace"))
    if desenlace is not None and desenlace not in _TIPOS_DESENLACE_VALIDOS:
        resultado.errores.append(Hallazgo("tipo_desenlace_invalido", f"tipo_desenlace '{desenlace}' desconocido; esperado uno de {sorted(_TIPOS_DESENLACE_VALIDOS)}.", nodo_id=clave))

    _validar_impactos_y_efectos_nodo(
        clave, nodo, es_final, resultado,
        recursos_validos=recursos_validos, catalogo_acciones=catalogo_acciones,
        catalogo_frecuencias=catalogo_frecuencias, tags_validos=tags_validos,
    )
    for opt in opciones:
        _validar_opcion(clave, opt, nodos, opciones_vistas, resultado)


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


def validar_grafo(
    grafo: Any,
    tipo: str = "evento",
    *,
    recursos_validos: Optional[Set[str]] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
    tags_validos: Optional[Set[str]] = None,
) -> ResultadoValidacion:
    """Valida la estructura y opcionalmente referencias contra catálogos de un grafo V2."""
    doc = _as_dict(grafo)
    grafo_id = doc.get("_id") or doc.get("id")
    resultado = ResultadoValidacion(tipo=tipo, grafo_id=grafo_id)

    nodos = _validar_cabecera_y_nodos(doc, tipo, grafo_id, resultado)
    if nodos is None:
        return resultado

    opciones_vistas: Set[str] = set()
    for clave, nodo in nodos.items():
        _validar_nodo(
            clave, nodo, nodos, opciones_vistas, resultado,
            recursos_validos=recursos_validos, catalogo_acciones=catalogo_acciones,
            catalogo_frecuencias=catalogo_frecuencias, tags_validos=tags_validos,
        )

    raiz = doc.get("nodo_raiz")
    if raiz in nodos:
        _validar_conectividad(nodos, raiz, resultado)
    return resultado


async def validar_grafo_para_guardado(grafo: Any, tipo: str = "evento", db=None) -> ResultadoValidacion:
    """Validación completa de un grafo antes de persistirlo: estructura más catálogo del universo."""
    doc = _as_dict(grafo)
    if db is None:
        from app.core.database import get_database
        db = get_database()
    contexto = await _cargar_contexto_universo(str(doc.get("universo_id") or "corte_medieval"), db)
    return validar_grafo(doc, tipo, **contexto)


async def validar_grafos_almacenados(
    db=None,
    *,
    tipos: Optional[Sequence[str]] = None,
    grafo_id: Optional[str] = None,
    universo_id: Optional[str] = None,
    limite: int = 500,
) -> List[ResultadoValidacion]:
    """Valida los grafos persistidos. ``db`` se inyecta en tests; en runtime usa la global."""
    if db is None:
        from app.core.database import get_database
        db = get_database()

    tipos_a_validar = list(tipos) if tipos else list(TIPOS_VALIDOS)
    invalidos = [t for t in tipos_a_validar if t not in _COLECCION_POR_TIPO]
    if invalidos:
        raise ValueError(f"Tipos de grafo inválidos: {invalidos}")

    resultados: List[ResultadoValidacion] = []
    contextos: Dict[str, Dict[str, Any]] = {}
    for tipo in tipos_a_validar:
        query: Dict[str, Any] = {}
        if grafo_id:
            query["_id"] = grafo_id
        if universo_id:
            query["universo_id"] = universo_id
        async for documento in db[_COLECCION_POR_TIPO[tipo]].find(query).limit(limite):
            universo = str(documento.get("universo_id") or "corte_medieval")
            if universo not in contextos:
                contextos[universo] = await _cargar_contexto_universo(universo, db)
            resultados.append(validar_grafo(documento, tipo, **contextos[universo]))
    return resultados


__all__ = [
    "TIPOS_VALIDOS",
    "Hallazgo",
    "ResultadoValidacion",
    "hallazgos_de_tags_referenciados",
    "hallazgos_de_efectos",
    "validar_efectos_almacenables",
    "_cargar_contexto_universo",
    "validar_grafo",
    "validar_grafo_para_guardado",
    "validar_grafos_almacenados",
]
