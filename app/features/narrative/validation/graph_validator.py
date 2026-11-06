"""
graph_validator.py
Validación estática de grafos narrativos V2: referencias, hojas, pesos y ciclos.

No toca la base de datos en ``validar_grafo``: recibe el documento y devuelve hallazgos.
``validar_grafos_almacenados`` es el adaptador para revisar las colecciones completas.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from app.features.narrative.constants import (
    COLL_TAGS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.schemas.rules_schemas import PrimitivaOperacionEnum

TIPOS_VALIDOS = ("evento", "conversacion", "evento_especial")

_PRIMITIVAS_VALIDAS = {p.value for p in PrimitivaOperacionEnum}

_COLECCION_POR_TIPO = {
    "evento": COLL_V2_EVENTS,
    "conversacion": COLL_V2_CONVERSATIONS,
    "evento_especial": COLL_V2_EVENTOS_ESPECIALES,
}

_DIRECCIONES_VALIDAS = {"lealtad", "traicion"}
_MODOS_BLOQUEO_VALIDOS = {"deshabilitada", "oculta"}
_TIPOS_DESENLACE_VALIDOS = {"positivo", "negativo", "neutro"}

# Eventos que el motor despacha por nombre, sin depender del catálogo de frecuencias.
_EVENTOS_MOTOR = {
    "al_obtener",
    "cada_mes",
    "inicio_mes",
    "al_desenlace",
    "en_evento_positivo",
    "en_evento_negativo",
}


@dataclass(frozen=True)
class Hallazgo:
    codigo: str
    mensaje: str
    nodo_id: Optional[str] = None
    opcion_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.nodo_id is not None:
            data["nodo_id"] = self.nodo_id
        if self.opcion_id is not None:
            data["opcion_id"] = self.opcion_id
        return data


@dataclass
class ResultadoValidacion:
    tipo: str
    grafo_id: Optional[str]
    errores: List[Hallazgo] = field(default_factory=list)
    advertencias: List[Hallazgo] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tipo": self.tipo,
            "grafo_id": self.grafo_id,
            "valido": self.valido,
            "errores": [h.as_dict() for h in self.errores],
            "advertencias": [h.as_dict() for h in self.advertencias],
        }


def _as_dict(value: Any) -> Dict[str, Any]:
    """Normaliza nodos/opciones que pueden llegar como modelos Pydantic o como dict."""
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(by_alias=True)
    return {}


def _destinos(opt: Dict[str, Any]) -> List[str]:
    destinos: List[str] = []
    if opt.get("siguiente_nodo"):
        destinos.append(opt["siguiente_nodo"])
    for desenlace in opt.get("desenlaces") or []:
        destino = _as_dict(desenlace).get("nodo")
        if destino:
            destinos.append(destino)
    return destinos


def _crudo(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value.value if hasattr(value, "value") else value)


def _primitiva_de(accion_id: str, catalogo_acciones: Optional[Dict[str, Any]]) -> str:
    item = (catalogo_acciones or {}).get(accion_id)
    if item:
        return _crudo(item.get("primitiva") or item.get("tipo_accion")) or accion_id
    return accion_id


def _recurso_exigido(primitiva: str, params: Dict[str, Any]) -> Optional[str]:
    """Recurso que la primitiva necesita que exista en la partida; None si no depende de uno."""
    if primitiva in ("modificar_recurso", "amortiguar_danio"):
        return _crudo(params.get("clave"))
    if primitiva == "mutar_estado":
        ruta = _crudo(params.get("ruta")) or ""
        for prefijo in ("recursos.", "limites."):
            if ruta.startswith(prefijo):
                return _crudo(ruta[len(prefijo):].split(".")[0]) or None
    return None


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


def hallazgos_de_tags_referenciados(
    tags: Sequence[Any] = (),
    condiciones: Sequence[Any] = (),
    *,
    tags_validos: Optional[Set[str]] = None,
) -> List[Hallazgo]:
    """Verifica que los tags declarados existan en el catálogo del universo."""
    if tags_validos is None:
        return []

    def buscar_tag(tag: Any) -> Optional[Hallazgo]:
        tag_id = _crudo(tag)
        if tag_id and tag_id not in tags_validos:
            return Hallazgo(
                "tag_inexistente",
                f"El tag '{tag_id}' no existe en el catálogo del universo.",
            )
        return None

    hallazgos: List[Hallazgo] = []
    for tag in tags:
        encontrado = buscar_tag(tag)
        if encontrado:
            hallazgos.append(encontrado)
    for crudo in condiciones:
        condicion = _as_dict(crudo)
        if _crudo(condicion.get("tipo")) == "tiene_tag":
            encontrado = buscar_tag(condicion.get("tag"))
            if encontrado:
                hallazgos.append(encontrado)
    return hallazgos


def hallazgos_de_efectos(
    efectos: Sequence[Any],
    *,
    recursos_validos: Optional[Set[str]] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
    tags_validos: Optional[Set[str]] = None,
    nodo_id: Optional[str] = None,
) -> List[Hallazgo]:
    """
    Errores de efectos ECA declarados en un nodo, una carta o un personaje.
    Replica el orden de resolución del motor para detectar lo que nunca se ejecuta.
    Sin catálogos pasados sólo controla lo estructural; con ellos, también la referencia.
    """
    hallazgos: List[Hallazgo] = []

    for indice, crudo in enumerate(efectos or []):
        efecto = _as_dict(crudo)
        etiqueta = efecto.get("id") or f"índice {indice}"

        def error(codigo: str, mensaje: str) -> None:
            hallazgos.append(Hallazgo(codigo, mensaje, nodo_id))

        evento = _crudo(efecto.get("frecuencia_id") or efecto.get("disparador"))
        if not evento:
            error("efecto_sin_evento", f"El efecto '{etiqueta}' no declara frecuencia ni disparador.")
        elif catalogo_frecuencias is not None and evento not in _EVENTOS_MOTOR \
                and not catalogo_frecuencias.get(evento):
            error(
                "evento_no_despachado",
                f"El efecto '{etiqueta}' usa '{evento}': el motor no lo emite y no está activo en el catálogo de frecuencias.",
            )

        hallazgos.extend(hallazgos_de_tags_referenciados(
            condiciones=efecto.get("condiciones") or [],
            tags_validos=tags_validos,
        ))

        acciones = [_as_dict(a) for a in (efecto.get("acciones") or [])]
        if efecto.get("accion"):
            acciones.append(_as_dict(efecto["accion"]))
        if not acciones:
            error("efecto_sin_acciones", f"El efecto '{etiqueta}' no ejecuta ninguna acción.")

        for accion in acciones:
            accion_id = _crudo(accion.get("accion_id") or accion.get("tipo"))
            if not accion_id:
                error("accion_sin_id", f"El efecto '{etiqueta}' tiene una acción sin identificador.")
                continue
            primitiva = _primitiva_de(accion_id, catalogo_acciones)
            if primitiva not in _PRIMITIVAS_VALIDAS:
                error(
                    "accion_desconocida",
                    f"El efecto '{etiqueta}' referencia '{accion_id}', que no es acción del catálogo ni primitiva del motor.",
                )
                continue
            params = _as_dict(accion.get("parametros")) or accion
            recurso = _recurso_exigido(primitiva, params)
            if recurso and recursos_validos is not None and recurso.lower() not in recursos_validos:
                error(
                    "recurso_inexistente",
                    f"El efecto '{etiqueta}' ({accion_id}) opera sobre '{recurso}', que no es un recurso del universo.",
                )
            if primitiva == "modificar_afinidad" and params.get("destino") == "personaje" \
                    and not params.get("personaje_id"):
                error(
                    "afinidad_sin_personaje",
                    f"El efecto '{etiqueta}' modifica afinidad de un personaje sin decir cuál.",
                )

            tags_de_accion: List[Any] = []
            if primitiva in ("otorgar_tag", "remover_tag"):
                tags_de_accion.append(params.get("tag"))
            elif primitiva == "mutar_estado_entidad" \
                    and (_crudo(params.get("entidad")) or "").lower() == "tag":
                tags_de_accion.append(params.get("id_entidad") or params.get("tag"))
            for tag in tags_de_accion:
                tag_id = _crudo(tag)
                if not tag_id:
                    error(
                        "tag_sin_id",
                        f"El efecto '{etiqueta}' ({accion_id}) opera sobre tags sin declarar cuál.",
                    )
                elif tags_validos is not None and tag_id not in tags_validos:
                    error(
                        "tag_inexistente",
                        f"El efecto '{etiqueta}' ({accion_id}) usa el tag '{tag_id}', que no existe en el catálogo del universo.",
                    )

    return hallazgos


def validar_grafo(
    grafo: Any,
    tipo: str = "evento",
    *,
    recursos_validos: Optional[Set[str]] = None,
    catalogo_acciones: Optional[Dict[str, Any]] = None,
    catalogo_frecuencias: Optional[Dict[str, Any]] = None,
    tags_validos: Optional[Set[str]] = None,
) -> ResultadoValidacion:
    """
    Valida la estructura de un evento, conversación o evento especial V2.

    Los catálogos son opcionales: sin ellos la validación es puramente estructural.
    Con ellos, además se rechaza contenido que el motor ejecutaría en silencio
    (recursos inexistentes, acciones o frecuencias fuera del catálogo del universo).
    """
    doc = _as_dict(grafo)
    grafo_id = doc.get("_id") or doc.get("id")
    resultado = ResultadoValidacion(tipo=tipo, grafo_id=grafo_id)

    def error(codigo: str, mensaje: str, nodo_id: Optional[str] = None, opcion_id: Optional[str] = None) -> None:
        resultado.errores.append(Hallazgo(codigo, mensaje, nodo_id, opcion_id))

    def advertencia(codigo: str, mensaje: str, nodo_id: Optional[str] = None, opcion_id: Optional[str] = None) -> None:
        resultado.advertencias.append(Hallazgo(codigo, mensaje, nodo_id, opcion_id))

    if tipo not in TIPOS_VALIDOS:
        error("tipo_invalido", f"Tipo de grafo desconocido: '{tipo}'.")
        return resultado

    if tipo == "evento_especial":
        if not (doc.get("personaje_id") or "").strip():
            error("personaje_id_ausente", "Un evento especial requiere 'personaje_id'.")
        direccion = doc.get("direccion")
        if direccion not in _DIRECCIONES_VALIDAS:
            error("direccion_invalida", f"Dirección inválida: '{direccion}'. Esperado lealtad o traicion.")

    if tipo == "evento" and grafo_id:
        if grafo_id in (doc.get("requisitos_eventos_previos") or []):
            error("requisito_autorreferente", "El evento se exige a sí mismo como requisito previo.")

    nodos_crudos = doc.get("nodos") or {}
    if not isinstance(nodos_crudos, dict) or not nodos_crudos:
        error("nodos_vacios", "El grafo no tiene nodos.")
        return resultado

    nodos: Dict[str, Dict[str, Any]] = {}
    for clave, nodo_crudo in nodos_crudos.items():
        nodo = _as_dict(nodo_crudo)
        nodos[str(clave)] = nodo
        nodo_id = nodo.get("id")
        if not nodo_id:
            error("nodo_sin_id", f"El nodo '{clave}' no declara 'id'.", nodo_id=str(clave))
        elif nodo_id != clave:
            error(
                "id_nodo_inconsistente",
                f"La clave '{clave}' no coincide con el id '{nodo_id}'.",
                nodo_id=str(clave),
            )

    raiz = doc.get("nodo_raiz")
    if not raiz:
        error("nodo_raiz_ausente", "El grafo no declara 'nodo_raiz'.")
    elif raiz not in nodos:
        error("nodo_raiz_inexistente", f"El nodo raíz '{raiz}' no existe.", nodo_id=raiz)

    opciones_vistas: Set[str] = set()

    for clave, nodo in nodos.items():
        es_final = bool(nodo.get("es_final"))
        opciones = [_as_dict(o) for o in (nodo.get("opciones") or [])]

        if es_final and opciones:
            error("nodo_final_con_opciones", "Un nodo final no puede ofrecer opciones.", nodo_id=clave)
        if not es_final and not opciones:
            error("nodo_sin_opciones", "Un nodo no final debe ofrecer al menos una opción.", nodo_id=clave)
        if es_final and not (nodo.get("resultado_texto") or "").strip():
            advertencia("nodo_final_sin_texto", "El nodo final no tiene resultado_texto.", nodo_id=clave)

        for impacto in (_as_dict(i) for i in (nodo.get("impactos_recursos") or [])):
            recurso = _crudo(impacto.get("recurso"))
            if recurso and recursos_validos is not None and recurso.lower() not in recursos_validos:
                error(
                    "recurso_inexistente",
                    f"'{recurso}' no es un recurso del universo; el motor descarta el impacto.",
                    nodo_id=clave,
                )

        for tag in (nodo.get("impactos_tags") or []):
            hallazgos_de_tag = hallazgos_de_tags_referenciados([tag], tags_validos=tags_validos)
            for hallazgo in hallazgos_de_tag:
                error(hallazgo.codigo, hallazgo.mensaje, nodo_id=clave)

        desenlace = _crudo(nodo.get("tipo_desenlace"))
        if desenlace is not None and desenlace not in _TIPOS_DESENLACE_VALIDOS:
            error(
                "tipo_desenlace_invalido",
                f"tipo_desenlace '{desenlace}' desconocido; esperado uno de {sorted(_TIPOS_DESENLACE_VALIDOS)}.",
                nodo_id=clave,
            )

        efectos = [_as_dict(e) for e in (nodo.get("efectos") or [])]
        if efectos and not es_final:
            error(
                "efectos_en_nodo_no_final",
                "Los efectos sólo se despachan en el nodo final; acá quedarían inactivos.",
                nodo_id=clave,
            )
        resultado.errores.extend(hallazgos_de_efectos(
            efectos,
            recursos_validos=recursos_validos,
            catalogo_acciones=catalogo_acciones,
            catalogo_frecuencias=catalogo_frecuencias,
            tags_validos=tags_validos,
            nodo_id=clave,
        ))

        for opt in opciones:
            opcion_id = opt.get("id")
            if not opcion_id:
                error("opcion_sin_id", "Una opción no declara 'id'.", nodo_id=clave)
                continue
            if opcion_id in opciones_vistas:
                error("opcion_duplicada", f"La opción '{opcion_id}' está repetida.", nodo_id=clave, opcion_id=opcion_id)
            opciones_vistas.add(opcion_id)

            siguiente = opt.get("siguiente_nodo")
            desenlaces = [_as_dict(d) for d in (opt.get("desenlaces") or [])]

            if not siguiente and not desenlaces:
                error("opcion_sin_destino", "La opción no apunta a ningún nodo.", nodo_id=clave, opcion_id=opcion_id)
            if siguiente and desenlaces:
                advertencia(
                    "opcion_con_destino_y_desenlaces",
                    "La opción define 'siguiente_nodo' y 'desenlaces'; se usará el sorteo ponderado.",
                    nodo_id=clave,
                    opcion_id=opcion_id,
                )
            if siguiente and siguiente not in nodos:
                error(
                    "referencia_inexistente",
                    f"'siguiente_nodo' apunta a '{siguiente}', que no existe.",
                    nodo_id=clave,
                    opcion_id=opcion_id,
                )

            if desenlaces:
                suma_pesos = 0.0
                for desenlace in desenlaces:
                    destino = desenlace.get("nodo")
                    if not destino:
                        error("desenlace_sin_nodo", "Un desenlace no declara 'nodo'.", nodo_id=clave, opcion_id=opcion_id)
                        continue
                    if destino not in nodos:
                        error(
                            "referencia_inexistente",
                            f"El desenlace apunta a '{destino}', que no existe.",
                            nodo_id=clave,
                            opcion_id=opcion_id,
                        )
                    try:
                        peso = float(desenlace.get("peso", 1.0))
                    except (TypeError, ValueError):
                        error("peso_invalido", f"Peso no numérico para '{destino}'.", nodo_id=clave, opcion_id=opcion_id)
                        continue
                    if peso <= 0:
                        error("peso_no_positivo", f"Peso no positivo para '{destino}'.", nodo_id=clave, opcion_id=opcion_id)
                    else:
                        suma_pesos += peso
                if suma_pesos <= 0:
                    error(
                        "desenlaces_sin_peso_positivo",
                        "Ningún desenlace tiene peso positivo; el sorteo no puede resolverse.",
                        nodo_id=clave,
                        opcion_id=opcion_id,
                    )

            modo = opt.get("bloqueo_modo", "deshabilitada")
            if modo not in _MODOS_BLOQUEO_VALIDOS:
                advertencia(
                    "bloqueo_modo_desconocido",
                    f"bloqueo_modo '{modo}' desconocido; se tratará como 'deshabilitada'.",
                    nodo_id=clave,
                    opcion_id=opcion_id,
                )

    if raiz in nodos:
        if bool(nodos[raiz].get("es_final")):
            error("raiz_es_final", "El nodo raíz no puede ser un nodo final.", nodo_id=raiz)

        ciclo = _detectar_ciclo(nodos, raiz)
        if ciclo:
            error("ciclo_detectado", f"El grafo contiene un ciclo alcanzable en '{ciclo}'.", nodo_id=ciclo)

        alcanzables = _alcanzables(nodos, raiz)
        if not any(bool(nodos[n].get("es_final")) for n in alcanzables):
            error("sin_final_alcanzable", "No hay ningún nodo final alcanzable desde la raíz.", nodo_id=raiz)
        for nodo_id in sorted(set(nodos) - alcanzables):
            advertencia("nodo_inalcanzable", "El nodo no es alcanzable desde la raíz.", nodo_id=nodo_id)

    return resultado


async def validar_grafo_para_guardado(
    grafo: Any,
    tipo: str = "evento",
    db=None,
) -> ResultadoValidacion:
    """
    Valación completa de un grafo antes de persistirlo: estructura más catálogo del universo.
    Sin este contexto el motor ejecutaría en silencio recursos o frecuencias inexistentes.
    """
    doc = _as_dict(grafo)
    if db is None:
        from app.core.database import get_database

        db = get_database()

    contexto = await _cargar_contexto_universo(str(doc.get("universo_id") or "corte_medieval"), db)
    return validar_grafo(doc, tipo, **contexto)


async def validar_efectos_almacenables(
    efectos: Sequence[Any],
    universo_id: str,
    db=None,
    *,
    tags: Sequence[Any] = (),
    condiciones_aparicion: Sequence[Any] = (),
) -> List[Hallazgo]:
    """
    Barato de pasar en cada guardado de carta o personaje: usa los mismos catálogos
    que el motor carga en la partida, así que lo que se rechaza acá es lo que en el
    juego se ejecutaría en silencio.
    """
    if db is None:
        from app.core.database import get_database

        db = get_database()

    contexto = await _cargar_contexto_universo(str(universo_id), db)
    hallazgos = hallazgos_de_efectos(efectos, **contexto)
    hallazgos.extend(hallazgos_de_tags_referenciados(
        tags,
        condiciones_aparicion,
        tags_validos=contexto["tags_validos"],
    ))
    return hallazgos


async def _cargar_contexto_universo(universo_id: str, db) -> Dict[str, Any]:
    from app.features.narrative.game.universe_resources import obtener_mapa_recursos_universo
    from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo

    recursos_mapa = await obtener_mapa_recursos_universo(universo_id)
    acciones, frecuencias = await obtener_catalogos_universo(universo_id, db)
    tags_docs = await db[COLL_TAGS].find({"universo_id": universo_id}, {"_id": 1}).to_list(None)
    return {
        "recursos_validos": {str(clave).lower() for clave in recursos_mapa},
        "catalogo_acciones": acciones,
        "catalogo_frecuencias": frecuencias,
        "tags_validos": {str(doc["_id"]) for doc in tags_docs},
    }


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
        cursor = db[_COLECCION_POR_TIPO[tipo]].find(query).limit(limite)
        async for documento in cursor:
            universo = str(documento.get("universo_id") or "corte_medieval")
            if universo not in contextos:
                contextos[universo] = await _cargar_contexto_universo(universo, db)
            resultados.append(validar_grafo(documento, tipo, **contextos[universo]))
    return resultados
