"""
actions_catalog_meta.py
Metadatos canónicos de primitivas y eventos del motor narrativo, frecuencias por defecto
y consultas de integridad referencial (usos de acciones y frecuencias).
"""

from typing import Any, Dict, List, Optional

from app.core.database import get_database
from app.features.narrative.constants import COLL_CARDS, COLL_CHARACTERS
from app.features.narrative.schemas.rules_schemas import PrimitivaOperacionEnum

# Catálogo canónico de primitivas soportadas por el motor
CATALOGO_PRIMITIVAS: List[Dict[str, Any]] = [
    {
        "primitiva": PrimitivaOperacionEnum.MODIFICAR_RECURSO.value,
        "nombre": "Modificar recurso",
        "descripcion": "Aumenta o disminuye el valor de un recurso numérico del universo (positivo suma, negativo resta).",
        "parametros_requeridos": ["clave", "valor", "tipo_calculo"],
        "soporta_calculo": ["fijo", "porcentual"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.MODIFICAR_AFINIDAD.value,
        "nombre": "Modificar afinidad",
        "descripcion": "Modifica la afinidad (0 a 100) con el personaje portador o uno específico.",
        "parametros_requeridos": ["destino", "valor"],
        "opciones_destino": ["portador", "personaje"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.OTORGAR_TAG.value,
        "nombre": "Otorgar tag pasivo",
        "descripcion": "Otorga un tag pasivo permanente al estado vivo de la partida.",
        "parametros_requeridos": ["tag"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.REMOVER_TAG.value,
        "nombre": "Remover tag",
        "descripcion": "Remueve un tag activo del estado de la partida.",
        "parametros_requeridos": ["tag"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.AMORTIGUAR_DANIO.value,
        "nombre": "Amortiguar daño de recurso",
        "descripcion": "Registra un modificador pasivo que reduce porcentualmente las pérdidas de un recurso.",
        "parametros_requeridos": ["clave", "valor"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO_ENTIDAD.value,
        "nombre": "Mutar estado de entidad (Tag o Personaje)",
        "descripcion": "Agrega o quita un tag del estado de la partida, o recluta/retira un personaje de la corte. Al retirar un personaje se eliminan sus modificadores pasivos y los tags que otorgó.",
        "parametros_requeridos": ["entidad", "operacion", "id_entidad"],
        "opciones_entidad": ["tag", "personaje"],
        "opciones_operacion": ["alta", "baja"],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
    {
        "primitiva": PrimitivaOperacionEnum.MUTAR_ESTADO.value,
        "nombre": "Mutar estado genérico",
        "descripcion": "Mutación matemática sobre recursos, límites dinámicos, afinidades o variables con soporte aditivo, multiplicativo, divisorio, porcentual o fijado.",
        "parametros_requeridos": ["ruta", "operacion_matematica", "valor"],
        "soporta_operaciones": ["sumar", "restar", "multiplicar", "dividir", "porcentual", "fijar"],
        "ejemplos_rutas": [
            "recursos.<clave>",
            "limites.<clave>.max",
            "limites.<clave>.min",
            "afinidad.<target>",
            "variables.<clave>",
        ],
        "permitido_en": ["carta", "personaje", "nodo"],
    },
]

# Eventos que el motor realmente despacha; el panel sólo ofrece lo ejecutable.
EVENTOS_MOTOR: List[Dict[str, Any]] = [
    {
        "evento_motor": "al_obtener",
        "nombre": "Al obtener",
        "descripcion": "Se ejecuta de inmediato cuando la carta entra en mano o el personaje es reclutado.",
        "soporta_intervalo": False,
    },
    {
        "evento_motor": "inicio_mes",
        "nombre": "Inicio de cada mes",
        "descripcion": "Se evalúa al inicio de cada mes. Puede configurarse periodicidad (ej. cada 1, 2 meses) relativa a la adquisición.",
        "soporta_intervalo": True,
        "opciones_conteo": ["adquisicion", "inicio_partida"],
    },
    {
        "evento_motor": "al_desenlace",
        "nombre": "Al cerrar el desenlace",
        "descripcion": "Se ejecuta sobre los efectos declarados en el nodo final del grafo, appena se aplican sus impactos.",
        "soporta_intervalo": False,
    },
    {
        "evento_motor": "en_evento_positivo",
        "nombre": "Tras desenlace positivo",
        "descripcion": "Reacción de cartas y corte cuando el desenlace del grafo se declara positivo.",
        "soporta_intervalo": False,
    },
    {
        "evento_motor": "en_evento_negativo",
        "nombre": "Tras desenlace negativo",
        "descripcion": "Reacción de cartas y corte cuando el desenlace del grafo se declara negativo.",
        "soporta_intervalo": False,
    },
]


def _frecuencias_default(universo_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": "al_obtener",
            "nombre": "Al obtener",
            "evento_motor": "al_obtener",
            "cada": 1,
            "desfase": 0,
            "conteo_desde": "adquisicion",
            "activo": True,
        },
        {
            "id": "mensual",
            "nombre": "Cada mes",
            "evento_motor": "inicio_mes",
            "cada": 1,
            "desfase": 0,
            "conteo_desde": "inicio_partida",
            "activo": True,
        },
        {
            "id": "cada_2_meses",
            "nombre": "Cada 2 meses desde adquisición",
            "evento_motor": "inicio_mes",
            "cada": 2,
            "desfase": 0,
            "conteo_desde": "adquisicion",
            "activo": True,
        },
    ]


def _serializar_usos(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"id": str(d["_id"]), "nombre": d.get("nombre", str(d["_id"])), "universo_id": d.get("universo_id")}
        for d in docs
    ]


async def _consultar_usos_entidad(
    clave_id: str, valor_id: str, filtro: Dict[str, Any]
) -> Dict[str, Any]:
    db = get_database()
    proyeccion = {"_id": 1, "nombre": 1, "universo_id": 1}
    cartas = await db[COLL_CARDS].find(filtro, proyeccion).to_list(None)
    personajes = await db[COLL_CHARACTERS].find(filtro, proyeccion).to_list(None)
    return {
        clave_id: valor_id,
        "total_usos": len(cartas) + len(personajes),
        "cartas": _serializar_usos(cartas),
        "personajes": _serializar_usos(personajes),
    }


async def obtener_usos_accion(accion_id: str) -> Dict[str, Any]:
    return await _consultar_usos_entidad(
        "accion_id",
        accion_id,
        {"$or": [{"efectos.acciones.accion_id": accion_id}, {"efectos.accion.tipo": accion_id}]},
    )


async def obtener_usos_frecuencia(frecuencia_id: str, universo_id: Optional[str] = None) -> Dict[str, Any]:
    filtro: Dict[str, Any] = {
        "$or": [{"efectos.frecuencia_id": frecuencia_id}, {"efectos.disparador": frecuencia_id}]
    }
    if universo_id:
        filtro["universo_id"] = universo_id
    return await _consultar_usos_entidad("frecuencia_id", frecuencia_id, filtro)
