# ============================================================================
# EXPORTACIÓN CENTRALIZADA DE MODELOS PYDANTIC DEL MOTOR NARRATIVO
# ============================================================================

from app.features.narrative.schemas.rules_schemas import (
    CondicionSchema,
    AccionSchema,
    EfectoSchema
)

from app.features.narrative.schemas.catalog_schemas import (
    RecursoDefinicionSchema,
    UniversoCreateRequest,
    UniversoResponse,
    PersonajeConversacionProbabilidad,
    PersonajeCreateRequest,
    PersonajeResponse,
    CartaCreateRequest,
    CartaResponse,
    ImpactoAfinidadSchema,
    ResultadoCreateRequest,
    ResultadoResponse,
    ModificadorProbabilidadSchema,
    ResultadoPosibleSchema,
    OpcionEventoSchema,
    EventoCreateRequest,
    ConversacionFraseSchema,
    ConversacionDecisionSchema,
    ConversacionRequisitoSchema,
    ConversacionCreateRequest,
    ConversacionResponse,
    FinalizacionCreateRequest,
    FinalizacionResponse,
    TagCreateRequest,
    TagUpdateRequest,
    TagResponse
)

from app.features.narrative.schemas.game_schemas import (
    HistorialMes,
    IniciarPartidaRequest,
    ElegirCartaMesRequest,
    AvanzarMesRequest,
    ReiniciarPartidaRequest,
    SetupDesafioResponse,
    ProbabilidadDesenlaceCalculada,
    OpcionEventoCalculadaResponse,
    EventoTurnoResponse,
    HistorialPartidaResponse,
    InventarioPartidaResponse,
    PersonajeCorteDetalle,
    CortePartidaResponse,
    FinalizacionPartidaResponse,
    EstadoTurnoResponse,
    IniciarPartidaV2Response,
    ElegirCartaMesV2Response,
    AvanzarMesV2Response
)

from app.features.narrative.schemas.v2_graph_schemas import (
    ImpactoRecursoSchema,
    OpcionNodoSchema,
    OpcionClienteSchema,
    NodoNarrativoSchema,
    NodoClienteSchema,
    EventoV2GrafoSchema,
    ConversacionV2GrafoSchema,
    EventoEspecialV2GrafoSchema,
    AvanzarNodoV2Request,
    EstadoGrafoV2Response
)

__all__ = [
    # Rules
    "CondicionSchema",
    "AccionSchema",
    "EfectoSchema",
    # Catalog
    "RecursoDefinicionSchema",
    "UniversoCreateRequest",
    "UniversoResponse",
    "PersonajeConversacionProbabilidad",
    "PersonajeCreateRequest",
    "PersonajeResponse",
    "CartaCreateRequest",
    "CartaResponse",
    "ImpactoAfinidadSchema",
    "ResultadoCreateRequest",
    "ResultadoResponse",
    "ModificadorProbabilidadSchema",
    "ResultadoPosibleSchema",
    "OpcionEventoSchema",
    "EventoCreateRequest",
    "ConversacionFraseSchema",
    "ConversacionDecisionSchema",
    "ConversacionRequisitoSchema",
    "ConversacionCreateRequest",
    "ConversacionResponse",
    "FinalizacionCreateRequest",
    "FinalizacionResponse",
    # Game
    "HistorialMes",
    "IniciarPartidaRequest",
    "ElegirCartaMesRequest",
    "AvanzarMesRequest",
    "ReiniciarPartidaRequest",
    "SetupDesafioResponse",
    "ProbabilidadDesenlaceCalculada",
    "OpcionEventoCalculadaResponse",
    "EventoTurnoResponse",
    "HistorialPartidaResponse",
    "InventarioPartidaResponse",
    "PersonajeCorteDetalle",
    "CortePartidaResponse",
    "FinalizacionPartidaResponse",
    "EstadoTurnoResponse",
    "IniciarPartidaV2Response",
    "ElegirCartaMesV2Response",
    "AvanzarMesV2Response",
]
