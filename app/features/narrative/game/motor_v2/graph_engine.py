"""
graph_engine.py
Motor Narrativo Genérico V2 basado en Grafos de Decisión.
Agnóstico al tipo de contenido (Eventos o Conversaciones), resuelve la navegación
paso a paso (heurística sin spoilers), valida transiciones y delega sorteo y resolución terminal.
"""

import logging
import random
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_V2_EVENTS,
)
from app.features.narrative.engine.rule_engine import evaluar_condicion
from app.features.narrative.enums import DisparadorEnum
from app.features.narrative.game.motor_v2 import graph_sampler, node_resolver
from app.features.narrative.game.run_repository import persistir_run
from app.features.narrative.schemas.v2_graph_schemas import (
    DesenlaceNodoSchema,
    EstadoGrafoV2Response,
    NodoClienteSchema,
    NodoNarrativoSchema,
)

logger = logging.getLogger(__name__)


class GraphTraversalEngine:
    def __init__(self):
        pass

    @staticmethod
    def _obtener_nodos_dict(grafo: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza los nodos del grafo asegurando formato diccionario indexado por ID."""
        return node_resolver.obtener_nodos_dict(grafo)

    def _get_collection_for_tipo(self, tipo: str):
        db = get_database()
        if tipo == "evento":
            return db[COLL_V2_EVENTS]
        if tipo == "conversacion":
            return db[COLL_V2_CONVERSATIONS]
        if tipo == "evento_especial":
            return db[COLL_V2_EVENTOS_ESPECIALES]
        raise ValueError(
            f"Tipo de grafo desconocido: '{tipo}'. Debe ser 'evento', 'conversacion' o 'evento_especial'."
        )

    async def obtener_grafo(self, tipo: str, grafo_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un grafo completo desde la colección correspondiente."""
        col = self._get_collection_for_tipo(tipo)
        return await col.find_one({"_id": grafo_id})

    async def sortear_evento_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval",
    ) -> Optional[Dict[str, Any]]:
        """Sortea un evento V2 elegible según universo, historial, requisitos y sinergias."""
        return await graph_sampler.sortear_evento_v2(
            run=run,
            pool_ids=pool_ids,
            universo_id=universo_id,
            db=get_database(),
        )

    async def sortear_conversacion_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval",
    ) -> Optional[Dict[str, Any]]:
        """Sortea una conversación V2 elegible respetando corte activa y condiciones."""
        return await graph_sampler.sortear_conversacion_v2(
            run=run,
            pool_ids=pool_ids,
            universo_id=universo_id,
            db=get_database(),
        )

    async def iniciar_grafo_en_partida(
        self,
        run: Dict[str, Any],
        grafo: Dict[str, Any],
        tipo: str,
        fase: str,
    ) -> EstadoGrafoV2Response:
        """Inicia un grafo en la partida fijando el nodo raíz y devolviendo el estado sanitizado."""
        grafo_id = grafo["_id"]
        nodo_raiz_id = grafo["nodo_raiz"]
        nodo_raiz_dict = self._obtener_nodos_dict(grafo).get(nodo_raiz_id)
        if not nodo_raiz_dict:
            raise HTTPException(
                status_code=500,
                detail=f"El grafo '{grafo_id}' no contiene su nodo raíz '{nodo_raiz_id}'.",
            )

        nodo_cliente = NodoNarrativoSchema(**nodo_raiz_dict).to_cliente_schema(run)
        # La preparación es en memoria; el coordinador confirma la transición completa.
        run["grafo_activo"] = {
            "tipo": tipo,
            "grafo_id": grafo_id,
            "nodo_actual_id": nodo_raiz_id,
        }
        run["fase_actual"] = fase

        return EstadoGrafoV2Response(
            fase_actual=fase,
            grafo_id=grafo_id,
            tipo=tipo,
            titulo=grafo.get("titulo", ""),
            imagen=grafo.get("imagen", ""),
            nodo_actual=nodo_cliente,
            status=run.get("status", "CONTINUA"),
        )

    def _detectar_cruces_afinidad(
        self,
        afinidad_before: Dict[str, Any],
        afinidad_after: Dict[str, Any],
    ) -> List[tuple]:
        return node_resolver._detectar_cruces_afinidad(afinidad_before, afinidad_after)

    @staticmethod
    def _pesos_desenlaces(desenlaces: List[DesenlaceNodoSchema], run: Dict[str, Any]) -> List[float]:
        return node_resolver._pesos_desenlaces(desenlaces, run)

    @staticmethod
    def _senal_desenlace(
        nodo: NodoNarrativoSchema,
        net_delta_recursos: float,
    ) -> Optional[DisparadorEnum]:
        return node_resolver._senal_desenlace(nodo, net_delta_recursos)

    async def _despachar_reactivos(
        self,
        run: Dict[str, Any],
        disparador: DisparadorEnum,
        recursos_mapa: Dict[str, Any],
        cat_acciones: Dict[str, Any],
        cat_frecuencias: Dict[str, Any],
        db,
    ) -> None:
        await node_resolver._despachar_reactivos(
            run, disparador, recursos_mapa, cat_acciones, cat_frecuencias, db
        )

    async def _obtener_evento_especial(
        self,
        personaje_id: str,
        direccion: str,
        universo_id: str,
    ) -> Optional[Dict[str, Any]]:
        return await node_resolver._obtener_evento_especial(
            personaje_id, direccion, universo_id, db=get_database()
        )

    async def _obtener_siguiente_especial_pendiente(
        self,
        run: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return await node_resolver._obtener_siguiente_especial_pendiente(run, db=get_database())

    async def _cargar_nodo_actual(
        self,
        run: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, Any], Dict[str, Any], NodoNarrativoSchema]:
        grafo_activo = run.get("grafo_activo")
        if not grafo_activo:
            raise HTTPException(
                status_code=409,
                detail="No hay ningún grafo (evento o conversación) activo en la partida para avanzar.",
            )

        tipo = grafo_activo["tipo"]
        grafo_id = grafo_activo["grafo_id"]
        nodo_actual_id = grafo_activo["nodo_actual_id"]

        grafo = await self.obtener_grafo(tipo, grafo_id)
        if not grafo:
            raise HTTPException(
                status_code=409,
                detail=f"El grafo activo '{grafo_id}' de tipo '{tipo}' ya no existe en la base de datos.",
            )

        nodos_dict = self._obtener_nodos_dict(grafo)
        nodo_actual_data = nodos_dict.get(nodo_actual_id)
        if not nodo_actual_data:
            raise HTTPException(
                status_code=409,
                detail=f"El nodo actual '{nodo_actual_id}' no existe en el grafo '{grafo_id}'.",
            )

        return tipo, grafo_id, grafo, nodos_dict, NodoNarrativoSchema(**nodo_actual_data)

    def _seleccionar_siguiente_nodo(
        self,
        run: Dict[str, Any],
        opcion_id: str,
        nodo_actual: NodoNarrativoSchema,
        nodos_dict: Dict[str, Any],
    ) -> Tuple[str, NodoNarrativoSchema, NodoClienteSchema]:
        opcion_elegida = next((opt for opt in nodo_actual.opciones if opt.id == opcion_id), None)
        if not opcion_elegida:
            raise HTTPException(
                status_code=400,
                detail=f"La opción '{opcion_id}' no es válida para el nodo '{nodo_actual.id}'.",
            )

        for cond in opcion_elegida.condiciones:
            cond_dict = cond.model_dump() if hasattr(cond, "model_dump") else cond
            if not evaluar_condicion(cond_dict, run):
                motivo = NodoNarrativoSchema._generar_motivo_bloqueo(cond)
                raise HTTPException(
                    status_code=400,
                    detail=f"La opción '{opcion_id}' está bloqueada: {motivo}.",
                )

        if opcion_elegida.desenlaces:
            nodos_destino = [d.nodo for d in opcion_elegida.desenlaces]
            pesos = self._pesos_desenlaces(opcion_elegida.desenlaces, run)
            siguiente_nodo_id = random.choices(nodos_destino, weights=pesos, k=1)[0]
        else:
            siguiente_nodo_id = opcion_elegida.siguiente_nodo

        if not siguiente_nodo_id:
            raise HTTPException(
                status_code=400,
                detail=f"La opción '{opcion_id}' no define un nodo destino (siguiente_nodo ni desenlaces).",
            )

        siguiente_nodo_data = nodos_dict.get(siguiente_nodo_id)
        if not siguiente_nodo_data:
            raise HTTPException(
                status_code=500,
                detail=f"El nodo destino '{siguiente_nodo_id}' configurado en la opción '{opcion_id}' no existe en el grafo.",
            )

        siguiente_nodo = NodoNarrativoSchema(**siguiente_nodo_data)
        return siguiente_nodo_id, siguiente_nodo, siguiente_nodo.to_cliente_schema(run)

    async def avanzar_nodo(
        self,
        run: Dict[str, Any],
        opcion_id: str,
    ) -> EstadoGrafoV2Response:
        """
        Avanza un paso en el grafo activo de la partida.
        Valida condiciones, avanza al siguiente nodo o resuelve el desenlace terminal.
        """
        tipo, grafo_id, grafo, nodos_dict, nodo_actual = await self._cargar_nodo_actual(run)
        siguiente_nodo_id, siguiente_nodo, nodo_cliente = self._seleccionar_siguiente_nodo(
            run, opcion_id, nodo_actual, nodos_dict
        )

        if not siguiente_nodo.es_final:
            run["grafo_activo"]["nodo_actual_id"] = siguiente_nodo_id
            run.setdefault("turno_actual", {})["opcion_elegida_id"] = opcion_id
            await persistir_run(run, ["grafo_activo", "turno_actual"])
            return EstadoGrafoV2Response(
                fase_actual=run["fase_actual"],
                grafo_id=grafo_id,
                tipo=tipo,
                titulo=grafo.get("titulo", ""),
                imagen=grafo.get("imagen", ""),
                nodo_actual=nodo_cliente,
                status=run.get("status", "CONTINUA"),
            )

        return await node_resolver.resolver_nodo_terminal(
            run=run,
            grafo=grafo,
            tipo=tipo,
            grafo_id=grafo_id,
            opcion_id=opcion_id,
            siguiente_nodo_id=siguiente_nodo_id,
            siguiente_nodo=siguiente_nodo,
            nodo_cliente=nodo_cliente,
            db=get_database(),
            persistir_fn=persistir_run,
            sortear_conversacion_fn=self.sortear_conversacion_v2,
        )


# Instancia singleton del motor
graph_engine = GraphTraversalEngine()
