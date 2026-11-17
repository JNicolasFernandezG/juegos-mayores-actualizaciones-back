"""
effects_validator.py
Validación estática y contra catálogos de efectos ECA y tags referenciados en nodos,
cartas y personajes del motor narrativo V2.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from app.features.narrative.constants import COLL_TAGS
from app.features.narrative.schemas.rules_schemas import PrimitivaOperacionEnum

_PRIMITIVAS_VALIDAS = {p.value for p in PrimitivaOperacionEnum}

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
    return dump(by_alias=True) if callable(dump) else {}


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
            return Hallazgo("tag_inexistente", f"El tag '{tag_id}' no existe en el catálogo del universo.")
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


def _validar_tags_accion(
    primitiva: str,
    params: Dict[str, Any],
    etiqueta: str,
    accion_id: str,
    tags_validos: Optional[Set[str]],
    nodo_id: Optional[str],
) -> List[Hallazgo]:
    tags_de_accion: List[Any] = []
    if primitiva in ("otorgar_tag", "remover_tag"):
        tags_de_accion.append(params.get("tag"))
    elif primitiva == "mutar_estado_entidad" and (_crudo(params.get("entidad")) or "").lower() == "tag":
        tags_de_accion.append(params.get("id_entidad") or params.get("tag"))

    hallazgos: List[Hallazgo] = []
    for tag in tags_de_accion:
        tag_id = _crudo(tag)
        if not tag_id:
            hallazgos.append(Hallazgo("tag_sin_id", f"El efecto '{etiqueta}' ({accion_id}) opera sobre tags sin declarar cuál.", nodo_id))
        elif tags_validos is not None and tag_id not in tags_validos:
            hallazgos.append(Hallazgo(
                "tag_inexistente",
                f"El efecto '{etiqueta}' ({accion_id}) usa el tag '{tag_id}', que no existe en el catálogo del universo.",
                nodo_id,
            ))
    return hallazgos


def _validar_accion_efecto(
    accion: Dict[str, Any],
    etiqueta: str,
    *,
    recursos_validos: Optional[Set[str]],
    catalogo_acciones: Optional[Dict[str, Any]],
    tags_validos: Optional[Set[str]],
    nodo_id: Optional[str],
) -> List[Hallazgo]:
    accion_id = _crudo(accion.get("accion_id") or accion.get("tipo"))
    if not accion_id:
        return [Hallazgo("accion_sin_id", f"El efecto '{etiqueta}' tiene una acción sin identificador.", nodo_id)]

    primitiva = _primitiva_de(accion_id, catalogo_acciones)
    if primitiva not in _PRIMITIVAS_VALIDAS:
        return [Hallazgo(
            "accion_desconocida",
            f"El efecto '{etiqueta}' referencia '{accion_id}', que no es acción del catálogo ni primitiva del motor.",
            nodo_id,
        )]

    hallazgos: List[Hallazgo] = []
    params = _as_dict(accion.get("parametros")) or accion
    recurso = _recurso_exigido(primitiva, params)
    if recurso and recursos_validos is not None and recurso.lower() not in recursos_validos:
        hallazgos.append(Hallazgo(
            "recurso_inexistente",
            f"El efecto '{etiqueta}' ({accion_id}) opera sobre '{recurso}', que no es un recurso del universo.",
            nodo_id,
        ))
    if primitiva == "modificar_afinidad" and params.get("destino") == "personaje" and not params.get("personaje_id"):
        hallazgos.append(Hallazgo("afinidad_sin_personaje", f"El efecto '{etiqueta}' modifica afinidad de un personaje sin decir cuál.", nodo_id))
    hallazgos.extend(_validar_tags_accion(primitiva, params, etiqueta, accion_id, tags_validos, nodo_id))
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
    """Errores de efectos ECA declarados en un nodo, una carta o un personaje."""
    hallazgos: List[Hallazgo] = []
    for indice, crudo in enumerate(efectos or []):
        efecto = _as_dict(crudo)
        etiqueta = efecto.get("id") or f"índice {indice}"

        evento = _crudo(efecto.get("frecuencia_id") or efecto.get("disparador"))
        if not evento:
            hallazgos.append(Hallazgo("efecto_sin_evento", f"El efecto '{etiqueta}' no declara frecuencia ni disparador.", nodo_id))
        elif catalogo_frecuencias is not None and evento not in _EVENTOS_MOTOR and not catalogo_frecuencias.get(evento):
            hallazgos.append(Hallazgo(
                "evento_no_despachado",
                f"El efecto '{etiqueta}' usa '{evento}': el motor no lo emite y no está activo en el catálogo de frecuencias.",
                nodo_id,
            ))

        hallazgos.extend(hallazgos_de_tags_referenciados(condiciones=efecto.get("condiciones") or [], tags_validos=tags_validos))
        acciones = [_as_dict(a) for a in (efecto.get("acciones") or [])]
        if efecto.get("accion"):
            acciones.append(_as_dict(efecto["accion"]))
        if not acciones:
            hallazgos.append(Hallazgo("efecto_sin_acciones", f"El efecto '{etiqueta}' no ejecuta ninguna acción.", nodo_id))

        for accion in acciones:
            hallazgos.extend(_validar_accion_efecto(
                accion, etiqueta, recursos_validos=recursos_validos,
                catalogo_acciones=catalogo_acciones, tags_validos=tags_validos, nodo_id=nodo_id,
            ))
    return hallazgos


async def _cargar_contexto_universo(universo_id: str, db) -> Dict[str, Any]:
    from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
    from app.features.narrative.game.universe_resources import obtener_mapa_recursos_universo

    recursos_mapa = await obtener_mapa_recursos_universo(universo_id)
    acciones, frecuencias = await obtener_catalogos_universo(universo_id, db)
    tags_docs = await db[COLL_TAGS].find({"universo_id": universo_id}, {"_id": 1}).to_list(None)
    return {
        "recursos_validos": {str(clave).lower() for clave in recursos_mapa},
        "catalogo_acciones": acciones,
        "catalogo_frecuencias": frecuencias,
        "tags_validos": {str(doc["_id"]) for doc in tags_docs},
    }


async def validar_efectos_almacenables(
    efectos: Sequence[Any],
    universo_id: str,
    db=None,
    *,
    tags: Sequence[Any] = (),
    condiciones_aparicion: Sequence[Any] = (),
) -> List[Hallazgo]:
    """Valida efectos y tags antes de guardar una carta o personaje usando los catálogos del universo."""
    if db is None:
        from app.core.database import get_database
        db = get_database()

    contexto = await _cargar_contexto_universo(str(universo_id), db)
    hallazgos = hallazgos_de_efectos(efectos, **contexto)
    hallazgos.extend(hallazgos_de_tags_referenciados(tags, condiciones_aparicion, tags_validos=contexto["tags_validos"]))
    return hallazgos
