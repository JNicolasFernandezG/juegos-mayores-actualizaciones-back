from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

from app.features.narrative.schemas.catalog_schemas import (
    PersonajeResponse,
    CartaResponse,
    ResultadoResponse,
    ConversacionResponse,
    FinalizacionResponse
)
from app.features.narrative.schemas.v2_graph_schemas import EstadoGrafoV2Response

# ============================================================================
# 1. HISTORIAL MENSUAL DE LA PARTIDA
# ============================================================================

class HistorialMes(BaseModel):
    mes: int
    carta_elegida_id: Optional[str] = None
    evento_id: Optional[str] = None
    opcion_elegida_id: Optional[str] = None
    resultado_id: Optional[str] = None
    conversacion_id: Optional[str] = None
    decision_conversacion_opcion: Optional[int] = None
    recursos_fin_mes: Dict[str, int]

# ============================================================================
# 2. DTOs DE ENTRADA (REQUESTS DEL JUGADOR)
# ============================================================================

class IniciarPartidaRequest(BaseModel):
    date: str
    corte_elegida_ids: List[str]
    cartas_iniciales_ids: List[str]

class ElegirCartaMesRequest(BaseModel):
    date: str
    carta_id: str

class AvanzarMesRequest(BaseModel):
    date: str

class ReiniciarPartidaRequest(BaseModel):
    date: str
    expected_version: Optional[int] = Field(
        None,
        ge=0,
        description="Versión leída antes de reiniciar; si cambió, la operación responde 409.",
    )

# ============================================================================
# 3. DTOs DE CÁLCULO DE PROBABILIDADES Y TURNO
# ============================================================================

class SetupDesafioResponse(BaseModel):
    date: str
    universo_id: str
    universo_nombre: str
    universo_descripcion: str = ""
    atributos_iniciales: Dict[str, int]
    personajes_ofrecidos: List[PersonajeResponse]
    cartas_ofrecidas: List[CartaResponse]
    tiene_partida_activa: bool = False
    fase_partida_activa: Optional[str] = None

class ProbabilidadDesenlaceCalculada(BaseModel):
    resultado_id: str
    titulo: str
    porcentaje: float
    explicaciones: List[str] = []

class OpcionEventoCalculadaResponse(BaseModel):
    id: str
    texto: str
    es_secreta: bool
    bloqueada: bool
    probabilidades: List[ProbabilidadDesenlaceCalculada]

class EventoTurnoResponse(BaseModel):
    id: str
    titulo: str
    descripcion: str
    imagen: str
    opciones: List[OpcionEventoCalculadaResponse]

# ============================================================================
# 5. DTOs PARA ENDPOINTS DE CONSULTA ESPECIALIZADOS (BAJO DEMANDA)
# ============================================================================

class HistorialPartidaResponse(BaseModel):
    date: str
    mes_actual: int
    status: str
    fase_actual: str
    historial_mensual: List[Union[HistorialMes, str, Dict[str, Any]]]

class InventarioPartidaResponse(BaseModel):
    date: str
    cartas: List[CartaResponse]
    tags_activos: List[str]

class PersonajeCorteDetalle(BaseModel):
    personaje: PersonajeResponse
    afinidad: int

class CortePartidaResponse(BaseModel):
    date: str
    corte: List[PersonajeCorteDetalle]
    afinidad: Dict[str, int]

class FinalizacionPartidaResponse(BaseModel):
    date: str
    status: str
    mes_actual: int
    finalizacion: Optional[FinalizacionResponse] = None
    epilogo_final: Optional[Dict[str, Any]] = None

class EstadoTurnoResponse(BaseModel):
    date: str
    mes_actual: int
    fase_actual: str
    status: str
    recursos: Dict[str, int]
    afinidad: Dict[str, int]
    cartas_draft_actual: List[CartaResponse] = []
    evento_actual: Optional[EventoTurnoResponse] = None
    resultado_actual: Optional[ResultadoResponse] = None
    conversacion_actual: Optional[ConversacionResponse] = None
    finalizacion: Optional[FinalizacionResponse] = None
    grafo_actual: Optional[EstadoGrafoV2Response] = None
    motor: Optional[str] = "v1"

# ============================================================================
# 7. DTOs DEL MOTOR V2 LIGERO (DELTAS POR FASE)
# ============================================================================

class IniciarPartidaV2Response(BaseModel):
    mes_actual: int = 1
    fase_actual: str = "DRAFT_MENSUAL"
    recursos: Dict[str, int]
    afinidad: Dict[str, int]
    cartas_draft_actual: List[CartaResponse]
    finalizacion: Optional[FinalizacionResponse] = None
    motor: Optional[str] = "v1"
    puntos_ganados: Optional[int] = None

class ElegirCartaMesV2Response(BaseModel):
    fase_actual: str = "TOMA_DECISION_EVENTO"
    recursos: Dict[str, int]
    evento_actual: Optional[EventoTurnoResponse] = None
    finalizacion: Optional[FinalizacionResponse] = None
    grafo_actual: Optional[EstadoGrafoV2Response] = None
    puntos_ganados: Optional[int] = None
    motor: Optional[str] = "v1"

class AvanzarMesV2Response(BaseModel):
    mes_actual: int
    fase_actual: str
    status: str
    recursos: Dict[str, int]
    cartas_draft_actual: List[CartaResponse] = []
    finalizacion: Optional[FinalizacionResponse] = None
    puntos_ganados: Optional[int] = None
