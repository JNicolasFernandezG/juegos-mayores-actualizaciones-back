"""Consejos del perfil respaldados por fuentes, administrables desde la Torre de Control.

Viven en Mongo para poder sumar nuevos sin deploy. La siembra inicial solo corre con
la colección vacía: nunca pisa ediciones ni revive consejos borrados a mano.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, get_args

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database

from .schemas import ConsejoAdmin, ConsejoPerfil, ConsejoUpsert, SituacionConsejo

COLL_CONSEJOS = "consejos_perfil"
SITUACIONES = get_args(SituacionConsejo)

CONSEJOS_DEFAULT: List[Dict[str, Any]] = [
    {
        "_id": "estimulacion-mental-alzheimer",
        "texto": (
            "Actividades que estimulan la mente se asociaron con menor riesgo de "
            "Alzheimer en adultos mayores."
        ),
        "fuente": "Wilson et al., JAMA, 2002",
        "url": "https://doi.org/10.1001/jama.287.6.742",
        "orden": 10,
    },
    {
        "_id": "aprender-habilidades-nuevas",
        "texto": (
            "Aprender habilidades nuevas mejoró la memoria en adultos mayores más "
            "que las actividades rutinarias."
        ),
        "fuente": "Park et al., Psychological Science, 2014",
        "url": "https://doi.org/10.1177/0956797613504966",
        "orden": 20,
        "situacion": "mes_en_mejora",
    },
    {
        "_id": "entrenar-una-capacidad",
        "texto": (
            "Entrenar una capacidad mejora sobre todo esa capacidad: conviene "
            "alternar lógica, lenguaje y atención."
        ),
        "fuente": "Ball et al., JAMA, 2002",
        "url": "https://doi.org/10.1001/jama.288.18.2271",
        "orden": 30,
        "situacion": "eje_desequilibrado",
    },
    {
        "_id": "reserva-cognitiva",
        "texto": (
            "La reserva cognitiva se construye a lo largo de la vida con educación "
            "y actividades mentales sostenidas."
        ),
        "fuente": "Stern, Lancet Neurology, 2012",
        "url": "https://doi.org/10.1016/S1474-4422(12)70191-6",
        "orden": 40,
        "situacion": "racha_reanudada",
    },
]


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _situacion(doc: Dict[str, Any]) -> Optional[str]:
    """Un valor viejo o corrupto no debe romper el resumen: se descarta."""
    valor = doc.get("situacion")
    return valor if valor in SITUACIONES else None


def _serializar(doc: Dict[str, Any]) -> ConsejoAdmin:
    return ConsejoAdmin(
        id=str(doc.get("_id", "")),
        texto=str(doc.get("texto") or ""),
        fuente=str(doc.get("fuente") or ""),
        url=str(doc.get("url") or ""),
        situacion=_situacion(doc),
        orden=int(doc.get("orden") or 0),
        activo=doc.get("activo", True) is not False,
        updated_at=doc.get("updated_at"),
    )


def _filtro_por_id(consejo_id: str) -> Dict[str, Any]:
    if ObjectId.is_valid(consejo_id):
        return {"_id": ObjectId(consejo_id)}
    return {"_id": consejo_id}


def _no_encontrado(consejo_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Consejo '{consejo_id}' no encontrado.",
    )


async def asegurar_consejos_default() -> int:
    """Siembra los consejos base solo con la colección vacía."""
    coleccion = get_database()[COLL_CONSEJOS]
    if await coleccion.count_documents({}) > 0:
        return 0
    ahora = _ahora_iso()
    docs = [{**consejo, "activo": True, "updated_at": ahora} for consejo in CONSEJOS_DEFAULT]
    try:
        await coleccion.insert_many(docs)
    except DuplicateKeyError:
        # Otra instancia sembró entre el conteo y el insert: el resultado buscado ya está.
        return 0
    return len(docs)


async def listar_consejos(*, solo_activos: bool) -> List[ConsejoAdmin]:
    query: Dict[str, Any] = {"activo": {"$ne": False}} if solo_activos else {}
    docs = await get_database()[COLL_CONSEJOS].find(query).sort(
        [("orden", 1), ("_id", 1)]
    ).to_list(length=None)
    return [_serializar(doc) for doc in docs]


async def consejos_para_perfil() -> List[ConsejoPerfil]:
    activos = await listar_consejos(solo_activos=True)
    return [
        ConsejoPerfil(
            id=consejo.id,
            texto=consejo.texto,
            fuente=consejo.fuente,
            url=consejo.url,
            situacion=consejo.situacion,
        )
        for consejo in activos
    ]


async def crear_consejo(req: ConsejoUpsert) -> ConsejoAdmin:
    doc: Dict[str, Any] = {
        **req.model_dump(),
        "updated_at": _ahora_iso(),
    }
    resultado = await get_database()[COLL_CONSEJOS].insert_one(doc)
    doc["_id"] = resultado.inserted_id
    return _serializar(doc)


async def actualizar_consejo(consejo_id: str, req: ConsejoUpsert) -> ConsejoAdmin:
    cambios = {**req.model_dump(), "updated_at": _ahora_iso()}
    doc = await get_database()[COLL_CONSEJOS].find_one_and_update(
        _filtro_por_id(consejo_id),
        {"$set": cambios},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise _no_encontrado(consejo_id)
    return _serializar(doc)


async def eliminar_consejo(consejo_id: str) -> Dict[str, Any]:
    resultado = await get_database()[COLL_CONSEJOS].delete_one(_filtro_por_id(consejo_id))
    if resultado.deleted_count == 0:
        raise _no_encontrado(consejo_id)
    return {"success": True, "message": f"Consejo '{consejo_id}' eliminado."}
