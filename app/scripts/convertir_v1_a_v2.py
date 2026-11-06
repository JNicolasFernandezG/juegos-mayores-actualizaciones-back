"""
convertir_v1_a_v2.py
Convierte los eventos y conversaciones planos de V1 en grafos V2 equivalentes.

Existe para poder retirar el motor V1 sin perder el contenido ya escrito: V1 resuelve
"opción -> sorteo de resultado", que es un grafo de dos niveles, así que la conversión
es mecánica y conserva el balance (pesos, modificadores condicionales, efectos y afinidad).

Es idempotente y no destructivo por defecto: escribe ids derivados (``<id_v1><suffix>``) con
``$setOnInsert`` y nunca toca los grafos V2 escritos a mano. No se ejecuta en el arranque;
se corre a mano, con ``--dry-run`` primero.

    python -m app.scripts.convertir_v1_a_v2 --dry-run
    python -m app.scripts.convertir_v1_a_v2 --universo corte_medieval
"""

import argparse
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from app.core.database import connect_to_mongo, get_database
from app.features.narrative.constants import (
    COLL_CONVERSATIONS,
    COLL_EVENTS,
    COLL_RESULTS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTS,
)
from app.features.narrative.schemas.v2_graph_schemas import (
    ConversacionV2GrafoSchema,
    EventoV2GrafoSchema,
)
from app.features.narrative.validation import validar_grafo_para_guardado

logger = logging.getLogger(__name__)

NODO_RAIZ = "nodo_inicio"

# Los efectos V1 "al_obtener" son, en V2, la consecuencia estática del nodo final.
_PRIMITIVAS_DE_IMPACTO = {"modificar_recurso", "modificar_afinidad", "otorgar_tag"}


def _nodo_base(nodo_id: str, hablante: str, texto: str, *, es_final: bool = False) -> Dict[str, Any]:
    return {
        "id": nodo_id,
        "hablante_id": hablante,
        "texto": texto,
        "es_final": es_final,
        "opciones": [],
        "resultado_texto": "",
        "impactos_recursos": [],
        "impactos_afinidad": [],
        "impactos_tags": [],
    }


def _opcion(op_id: str, texto: str, **extra) -> Dict[str, Any]:
    opcion = {
        "id": op_id,
        "texto": texto,
        "siguiente_nodo": None,
        "desenlaces": [],
        "condiciones": [],
        "bloqueo_modo": "deshabilitada",
    }
    opcion.update(extra)
    return opcion


def _impactos_de_obtencion(efectos: List[Dict[str, Any]]) -> Tuple[List[dict], List[dict], List[str], List[dict]]:
    """
    Separa los efectos ``al_obtener`` de V1 en impactos del nodo final y conserva el resto
    como efectos ECA intactos, para que el despachador los siga ejecutando en V2.
    """
    recursos: List[dict] = []
    afinidad: List[dict] = []
    tags: List[str] = []
    restantes: List[dict] = []

    for efecto in efectos or []:
        accion = efecto.get("accion") or {}
        tipo = str(accion.get("tipo") or "")
        evento = str(efecto.get("frecuencia_id") or efecto.get("disparador") or "al_obtener")

        if evento != "al_obtener" or tipo not in _PRIMITIVAS_DE_IMPACTO:
            restantes.append(efecto)
            continue

        if tipo == "modificar_recurso":
            recursos.append({"recurso": accion.get("clave"), "delta": int(float(accion.get("valor") or 0))})
        elif tipo == "modificar_afinidad":
            afinidad.append(
                {"personaje_id": accion.get("personaje_id"), "delta": int(float(accion.get("valor") or 0))}
            )
        else:
            tags.append(str(accion.get("tag")))

    return recursos, afinidad, [t for t in tags if t], restantes


def _nodo_final(resultado: Dict[str, Any]) -> Dict[str, Any]:
    clave = f"fin_{resultado['_id']}"
    nodo = _nodo_base(clave, "narrador", resultado.get("titulo") or resultado["_id"], es_final=True)
    recursos, afinidad, tags, restantes = _impactos_de_obtencion(resultado.get("efectos") or [])
    for impacto in resultado.get("impacto_afinidad") or []:
        afinidad.append({"personaje_id": impacto.get("personaje_id"), "delta": int(impacto.get("delta") or 0)})

    nodo["resultado_texto"] = resultado.get("texto") or resultado.get("titulo") or ""
    nodo["imagen"] = resultado.get("imagen")
    nodo["impactos_recursos"] = recursos
    nodo["impactos_afinidad"] = afinidad
    nodo["impactos_tags"] = tags
    nodo["tipo_desenlace"] = resultado.get("tipo_resultado") or "neutro"
    nodo["efectos"] = restantes
    return nodo


def convertir_evento(evt: Dict[str, Any], resultados: Dict[str, Dict[str, Any]]) -> Tuple[Optional[dict], List[str]]:
    """Arma el grafo V2 de un evento V1. Devuelve (grafo, avisos no bloqueantes)."""
    avisos: List[str] = []
    nodos: Dict[str, Dict[str, Any]] = {
        NODO_RAIZ: _nodo_base(NODO_RAIZ, "narrador", evt.get("descripcion") or evt.get("titulo") or "")
    }

    for op in evt.get("opciones") or []:
        posibles = op.get("resultados_posibles") or []
        validos: List[dict] = []
        for rp in posibles:
            res_id = str(rp.get("resultado_id"))
            if res_id not in resultados:
                avisos.append(f"opción '{op.get('id')}': el resultado '{res_id}' no está en el catálogo V1.")
                continue
            clave = f"fin_{res_id}"
            if clave not in nodos:
                nodos[clave] = _nodo_final(resultados[res_id])
            validos.append(rp)

        if not validos:
            avisos.append(f"opción '{op.get('id')}': sin desenlaces resolubles, se descarta del grafo.")
            continue

        modo = "oculta" if op.get("es_secreta") else "deshabilitada"
        condiciones = op.get("condiciones") or []
        if len(validos) == 1:
            opcion = _opcion(
                op["id"], op.get("texto") or "",
                siguiente_nodo=f"fin_{validos[0]['resultado_id']}",
                bloqueo_modo=modo, condiciones=condiciones,
            )
        else:
            opcion = _opcion(
                op["id"], op.get("texto") or "",
                bloqueo_modo=modo, condiciones=condiciones,
                desenlaces=[
                    {
                        "nodo": f"fin_{rp['resultado_id']}",
                        "peso": float(rp.get("peso_base", 50.0)),
                        "modificadores_probabilidad": rp.get("modificadores_probabilidad") or [],
                    }
                    for rp in validos
                ],
            )
        nodos[NODO_RAIZ]["opciones"].append(opcion)

    if not nodos[NODO_RAIZ]["opciones"]:
        return None, ["el evento no dejó ninguna opción resoluble"]

    return {
        "_id": None,
        "universo_id": evt.get("universo_id", "corte_medieval"),
        "titulo": evt.get("titulo") or evt["_id"],
        "imagen": evt.get("imagen") or "/assets/narrative/eventos/default.webp",
        "peso_base": float(evt.get("peso_base", 100.0)),
        "tags_tematicos": evt.get("tags_tematicos") or [],
        "requisitos_eventos_previos": [],
        "requisitos_personajes": [],
        "condiciones_disparo": [],
        "nodo_raiz": NODO_RAIZ,
        "nodos": nodos,
    }, avisos


def convertir_conversacion(conv: Dict[str, Any]) -> Tuple[Optional[dict], List[str]]:
    """
    Una conversación V1 es frases encadenadas más una lista de decisiones.
    Cada frase es un nodo; el último nodo de la cadena lleva las decisiones como opciones,
    así no hace falta inventar texto ni pasos de "continuar" que el jugador ya no veía en V1.
    """
    avisos: List[str] = []
    frases = conv.get("frases") or []
    decisiones = conv.get("decisiones") or []
    if not decisiones:
        return None, ["la conversación no tiene decisiones"]

    hablante = (frases[0].get("personajeId") if frases else None) or "narrador"
    nodos: Dict[str, Dict[str, Any]] = {}

    opciones = [
        _opcion(
            f"opt_{d.get('opcion')}", d.get("texto") or "",
            siguiente_nodo=f"fin_op_{d.get('opcion')}", condiciones=d.get("condiciones") or [],
        )
        for d in decisiones
    ]
    for decision in decisiones:
        clave = f"fin_op_{decision.get('opcion')}"
        nodo = _nodo_base(clave, hablante, decision.get("resultado_texto") or "", es_final=True)
        nodo["resultado_texto"] = decision.get("resultado_texto") or ""
        nodo["impactos_afinidad"] = [
            {"personaje_id": i.get("personaje_id"), "delta": int(i.get("delta") or 0)}
            for i in (decision.get("impacto_afinidad") or [])
        ]
        nodos[clave] = nodo

    if frases:
        for i, frase in enumerate(frases):
            clave = f"frase_{i + 1}"
            nodo = _nodo_base(clave, frase.get("personajeId") or hablante, frase.get("texto") or "")
            if i + 1 < len(frases):
                nodo["opciones"] = [_opcion(f"opt_frase_{i + 1}", "Continuar", siguiente_nodo=f"frase_{i + 2}")]
            else:
                nodo["opciones"] = opciones
            nodos[clave] = nodo
        raiz = "frase_1"
    else:
        nodo = _nodo_base(NODO_RAIZ, hablante, conv.get("titulo") or "")
        nodo["opciones"] = opciones
        nodos[NODO_RAIZ] = nodo
        raiz = NODO_RAIZ
        avisos.append("la conversación V1 no tenía frases; se usó el título como nodo de decisión.")

    return {
        "_id": None,
        "universo_id": conv.get("universo_id", "corte_medieval"),
        "titulo": conv.get("titulo") or conv["_id"],
        "imagen": conv.get("imagen") or "/assets/narrative/conversation-hall.png",
        "requisitos": [r.get("personajeId") for r in (conv.get("requisitos") or []) if r.get("personajeId")],
        "condiciones_disparo": [],
        "nodo_raiz": raiz,
        "nodos": nodos,
    }, avisos


async def convertir(
    universo_id: str = "corte_medieval",
    dry_run: bool = False,
    force: bool = False,
    suffix: str = "_v2c",
    solo_eventos: Optional[List[str]] = None,
    solo_conversaciones: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convierte el contenido V1 del universo y escribe los grafos derivados que pasen la validación."""
    db = get_database()
    resultados = {d["_id"]: d for d in await db[COLL_RESULTS].find({"universo_id": universo_id}).to_list(500)}

    informe: Dict[str, Any] = {"escritos": [], "omitidos": [], "rechazados": [], "avisos": {}}

    filtro_base = {"universo_id": universo_id}
    planes = []
    filtro_evt = dict(filtro_base)
    if solo_eventos:
        filtro_evt["_id"] = {"$in": solo_eventos}
    for evt in await db[COLL_EVENTS].find(filtro_evt).to_list(500):
        grafo, avisos = convertir_evento(evt, resultados)
        planes.append(("evento", str(evt["_id"]), grafo, avisos))

    filtro_conv = dict(filtro_base)
    if solo_conversaciones:
        filtro_conv["_id"] = {"$in": solo_conversaciones}
    for conv in await db[COLL_CONVERSATIONS].find(filtro_conv).to_list(500):
        grafo, avisos = convertir_conversacion(conv)
        planes.append(("conversacion", str(conv["_id"]), grafo, avisos))

    for tipo, id_v1, grafo, avisos in planes:
        if grafo is None:
            informe["rechazados"].append(f"{tipo}/{id_v1}: {avisos[0]}")
            continue

        destino = COLL_V2_EVENTS if tipo == "evento" else COLL_V2_CONVERSATIONS
        id_v2 = f"{id_v1}{suffix}"
        grafo["_id"] = id_v2

        if await db[destino].find_one({"_id": id_v2}, {"_id": 1}) and not force:
            informe["omitidos"].append(f"{tipo}/{id_v2} (ya existe; --force para reemplazar)")
            continue

        modelo_cls = EventoV2GrafoSchema if tipo == "evento" else ConversacionV2GrafoSchema
        try:
            modelo = modelo_cls(**grafo)
        except ValidationError as exc:
            informe["rechazados"].append(f"{tipo}/{id_v2}: grafo fuera de schema -> {exc.errors()[:2]}")
            continue

        resultado = await validar_grafo_para_guardado(modelo, tipo, db)
        if not resultado.valido:
            informe["rechazados"].append(
                f"{tipo}/{id_v2}: " + "; ".join(f"[{h.codigo}] {h.mensaje}" for h in resultado.errores)
            )
            continue

        document = modelo.model_dump(by_alias=True)
        for h in resultado.advertencias:
            avisos.append(f"advertencia [{h.codigo}] {h.mensaje} (nodo {h.nodo_id})")
        if avisos:
            informe["avisos"][f"{tipo}/{id_v2}"] = avisos

        if dry_run:
            informe["escritos"].append(f"{tipo}/{id_v2} dry-run ({len(document['nodos'])} nodos)")
            continue

        if force:
            await db[destino].replace_one({"_id": id_v2}, document, upsert=True)
        else:
            await db[destino].update_one({"_id": id_v2}, {"$setOnInsert": document}, upsert=True)
        informe["escritos"].append(f"{tipo}/{id_v2} ({len(document['nodos'])} nodos)")

    return informe


def _parsear_lista(valor: Optional[str]) -> Optional[List[str]]:
    if not valor:
        return None
    return [v.strip() for v in valor.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte contenido narrativo V1 a grafos V2.")
    parser.add_argument("--universo", default="corte_medieval")
    parser.add_argument("--dry-run", action="store_true", help="Valida y reporta sin escribir")
    parser.add_argument("--force", action="store_true", help="Reemplaza los grafos derivados ya escritos")
    parser.add_argument("--suffix", default="_v2c", help="Sufijo del id V2 derivado del id V1")
    parser.add_argument("--eventos", help="Lista separada por comas de ids V1 de eventos")
    parser.add_argument("--conversaciones", help="Lista separada por comas de ids V1 de conversaciones")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def correr() -> None:
        await connect_to_mongo()
        informe = await convertir(
            universo_id=args.universo,
            dry_run=args.dry_run,
            force=args.force,
            suffix=args.suffix,
            solo_eventos=_parsear_lista(args.eventos),
            solo_conversaciones=_parsear_lista(args.conversaciones),
        )
        logger.info("=" * 72)
        logger.info("CONVERSIÓN V1 -> V2 (%s)%s", args.universo, " [dry-run]" if args.dry_run else "")
        for destino in informe["escritos"]:
            logger.info("  + %s", destino)
        for omitido in informe["omitidos"]:
            logger.info("  = %s", omitido)
        for rechazo in informe["rechazados"]:
            logger.error("  x %s", rechazo)
        for grafo_id, avisos in informe["avisos"].items():
            for aviso in avisos:
                logger.warning("  ! %s: %s", grafo_id, aviso)
        logger.info(
            "Totales: %s escritos, %s omitidos, %s rechazados",
            len(informe["escritos"]), len(informe["omitidos"]), len(informe["rechazados"]),
        )
        if informe["rechazados"]:
            raise SystemExit(1)

    asyncio.run(correr())


if __name__ == "__main__":
    main()
