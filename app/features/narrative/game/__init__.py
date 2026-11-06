"""
Módulo de Lógica de Juego Narrativo V2 (Grafos).
- ciclo: setup, elección de carta, avance de nodo en grafo, transición mensual, estado y desenlaces.
"""

from app.features.narrative.game.router import router, router_v2
from app.features.narrative.game.universe_resources import (
    _RECURSOS_MAPA_CACHE,
    invalidar_cache_recursos_universo,
    obtener_mapa_recursos_universo,
)
from app.features.narrative.game.setup_service import (
    obtener_setup_desafio,
    iniciar_partida,
    reiniciar_partida,
)
from app.features.narrative.game.turn_service import elegir_carta_mes
from app.features.narrative.game.transition_service import avanzar_mes
from app.features.narrative.game.endings_service import (
    verificar_colapso_recursos,
    calcular_finalizacion_victoria,
    sincronizar_intento_usuario,
)
from app.features.narrative.game.modals_service import (
    obtener_historial_partida,
    obtener_inventario_partida,
    obtener_corte_partida,
    obtener_finalizacion_partida,
)
from app.features.narrative.game.turn_state import obtener_turno_actual

__all__ = [
    # Routers
    "router",
    "router_v2",
    # Recursos de universo
    "_RECURSOS_MAPA_CACHE",
    "invalidar_cache_recursos_universo",
    "obtener_mapa_recursos_universo",
    # Setup
    "obtener_setup_desafio",
    "iniciar_partida",
    "reiniciar_partida",
    # Turn Loop
    "elegir_carta_mes",
    # Transition
    "avanzar_mes",
    # Endings & Sync
    "verificar_colapso_recursos",
    "calcular_finalizacion_victoria",
    "sincronizar_intento_usuario",
    # Modals & Reactive Queries
    "obtener_historial_partida",
    "obtener_inventario_partida",
    "obtener_corte_partida",
    "obtener_finalizacion_partida",
    "obtener_turno_actual",
]
