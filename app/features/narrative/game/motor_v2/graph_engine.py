"""
graph_engine.py
Motor Narrativo Genérico V2 basado en Grafos de Decisión.
Agnóstico al tipo de contenido (Eventos, Conversaciones o Especiales), resuelve navegación
paso a paso sin spoilers y delega sorteo, encadenamiento y resolución terminal.
"""

import logging
import random
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import COLECCION_V2_POR_TIPO
from app.features.narrative.engine.condition_evaluator import primer_motivo_bloqueo
from app.features.narrative.game.motor_v2 import graph_chaining, graph_sampler, node_resolver
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
        return graph_chaining.obtener_nodos_dict(grafo)

    def _get_collection_for_tipo(self, tipo: str):
        col_name = COLECCION_V2_POR_TIPO.get(tipo)
        if not col_name:
            raise ValueError(
                f"Tipo de grafo desconocido: '{tipo}'. Debe ser 'evento', 'conversacion' o 'evento_especial'."
            )
        return get_database()[col_name]

    async def obtener_grafo(self, tipo: str, grafo_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un grafo completo desde la colección correspondiente."""
        return await self._get_collection_for_tipo(tipo).find_one({"_id": grafo_id})

    async def sortear_evento_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval",
    ) -> Optional[Dict[str, Any]]:
        """Sortea un evento V2 elegible según universo, historial, requisitos y sinergias."""
        return await graph_sampler.sortear_evento_v2(
            run=run, pool_ids=pool_ids, universo_id=universo_id, db=get_database()
        )

    async def sortear_conversacion_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval",
    ) -> Optional[Dict[str, Any]]:
        """Sortea una conversación V2 elegible respetando corte activa y condiciones."""
        return await graph_sampler.sortear_conversacion_v2(
            run=run, pool_ids=pool_ids, universo_id=universo_id, db=get_database()
        )

    async def iniciar_grafo_en_partida(
        self,
        run: Dict[str, Any],
        grafo: Dict[str, Any],
        tipo: str,
        fase: str,
    ) -> EstadoGrafoV2Response:
        """Inicia un grafo en la partida fijando el nodo raíz y devolviendo el estado sanitizado."""
        nodo_cliente = graph_chaining.activar_raiz_grafo(run, grafo, tipo, fase)
        return graph_chaining.construir_estado_grafo_v2(
            run, grafo, tipo, grafo["_id"], nodo_cliente, fase_actual=fase
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

        motivo = primer_motivo_bloqueo(opcion_elegida.condiciones, run)
        if motivo is not None:
            raise HTTPException(status_code=400, detail=f"La opción '{opcion_id}' está bloqueada: {motivo}.")

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
            return graph_chaining.construir_estado_grafo_v2(
                run, grafo, tipo, grafo_id, nodo_cliente
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


graph_engine = GraphTraversalEngine()
