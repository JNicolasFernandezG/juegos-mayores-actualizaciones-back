"""
router.py
Controladores FastAPI del módulo de Juego Narrativo V2:
- router (/api/narrative/partida): Setup diario, reinicio y modales de consulta bajo demanda.
- router_v2 (/api/narrative/v2/partida): Ciclo reactivo nativo V2 basado en grafos (iniciar, draft, avance-nodo, estado).
"""

from fastapi import APIRouter, Query, Depends
from typing import Optional

from app.features.narrative.schemas.game_schemas import (
    IniciarPartidaRequest,
    ElegirCartaMesRequest,
    AvanzarMesRequest,
    ReiniciarPartidaRequest,
    IniciarPartidaV2Response,
    ElegirCartaMesV2Response,
    AvanzarMesV2Response,
    EstadoTurnoResponse,
    SetupDesafioResponse,
    HistorialPartidaResponse,
    InventarioPartidaResponse,
    CortePartidaResponse,
    FinalizacionPartidaResponse,
)
from app.features.narrative.schemas.v2_graph_schemas import (
    AvanzarNodoV2Request,
    EstadoGrafoV2Response,
)
from app.features.narrative.game.motor_v2.v2_graph_service import (
    avanzar_nodo_v2,
    obtener_grafo_actual_v2,
    iniciar_evento_mes_v2,
    iniciar_conversacion_mes_v2,
)
from app.features.narrative.game.setup_service import (
    obtener_setup_desafio,
    iniciar_partida,
    reiniciar_partida,
)
from app.features.narrative.game.turn_service import elegir_carta_mes
from app.features.narrative.game.transition_service import avanzar_mes
from app.features.narrative.game.modals_service import (
    obtener_historial_partida,
    obtener_inventario_partida,
    obtener_corte_partida,
    obtener_finalizacion_partida,
)
from app.features.narrative.game.turn_state import obtener_turno_actual
from app.features.narrative.game.identity import obtener_identidad_narrativa

# ============================================================================
# ROUTER V2: CICLO MENSUAL NATIVO LIGERO (/api/narrative/v2/partida)
# ============================================================================

router_v2 = APIRouter(
    prefix="/api/narrative/v2/partida",
)

@router_v2.post(
    "/iniciar",
    tags=["Narrativo - Flujo de Juego"],
    response_model=IniciarPartidaV2Response,
    summary="[V2] Fase 0: Iniciar partida devolviendo solo recursos iniciales y las 3 cartas de draft del Mes 1"
)
async def endpoint_v2_iniciar_partida(
    req: IniciarPartidaRequest,
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Inicia la partida para la fecha actual devolviendo recursos y mazo de draft inicial."""
    return await iniciar_partida(user_id=user_id, req=req)

@router_v2.post(
    "/elegir-carta-mes",
    tags=["Narrativo - Flujo de Juego"],
    response_model=ElegirCartaMesV2Response,
    summary="[V2] Fase 1: Elegir carta de draft mensual devolviendo el grafo del evento sorteado"
)
async def endpoint_v2_elegir_carta_mes(
    req: ElegirCartaMesRequest,
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Aplica la carta seleccionada y retorna el evento sorteado del mes (o finalización si colapsó)."""
    return await elegir_carta_mes(user_id=user_id, req=req)

@router_v2.post(
    "/avanzar-mes",
    tags=["Narrativo - Flujo de Juego"],
    response_model=AvanzarMesV2Response,
    summary="[V2] Fase 4: Avanzar mes devolviendo recursos post-pasivos y las 3 nuevas cartas de draft"
)
async def endpoint_v2_avanzar_mes(
    req: AvanzarMesRequest,
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Aplica pasivos mensuales, guarda el historial y avanza al siguiente mes (o decreta fin de año)."""
    return await avanzar_mes(user_id=user_id, req=req)

@router_v2.get(
    "/estado",
    tags=["Narrativo - Flujo de Juego"],
    response_model=EstadoTurnoResponse,
    summary="[V2] Consultar estado reactivo del turno actual para sincronización / F5"
)
async def endpoint_v2_obtener_estado_turno(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Permite al frontend restaurar el estado exacto del turno tras recargar la página."""
    return await obtener_turno_actual(user_id=user_id, date=date)

@router_v2.post(
    "/avanzar-nodo",
    tags=["Narrativo - Flujo de Juego"],
    response_model=EstadoGrafoV2Response,
    summary="[V2 Grafos] Avanzar un paso en el grafo activo (evento o conversación) sin spoilers"
)
async def endpoint_v2_avanzar_nodo(
    req: AvanzarNodoV2Request,
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """
    Avanza un paso en el árbol narrativo activo.
    Si el siguiente nodo es intermedio, retorna el nuevo nodo a mostrar.
    Si es final, aplica impactos en recursos y afinidad y avanza la fase de la partida.
    """
    return await avanzar_nodo_v2(user_id=user_id, req=req)

@router_v2.get(
    "/grafo-actual",
    tags=["Narrativo - Flujo de Juego"],
    response_model=Optional[EstadoGrafoV2Response],
    summary="[V2 Grafos] Consultar el estado del grafo activo (evento o conversación) para recargas/F5"
)
async def endpoint_v2_obtener_grafo_actual(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Permite restaurar el nodo activo tras recargar la página."""
    return await obtener_grafo_actual_v2(user_id=user_id, date=date)

@router_v2.post(
    "/iniciar-evento-grafo",
    tags=["Narrativo - Flujo de Juego"],
    response_model=EstadoGrafoV2Response,
    summary="[V2 Grafos] Iniciar un evento basado en grafos para el mes actual"
)
async def endpoint_v2_iniciar_evento_grafo(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Inicia un evento V2 del pool respetando arcos narrativos y requisitos previos."""
    return await iniciar_evento_mes_v2(user_id=user_id, date=date)

@router_v2.post(
    "/iniciar-conversacion-grafo",
    tags=["Narrativo - Flujo de Juego"],
    response_model=Optional[EstadoGrafoV2Response],
    summary="[V2 Grafos] Iniciar una conversación basada en grafos para el mes actual"
)
async def endpoint_v2_iniciar_conversacion_grafo(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Inicia una conversación V2 si los requisitos de consejeros activos se cumplen."""
    return await iniciar_conversacion_mes_v2(user_id=user_id, date=date)

# ============================================================================
# ROUTER CONSULTAS: MODALES Y SETUP (/api/narrative/partida)
# ============================================================================

router = APIRouter(
    prefix="/api/narrative/partida",
)

@router.get(
    "/setup",
    tags=["Narrativo - Flujo de Juego"],
    response_model=SetupDesafioResponse,
    summary="Fase 0: Obtener los 5 personajes y 5 cartas ofrecidas para iniciar el día"
)
async def endpoint_obtener_setup(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Consulta los 5 personajes y 5 cartas ofrecidas para la selección inicial del día."""
    return await obtener_setup_desafio(user_id=user_id, date=date)

@router.post(
    "/reiniciar",
    summary="Reiniciar partida de hoy para volver a Fase 0 (Setup limpio)",
    tags=["Narrativo - Flujo de Juego"]
)
async def endpoint_reiniciar_partida(
    req: ReiniciarPartidaRequest,
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Archiva la run en curso y habilita una nueva generación desde el setup."""
    return await reiniciar_partida(
        user_id=user_id,
        date=req.date,
        expected_version=req.expected_version,
    )

@router.get(
    "/historial",
    tags=["Narrativo - Flujo de Juego"],
    response_model=HistorialPartidaResponse,
    summary="Consultar historial mensual acumulado de la partida (modal historial)"
)
async def endpoint_obtener_historial_partida(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Retorna la bitácora histórica mes a mes con todas las elecciones y balances."""
    return await obtener_historial_partida(user_id=user_id, date=date)

@router.get(
    "/inventario",
    tags=["Narrativo - Flujo de Juego"],
    response_model=InventarioPartidaResponse,
    summary="Consultar cartas en mano y tags activos del jugador (modal inventario)"
)
async def endpoint_obtener_inventario_partida(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Retorna el mazo de cartas acumuladas y los tags activos del jugador."""
    return await obtener_inventario_partida(user_id=user_id, date=date)

@router.get(
    "/corte",
    tags=["Narrativo - Flujo de Juego"],
    response_model=CortePartidaResponse,
    summary="Consultar integrantes de la corte y sus afinidades actuales (modal corte)"
)
async def endpoint_obtener_corte_partida(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Retorna los 3 consejeros de la corte y su nivel de afinidad actual (0 a 100)."""
    return await obtener_corte_partida(user_id=user_id, date=date)

@router.get(
    "/finalizacion",
    tags=["Narrativo - Flujo de Juego"],
    response_model=FinalizacionPartidaResponse,
    summary="Consultar desenlace / finalización detallada de la partida (modal fin de juego)"
)
async def endpoint_obtener_finalizacion_partida(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD"),
    user_id: int = Depends(obtener_identidad_narrativa)
):
    """Retorna los datos del epílogo final (derrota o victoria anual)."""
    return await obtener_finalizacion_partida(user_id=user_id, date=date)
