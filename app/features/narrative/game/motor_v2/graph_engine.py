"""
graph_engine.py
Motor Narrativo Genérico V2 basado en Grafos de Decisión.
Agnóstico al tipo de contenido (Eventos o Conversaciones), resuelve la navegación
paso a paso (heurística sin spoilers), valida transiciones y aplica consecuencias atómicas en MongoDB.
Incorpora reactividad de estado con condiciones dinámicas por opción y sorteo ponderado por sinergias.
"""

import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from fastapi import HTTPException

from app.core.database import get_database
from app.features.narrative.constants import (
    COLL_V2_EVENTS,
    COLL_V2_CONVERSATIONS,
    COLL_V2_EVENTOS_ESPECIALES,
    COLL_CHARACTERS,
    COLL_CARDS,
    COLL_SETTINGS,
    AFINIDAD_UMBRAL_LEALTAD,
    AFINIDAD_UMBRAL_TRAICION
)
from app.features.narrative.enums import RunPhaseEnum, DisparadorEnum
from app.features.narrative.schemas.rules_schemas import EfectoSchema
from app.features.narrative.engine.tag_state import personajes_activos, sincronizar_personajes
from app.features.narrative.engine.rule_engine import despachar_efectos, aplicar_delta_recurso
from app.features.narrative.engine.catalog_loader import obtener_catalogos_universo
from app.features.narrative.schemas.v2_graph_schemas import (
    NodoNarrativoSchema,
    DesenlaceNodoSchema,
    EstadoGrafoV2Response
)
from app.features.narrative.game.run_repository import persistir_run

logger = logging.getLogger(__name__)

class GraphTraversalEngine:
    def __init__(self):
        pass

    @staticmethod
    def _obtener_nodos_dict(grafo: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza los nodos del grafo asegurando formato diccionario indexado por ID."""
        nodos_raw = grafo.get("nodos", {})
        if isinstance(nodos_raw, list):
            return {n["id"]: n for n in nodos_raw if isinstance(n, dict) and "id" in n}
        elif isinstance(nodos_raw, dict):
            return nodos_raw
        return {}

    def _get_collection_for_tipo(self, tipo: str):
        db = get_database()
        if tipo == "evento":
            return db[COLL_V2_EVENTS]
        elif tipo == "conversacion":
            return db[COLL_V2_CONVERSATIONS]
        elif tipo == "evento_especial":
            return db[COLL_V2_EVENTOS_ESPECIALES]
        else:
            raise ValueError(f"Tipo de grafo desconocido: '{tipo}'. Debe ser 'evento', 'conversacion' o 'evento_especial'.")

    async def obtener_grafo(self, tipo: str, grafo_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un grafo completo desde la colección correspondiente."""
        col = self._get_collection_for_tipo(tipo)
        return await col.find_one({"_id": grafo_id})

    async def sortear_evento_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval"
    ) -> Optional[Dict[str, Any]]:
        """
        Sortea un evento V2 elegible respetando:
        1. Universo y pool de IDs del mes (si se proporciona).
        2. Que no se haya jugado ya en esta partida (run['eventos_jugados']).
        3. Que se cumplan los 'requisitos_eventos_previos' (cadenas de eventos / arcos narrativos).
        4. Que se cumplan los 'requisitos_personajes' (consejeros requeridos en corte).
        5. Que se cumplan las 'condiciones_disparo' (recursos mínimos, crisis, afinidad, etc.).
        6. Sorteo ponderado por sinergia con corte activa, cartas en inventario y situaciones de crisis.
        """
        db = get_database()
        query: Dict[str, Any] = {"universo_id": universo_id}
        if pool_ids:
            query["_id"] = {"$in": pool_ids}

        candidatos = await db[COLL_V2_EVENTS].find(query).to_list(None)
        if not candidatos:
            return None

        eventos_jugados = set(run.get("eventos_jugados", []))
        corte_activa = set(run.get("afinidad", {}).keys()) or set(run.get("corte_activa", []))

        # 1. Obtener tags de la corte activa
        tags_corte = set()
        if corte_activa:
            pjs_docs = await db[COLL_CHARACTERS].find({"_id": {"$in": list(corte_activa)}}).to_list(None)
            for p in pjs_docs:
                for t in p.get("tags", []):
                    tags_corte.add(t.lower())

        # 2. Obtener tags de cartas en mano / inventario
        tags_cartas = set()
        cartas_mano = run.get("cartas_en_mano", [])
        if cartas_mano:
            cartas_docs = await db[COLL_CARDS].find({"_id": {"$in": cartas_mano}}).to_list(None)
            for c in cartas_docs:
                for t in c.get("tags", []):
                    tags_cartas.add(t.lower())

        # 3. Detectar recursos en crisis (< 25)
        recursos = run.get("recursos", {})
        recursos_en_crisis = {k.lower() for k, v in recursos.items() if float(v) < 25.0}

        from app.features.narrative.engine.rule_engine import evaluar_condiciones

        def _elegibles(eventos_previos: set) -> tuple[list, list]:
            disponibles_elegibles = []
            pesos_elegibles = []
            for evt in candidatos:
                evt_id = evt.get("_id")
                if evt_id in eventos_previos:
                    continue

                # Validar requisitos de eventos previos (Arcos Narrativos)
                requisitos_previos = evt.get("requisitos_eventos_previos", [])
                if requisitos_previos and not set(requisitos_previos).issubset(eventos_previos):
                    continue

                # Validar requisitos de personajes de la corte
                requisitos_personajes = evt.get("requisitos_personajes", [])
                if requisitos_personajes and not set(requisitos_personajes).issubset(corte_activa):
                    continue

                # Validar condiciones de disparo del estado del reino
                condiciones_disparo = evt.get("condiciones_disparo", [])
                if condiciones_disparo and not evaluar_condiciones(condiciones_disparo, run):
                    continue

                # Cálculo de peso ponderado (sinergias con corte, cartas y urgencia)
                peso = float(evt.get("peso_base", 100.0))
                tags_evento = {t.lower() for t in evt.get("tags_tematicos", [])}

                if tags_corte.intersection(tags_evento):
                    peso *= 2.0

                if tags_cartas.intersection(tags_evento):
                    peso *= 2.5

                if recursos_en_crisis.intersection(tags_evento):
                    peso *= 3.0

                disponibles_elegibles.append(evt)
                pesos_elegibles.append(max(1.0, peso))
            return disponibles_elegibles, pesos_elegibles

        disponibles, pesos = _elegibles(eventos_jugados)

        if not disponibles and eventos_jugados:
            universo_doc = await db[COLL_SETTINGS].find_one(
                {"_id": universo_id}, {"reciclaje_eventos_v2": 1}
            )
            reciclar = bool(
                run.get("reciclaje_eventos_v2")
                or (universo_doc or {}).get("reciclaje_eventos_v2")
            )
            if reciclar:
                # Reciclaje controlado: al agotar los eventos elegibles se libera el
                # historial para que la partida pueda cerrar los 12 meses.
                run["eventos_jugados"] = []
                run["reciclajes_eventos_v2"] = int(run.get("reciclajes_eventos_v2", 0)) + 1
                disponibles, pesos = _elegibles(set())

        if not disponibles:
            return None

        return random.choices(disponibles, weights=pesos, k=1)[0]

    async def sortear_conversacion_v2(
        self,
        run: Dict[str, Any],
        pool_ids: Optional[List[str]] = None,
        universo_id: str = "corte_medieval"
    ) -> Optional[Dict[str, Any]]:
        """
        Sortea una conversación V2 elegible respetando:
        1. Universo y pool de IDs del mes.
        2. Que no se haya jugado ya en esta partida (run['conversaciones_jugadas']).
        3. Que todos los consejeros requeridos estén activos en la corte del jugador.
        4. Que se cumplan las condiciones_disparo si existen.
        """
        db = get_database()
        query: Dict[str, Any] = {"universo_id": universo_id}
        if pool_ids:
            query["_id"] = {"$in": pool_ids}

        candidatas = await db[COLL_V2_CONVERSATIONS].find(query).to_list(None)
        if not candidatas:
            return None

        convs_jugadas = set(run.get("conversaciones_jugadas", []))
        corte_activa = set(run.get("afinidad", {}).keys()) or set(run.get("corte_activa", []))

        from app.features.narrative.engine.rule_engine import evaluar_condiciones

        validas = []
        for conv in candidatas:
            conv_id = conv.get("_id")
            if conv_id in convs_jugadas:
                continue

            requisitos = conv.get("requisitos", [])
            if not set(requisitos).issubset(corte_activa):
                continue

            condiciones_disparo = conv.get("condiciones_disparo", [])
            if condiciones_disparo and not evaluar_condiciones(condiciones_disparo, run):
                continue

            validas.append(conv)

        if not validas:
            return None

        return random.choice(validas)

    async def iniciar_grafo_en_partida(
        self,
        run: Dict[str, Any],
        grafo: Dict[str, Any],
        tipo: str,
        fase: str
    ) -> EstadoGrafoV2Response:
        """
        Inicia un grafo en la partida, fijando el nodo raíz y devolviendo el estado inicial sanitizado y evaluado.
        """
        grafo_id = grafo["_id"]
        nodo_raiz_id = grafo["nodo_raiz"]
        nodos = self._obtener_nodos_dict(grafo)

        nodo_raiz_dict = nodos.get(nodo_raiz_id)
        if not nodo_raiz_dict:
            raise HTTPException(status_code=500, detail=f"El grafo '{grafo_id}' no contiene su nodo raíz '{nodo_raiz_id}'.")

        nodo_schema = NodoNarrativoSchema(**nodo_raiz_dict)
        nodo_cliente = nodo_schema.to_cliente_schema(run)

        # La preparación es en memoria; el coordinador confirma la transición completa.
        run["grafo_activo"] = {
            "tipo": tipo,
            "grafo_id": grafo_id,
            "nodo_actual_id": nodo_raiz_id
        }
        run["fase_actual"] = fase

        return EstadoGrafoV2Response(
            fase_actual=fase,
            grafo_id=grafo_id,
            tipo=tipo,
            titulo=grafo.get("titulo", ""),
            imagen=grafo.get("imagen", ""),
            nodo_actual=nodo_cliente,
            status=run.get("status", "CONTINUA")
        )

    def _detectar_cruces_afinidad(
        self,
        afinidad_before: Dict[str, Any],
        afinidad_after: Dict[str, Any]
    ) -> List[tuple]:
        """
        Detecta personajes que cruzaron un umbral de afinidad al aplicar deltas:
        - 'lealtad': pasó de estar por debajo de AFINIDAD_UMBRAL_LEALTAD a alcanzarlo o superarlo.
        - 'traicion': pasó de estar en o por encima de AFINIDAD_UMBRAL_TRAICION a caer por debajo.
        """
        cruces: List[tuple] = []
        for pj_id, valor_actual in afinidad_after.items():
            valor_previo = afinidad_before.get(pj_id)
            if valor_previo is None:
                continue
            if valor_previo < AFINIDAD_UMBRAL_LEALTAD and valor_actual >= AFINIDAD_UMBRAL_LEALTAD:
                cruces.append((pj_id, "lealtad"))
            if valor_previo >= AFINIDAD_UMBRAL_TRAICION and valor_actual < AFINIDAD_UMBRAL_TRAICION:
                cruces.append((pj_id, "traicion"))
        return cruces

    @staticmethod
    def _pesos_desenlaces(desenlaces: List[DesenlaceNodoSchema], run: Dict[str, Any]) -> List[float]:
        """
        Pesos efectivos del sorteo de desenlaces, aplicando los modificadores condicionales
        que V1 resolvía en sus resultados y V2 aún no tenía.
        El suelo sigue siendo 0.0: un desenlace anulado por sus modificadores deja de sortearse,
        que es la semántica que el validador y el contenido V2 ya tenían.
        """
        from app.features.narrative.engine.rule_engine import evaluar_condicion

        pesos: List[float] = []
        for desenlace in desenlaces:
            peso = float(desenlace.peso)
            for mod in desenlace.modificadores_probabilidad:
                if evaluar_condicion(mod.condicion.model_dump(), run):
                    peso += float(mod.delta_peso)
            pesos.append(max(0.0, peso))
        return pesos

    @staticmethod
    def _senal_desenlace(
        nodo: NodoNarrativoSchema,
        net_delta_recursos: float
    ) -> Optional[DisparadorEnum]:
        """
        Resuelve el signo que perciben cartas y corte al cerrarse un desenlace.
        La declaración del autor manda; sin ella se infiere del balance de recursos,
        que era la única señal disponible antes de los grafos.
        """
        if nodo.tipo_desenlace is not None:
            signo = nodo.tipo_desenlace.value if hasattr(nodo.tipo_desenlace, "value") else str(nodo.tipo_desenlace)
        else:
            signo = "positivo" if net_delta_recursos > 0 else ("negativo" if net_delta_recursos < 0 else "neutro")

        if signo == "positivo":
            return DisparadorEnum.EN_EVENTO_POSITIVO
        if signo == "negativo":
            return DisparadorEnum.EN_EVENTO_NEGATIVO
        return None

    async def _despachar_reactivos(
        self,
        run: Dict[str, Any],
        disparador: DisparadorEnum,
        recursos_mapa: Dict[str, Any],
        cat_acciones: Dict[str, Any],
        cat_frecuencias: Dict[str, Any],
        db
    ) -> None:
        """
        Descarga cartas y corte en dos consultas y despacha sus efectos reactivos,
        en lugar de un find_one por cada posesión del jugador.
        """
        dueños: List[Tuple[str, List[Any]]] = []

        cartas_ids = run.get("cartas_en_mano", [])
        if cartas_ids:
            docs = await db[COLL_CARDS].find(
                {"_id": {"$in": cartas_ids}}, {"efectos": 1}
            ).to_list(None)
            dueños.extend((str(d["_id"]), d.get("efectos") or []) for d in docs)

        corte_ids = list(run.get("afinidad", {}).keys())
        if corte_ids:
            docs = await db[COLL_CHARACTERS].find(
                {"_id": {"$in": corte_ids}}, {"efectos": 1}
            ).to_list(None)
            dueños.extend((str(d["_id"]), d.get("efectos") or []) for d in docs)

        for duenio_id, efectos in dueños:
            if not efectos:
                continue
            despachar_efectos(
                disparador,
                run,
                [EfectoSchema(**e) for e in efectos],
                recursos_mapa,
                duenio_id=duenio_id,
                mes_actual=run.get("mes_actual", 1),
                catalogo_acciones=cat_acciones,
                catalogo_frecuencias=cat_frecuencias,
            )

    async def _obtener_evento_especial(
        self,
        personaje_id: str,
        direccion: str,
        universo_id: str
    ) -> Optional[Dict[str, Any]]:
        """Recupera el grafo de evento especial para un personaje y dirección de umbral."""
        db = get_database()
        return await db[COLL_V2_EVENTOS_ESPECIALES].find_one({
            "universo_id": universo_id,
            "personaje_id": personaje_id,
            "direccion": direccion
        })

    async def _encadenar_especial_pendiente(
        self,
        run: Dict[str, Any]
    ) -> Optional[EstadoGrafoV2Response]:
        """Desencola y encadena el próximo evento especial de afinidad pendiente, si hay grafo disponible."""
        pendientes = run.get("especiales_pendientes", [])
        if not pendientes:
            return None

        while pendientes:
            item = pendientes.pop(0)
            grafo = await self._obtener_evento_especial(
                item["personaje_id"],
                item["direccion"],
                run.get("universo_id", "corte_medieval")
            )
            if grafo:
                return await self.iniciar_grafo_en_partida(
                    run=run,
                    grafo=grafo,
                    tipo="evento_especial",
                    fase=RunPhaseEnum.TOMA_DECISION_EVENTO.value
                )
        return None

    async def _obtener_siguiente_especial_pendiente(
        self,
        run: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Desencola el próximo evento especial de afinidad pendiente y devuelve su grafo si existe."""
        pendientes = run.get("especiales_pendientes", [])
        while pendientes:
            item = pendientes.pop(0)
            grafo = await self._obtener_evento_especial(
                item["personaje_id"],
                item["direccion"],
                run.get("universo_id", "corte_medieval")
            )
            if grafo:
                return grafo
        return None

    async def avanzar_nodo(
        self,
        run: Dict[str, Any],
        opcion_id: str
    ) -> EstadoGrafoV2Response:
        """
        Avanza un paso en el grafo activo de la partida.
        Valida que la opción seleccionada cumpla con las condiciones dinámicas requeridas.
        Si el siguiente nodo es intermedio, actualiza el puntero y lo devuelve sin spoilers.
        Si es final, aplica impactos en recursos y afinidad, evalúa fin de partida y avanza la fase.
        """
        grafo_activo = run.get("grafo_activo")
        if not grafo_activo:
            raise HTTPException(
                status_code=409,
                detail="No hay ningún grafo (evento o conversación) activo en la partida para avanzar."
            )

        tipo = grafo_activo["tipo"]
        grafo_id = grafo_activo["grafo_id"]
        nodo_actual_id = grafo_activo["nodo_actual_id"]

        grafo = await self.obtener_grafo(tipo, grafo_id)
        if not grafo:
            raise HTTPException(
                status_code=409,
                detail=f"El grafo activo '{grafo_id}' de tipo '{tipo}' ya no existe en la base de datos."
            )

        nodos_dict = self._obtener_nodos_dict(grafo)
        nodo_actual_data = nodos_dict.get(nodo_actual_id)
        if not nodo_actual_data:
            raise HTTPException(
                status_code=409,
                detail=f"El nodo actual '{nodo_actual_id}' no existe en el grafo '{grafo_id}'."
            )

        nodo_actual = NodoNarrativoSchema(**nodo_actual_data)

        # Buscar la opción seleccionada dentro del nodo actual
        opcion_elegida = next((opt for opt in nodo_actual.opciones if opt.id == opcion_id), None)
        if not opcion_elegida:
            raise HTTPException(
                status_code=400,
                detail=f"La opción '{opcion_id}' no es válida para el nodo '{nodo_actual_id}'."
            )

        # Validar si la opción cumplía las condiciones requeridas
        if opcion_elegida.condiciones:
            from app.features.narrative.engine.rule_engine import evaluar_condicion
            for cond in opcion_elegida.condiciones:
                cond_dict = cond.model_dump() if hasattr(cond, "model_dump") else cond
                if not evaluar_condicion(cond_dict, run):
                    motivo = NodoNarrativoSchema._generar_motivo_bloqueo(cond)
                    raise HTTPException(
                        status_code=400,
                        detail=f"La opción '{opcion_id}' está bloqueada: {motivo}."
                    )

        # Resolver el nodo destino: desenlaces ponderados (si los hay) o destino fijo
        if opcion_elegida.desenlaces:
            nodos_destino = [d.nodo for d in opcion_elegida.desenlaces]
            pesos = self._pesos_desenlaces(opcion_elegida.desenlaces, run)
            siguiente_nodo_id = random.choices(nodos_destino, weights=pesos, k=1)[0]
        else:
            siguiente_nodo_id = opcion_elegida.siguiente_nodo

        if not siguiente_nodo_id:
            raise HTTPException(
                status_code=400,
                detail=f"La opción '{opcion_id}' no define un nodo destino (siguiente_nodo ni desenlaces)."
            )

        siguiente_nodo_data = nodos_dict.get(siguiente_nodo_id)
        if not siguiente_nodo_data:
            raise HTTPException(
                status_code=500,
                detail=f"El nodo destino '{siguiente_nodo_id}' configurado en la opción '{opcion_id}' no existe en el grafo."
            )

        siguiente_nodo = NodoNarrativoSchema(**siguiente_nodo_data)
        nodo_cliente = siguiente_nodo.to_cliente_schema(run)

        # ====================================================================
        # CASO 1: NODO INTERMEDIO (es_final == False)
        # ====================================================================
        if not siguiente_nodo.es_final:
            grafo_activo["nodo_actual_id"] = siguiente_nodo_id
            turno = run.setdefault("turno_actual", {})
            turno["opcion_elegida_id"] = opcion_id
            await persistir_run(run, ["grafo_activo", "turno_actual"])

            return EstadoGrafoV2Response(
                fase_actual=run["fase_actual"],
                grafo_id=grafo_id,
                tipo=tipo,
                titulo=grafo.get("titulo", ""),
                imagen=grafo.get("imagen", ""),
                nodo_actual=nodo_cliente,
                status=run.get("status", "CONTINUA")
            )

        # ====================================================================
        # CASO 2: NODO TERMINAL (es_final == True)
        # ====================================================================
        from app.features.narrative.game.endings_service import (
            verificar_colapso_recursos,
            sincronizar_intento_usuario
        )
        from app.features.narrative.game.universe_resources import obtener_mapa_recursos_universo

        recursos = run.setdefault("recursos", {"oro": 50, "pueblo": 50, "ejercito": 50, "fe": 50})
        afinidad = run.setdefault("afinidad", {})

        # Límites min/max de recursos configurados para el universo
        recursos_mapa = await obtener_mapa_recursos_universo(run.get("universo_id", "corte_medieval"))

        db = get_database()
        cat_acciones, cat_frecuencias = await obtener_catalogos_universo(run.get("universo_id", "corte_medieval"), db)

        # 1. Impactos de recursos por el único punto de aritmética del motor
        for imp_rec in siguiente_nodo.impactos_recursos:
            aplicar_delta_recurso(run, imp_rec.recurso.lower(), float(imp_rec.delta), recursos_mapa)

        # 2. Impactos de afinidad
        afinidad_before = dict(afinidad)
        for imp_af in siguiente_nodo.impactos_afinidad:
            pj_id = imp_af.personaje_id
            if pj_id in afinidad:
                afinidad[pj_id] = max(0, min(100, afinidad[pj_id] + imp_af.delta))

        # 3. Tags permanentes otorgados al reino
        for tag in siguiente_nodo.impactos_tags:
            tags_activos = run.setdefault("tags_activos", [])
            if tag not in tags_activos:
                tags_activos.append(tag)

        # 4. Efectos ECA declarados en el propio desenlace
        if siguiente_nodo.efectos:
            despachar_efectos(
                DisparadorEnum.AL_DESENLACE,
                run,
                siguiente_nodo.efectos,
                recursos_mapa,
                mes_actual=run.get("mes_actual", 1),
                catalogo_acciones=cat_acciones,
                catalogo_frecuencias=cat_frecuencias,
            )

        # 5. Reactivos de cartas y corte: el autor declara el signo del desenlace y,
        #    si no lo declaró, se infiere del balance de recursos (compatibilidad V1)
        disparador_reactivo = self._senal_desenlace(
            siguiente_nodo, sum(float(imp.delta) for imp in siguiente_nodo.impactos_recursos)
        )
        if disparador_reactivo:
            await self._despachar_reactivos(
                run, disparador_reactivo, recursos_mapa, cat_acciones, cat_frecuencias, db
            )

        # Desenlaces o reactivos pueden reclutar personajes: activar sus tags estáticos
        await sincronizar_personajes(run, personajes_activos(run), db)

        cruces_afinidad = self._detectar_cruces_afinidad(afinidad_before, afinidad)

        # 6. Registrar en historial de jugados
        if tipo == "evento":
            run.setdefault("eventos_jugados", []).append(grafo_id)
        elif tipo == "conversacion":
            run.setdefault("conversaciones_jugadas", []).append(grafo_id)
        elif tipo == "evento_especial":
            run.setdefault("eventos_especiales_jugados", []).append(grafo_id)

        # 7. Persistir la última decisión y limpiar el grafo activo
        turno = run.setdefault("turno_actual", {})
        turno["opcion_elegida_id"] = opcion_id
        turno["resultado_obtenido_id"] = siguiente_nodo_id
        run["grafo_activo"] = None

        run.setdefault("historial_grafos", []).append({
            "mes": run.get("mes_actual", 1),
            "tipo": tipo,
            "grafo_id": grafo_id,
            "opcion_elegida_id": opcion_id,
            "resultado_obtenido_id": siguiente_nodo_id,
            "resultado_texto": siguiente_nodo.resultado_texto,
        })

        # 5. Comprobar Derrota por colapso de recursos (epílogo + sincronización de intento)
        derrota = await verificar_colapso_recursos(run)
        if derrota:
            run["updated_at"] = datetime.now(timezone.utc).isoformat()
            await persistir_run(run)
            puntos_ganados = await sincronizar_intento_usuario(run)

            return EstadoGrafoV2Response(
                fase_actual=run["fase_actual"],
                grafo_id=grafo_id,
                tipo=tipo,
                titulo=grafo.get("titulo", ""),
                imagen=grafo.get("imagen", ""),
                nodo_actual=nodo_cliente,
                afinidad=afinidad,
                recursos=recursos,
                finalizacion=run.get("finalizacion"),
                status=run.get("status", "game_over"),
                puntos_ganados=puntos_ganados,
            )

        # 5.5 Encadenar evento especial de afinidad (lealtad/traición) si se cruzó un umbral
        if cruces_afinidad:
            pendientes = run.setdefault("especiales_pendientes", [])
            claves_pendientes = {(p["personaje_id"], p["direccion"]) for p in pendientes}
            for pj_id, direccion in cruces_afinidad:
                if (pj_id, direccion) not in claves_pendientes:
                    pendientes.append({"personaje_id": pj_id, "direccion": direccion})
                    claves_pendientes.add((pj_id, direccion))

        next_grafo = await self._obtener_siguiente_especial_pendiente(run)
        next_tipo = "evento_especial" if next_grafo else None

        # 6. (solo tras un evento) Conversación incidental de corte con 40% de probabilidad
        if not next_grafo and tipo == "evento" and random.random() < 0.40:
            conv = await self.sortear_conversacion_v2(
                run=run,
                pool_ids=None,
                universo_id=run.get("universo_id", "corte_medieval")
            )
            if conv:
                next_grafo = conv
                next_tipo = "conversacion"

        conversacion_dto = None
        if next_grafo:
            nodo_raiz_id = next_grafo["nodo_raiz"]
            nodos_next = self._obtener_nodos_dict(next_grafo)
            nodo_raiz_dict = nodos_next.get(nodo_raiz_id)
            if not nodo_raiz_dict:
                raise HTTPException(status_code=500, detail=f"El grafo '{next_grafo['_id']}' no contiene su nodo raíz '{nodo_raiz_id}'.")

            nodo_schema_next = NodoNarrativoSchema(**nodo_raiz_dict)
            nodo_cliente_next = nodo_schema_next.to_cliente_schema(run)

            run["grafo_activo"] = {
                "tipo": next_tipo,
                "grafo_id": next_grafo["_id"],
                "nodo_actual_id": nodo_raiz_id
            }
            run["fase_actual"] = RunPhaseEnum.RESOLVER_CONVERSACION.value
            run.setdefault("turno_actual", {})["conversacion_actual_id"] = next_grafo["_id"]

            conversacion_dto = {
                "_id": next_grafo["_id"],
                "nodo_id": nodo_raiz_id,
                "titulo": next_grafo.get("titulo", ""),
                "imagen": nodo_cliente_next.imagen or next_grafo.get("imagen", ""),
                "requisitos": [{"personajeId": nodo_cliente_next.hablante_id}],
                "frases": [{"personajeId": nodo_cliente_next.hablante_id, "texto": nodo_cliente_next.texto}],
                "decisiones": [
                    {
                        "opcion": opt.id,
                        "texto": opt.texto,
                        "resultado_texto": "",
                        "impacto_afinidad": []
                    }
                    for opt in nodo_cliente_next.opciones
                    if opt.disponible
                ]
            }
        else:
            # 7. Transición de Fase a balance mensual
            run["grafo_activo"] = None
            run["fase_actual"] = RunPhaseEnum.BALANCE_MES.value

        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        await persistir_run(run)

        return EstadoGrafoV2Response(
            fase_actual=run["fase_actual"],
            grafo_id=grafo_id,
            tipo=tipo,
            titulo=grafo.get("titulo", ""),
            imagen=grafo.get("imagen", ""),
            nodo_actual=nodo_cliente,
            afinidad=afinidad,
            recursos=recursos,
            status=run.get("status", "CONTINUA"),
            conversacion_actual=conversacion_dto
        )

# Instancia singleton del motor
graph_engine = GraphTraversalEngine()
