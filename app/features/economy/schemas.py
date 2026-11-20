from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features.economy.defaults import (  # noqa: F401
    DEFAULT_BONUS_RACHA,
    DEFAULT_ESCALAS_TIEMPO,
    DEFAULT_PUNTOS_POR_CALIFICACION,
    DEFAULT_PUNTOS_POR_JUEGO,
)


class _EconomyModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EscalaCalificacionTiempo(_EconomyModel):
    grade: str = Field(..., description="Letra o código de la calificación (ej: 'S', 'A', 'B', 'C', 'D')")
    tiempo_max_segundos: int = Field(..., ge=1, description="Tiempo máximo en segundos para obtener esta calificación")
    puntos: int = Field(..., ge=0, description="Puntos otorgados al completar en este rango")
    estrellas: int = Field(3, ge=0, le=3, description="Estrellas visuales otorgadas (0 a 3)")
    titulo: Optional[str] = Field(None, description="Título amigable ej: '¡Impecable!', '¡Excelente!'")
    descripcion: Optional[str] = Field(None, description="Descripción del rango ej: 'Menos de 03:00'")


class TramoBonusRacha(_EconomyModel):
    dias: int = Field(..., ge=1, le=3650, description="Días de racha necesarios para que aplique el tramo")
    valor: int = Field(..., ge=0, le=10000, description="Boost del tramo: porcentaje sobre el puntaje base o puntos fijos según el modo")


class BonusRachaConfig(_EconomyModel):
    activo: bool = Field(False, description="Habilita el boost de puntos por racha")
    modo: Literal["porcentaje", "puntos_fijos"] = Field("porcentaje", description="'porcentaje' del puntaje base o 'puntos_fijos' por tramo")
    tramos: List[TramoBonusRacha] = Field(default_factory=list, description="Umbrales de racha; se aplica solo el tramo de mayor 'dias' alcanzado")

    @field_validator("tramos")
    @classmethod
    def _dias_sin_duplicados(cls, tramos: List[TramoBonusRacha]) -> List[TramoBonusRacha]:
        dias = [tramo.dias for tramo in tramos]
        if len(set(dias)) != len(dias):
            raise ValueError("Los tramos de racha no pueden repetir días.")
        return tramos

    @model_validator(mode="after")
    def _coherencia_del_bonus(self) -> "BonusRachaConfig":
        if self.activo and not self.tramos:
            raise ValueError("El bonus por racha activo requiere al menos un tramo.")
        if self.modo == "porcentaje" and any(tramo.valor > 500 for tramo in self.tramos):
            raise ValueError("En modo porcentaje el boost máximo por tramo es 500%.")
        return self


def _default_escalas_tiempo() -> Dict[str, List[EscalaCalificacionTiempo]]:
    return {k: [EscalaCalificacionTiempo(**item) for item in v] for k, v in DEFAULT_ESCALAS_TIEMPO.items()}


def _default_bonus_racha() -> BonusRachaConfig:
    return BonusRachaConfig(**DEFAULT_BONUS_RACHA)


class EconomyConfigResponse(_EconomyModel):
    vidas_iniciales: int = Field(5, ge=1, description="Vidas con las que arranca cada cuenta nueva (deprecado/local)")
    costo_desbloqueo_dia_puntos: int = Field(100, ge=0, description="Costo en puntos para desbloquear un día histórico")
    costo_pista_puntos: int = Field(20, ge=0, description="Costo en puntos para solicitar una pista")
    puntos_por_calificacion: Dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_PUNTOS_POR_CALIFICACION), description="Puntos otorgados según calificación S, A, B, C, F")
    escalas_tiempo_por_juego: Dict[str, List[EscalaCalificacionTiempo]] = Field(default_factory=_default_escalas_tiempo, description="Escalas de calificación por tiempo configuradas por juego")
    puntos_por_juego: Dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_PUNTOS_POR_JUEGO), description="Puntos que otorga cada juego al completar un desafío")
    guest_migration_max_points: int = Field(1000, ge=0, description="Tope de puntos de invitado que una cuenta puede reclamar al registrarse")
    bonus_racha: BonusRachaConfig = Field(default_factory=_default_bonus_racha, description="Boost de puntos aplicado al completar desafíos con una racha activa")
    updated_at: Optional[str] = None


class EconomyConfigUpdateRequest(_EconomyModel):
    vidas_iniciales: Optional[int] = Field(None, ge=1, description="Vidas iniciales para cuentas nuevas")
    costo_desbloqueo_dia_puntos: Optional[int] = Field(None, ge=0, description="Costo en puntos para desbloquear un día histórico")
    costo_pista_puntos: Optional[int] = Field(None, ge=0, description="Costo en puntos para solicitar una pista")
    puntos_por_calificacion: Optional[Dict[str, int]] = Field(None, description="Puntos otorgados según calificación S, A, B, C, F")
    escalas_tiempo_por_juego: Optional[Dict[str, List[EscalaCalificacionTiempo]]] = Field(None, description="Escalas de calificación por tiempo por juego (sudoku, crucigrama, sopa_letras)")
    puntos_por_juego: Optional[Dict[str, int]] = None
    guest_migration_max_points: Optional[int] = Field(None, ge=0, description="Tope de puntos de invitado reclamables por cuenta")
    bonus_racha: Optional[BonusRachaConfig] = Field(None, description="Boost de puntos por racha; omitirlo conserva la configuración actual")


class UserEconomyResponse(_EconomyModel):
    user_id: int
    vidas: Optional[int] = Field(5, description="Deprecado: vidas globales informativas")
    puntos: int
    racha: int = Field(0, description="Días consecutivos en que el usuario abrió la aplicación con sesión válida")
    racha_ultima_fecha: Optional[str] = Field(None, description="Último día con ingreso registrado en formato YYYY-MM-DD")
    racha_hoy_ingresada: bool = Field(False, description="Indica si el usuario ya abrió la aplicación hoy (ART)")
    racha_puntos_dia: int = Field(0, description="Puntos diarios que entrega el día de racha en que se encuentra el usuario")
    racha_tramos_diarios: List[Dict[str, int]] = Field(default_factory=list, description="Tramos de puntos diarios por racha: [{'dias': 1, 'puntos': 40}, ...]")
    suscripcion: str = Field("basica", description="'basica' | 'premium'")
    dias_desbloqueados: List[str] = Field(default_factory=list, description="Días históricos desbloqueados ej: ['crucigrama:2026-10-15']")
    costo_pista_puntos: int = Field(20, description="Costo en puntos para solicitar una pista")
    costo_desbloqueo_dia_puntos: int = Field(100, ge=0, description="Costo en puntos para desbloquear un día histórico")
    bonus_racha: BonusRachaConfig = Field(default_factory=_default_bonus_racha, description="Hitos y recompensa del bonus por racha vigente")
    updated_at: Optional[str] = None


class ConsumeLifeRequest(_EconomyModel):
    game_id: Optional[str] = Field(None, description="Juego en el que se consumió la vida")
    motivo: Optional[str] = Field("error", description="error | reintento | inicio")


class ConsumeLifeResponse(_EconomyModel):
    success: bool
    vidas_restantes: int
    consumidas: int = 1
    message: Optional[str] = None


class RefillLivesResponse(_EconomyModel):
    success: bool
    puntos: int = Field(..., description="Saldo de puntos restante tras la recarga")
    message: str


class UnlockDayRequest(_EconomyModel):
    game_id: str = Field(..., description="ID del juego: wordle, crucigrama, sopa_letras, sudoku")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD del día a desbloquear")


class UnlockDayResponse(_EconomyModel):
    success: bool
    unlocked: bool
    puntos: int
    costo: int
    date: str
    game_id: str
    message: str


class CambiarSuscripcionRequest(_EconomyModel):
    suscripcion: str = Field("basica", pattern=r"^(basica|premium)$", description="'basica' o 'premium'")


class SearchUserEconomyResponse(_EconomyModel):
    id: int
    name: str
    email: Optional[str] = None
    codigoAcceso: Optional[str] = None
    vidas: int
    puntos: int
    suscripcion: str = "basica"
    dias_desbloqueados: List[str] = []


class AdjustUserEconomyRequest(_EconomyModel):
    identificador: str = Field(..., description="Email, código de acceso PIN o ID del usuario")
    vidas_sumar: Optional[int] = Field(None, description="Cantidad de vidas a sumar (positivo) o restar (negativo)")
    puntos_sumar: Optional[int] = Field(None, description="Cantidad de puntos a sumar (positivo) o restar (negativo)")
    vidas_set: Optional[int] = Field(None, ge=0, description="Fijar vidas a un valor exacto")
    puntos_set: Optional[int] = Field(None, ge=0, description="Fijar puntos a un valor exacto")
    suscripcion_set: Optional[str] = Field(None, pattern=r"^(basica|premium)$", description="Cambiar suscripción a 'basica' o 'premium'")


class AdjustUserEconomyResponse(_EconomyModel):
    success: bool
    user_id: int
    name: str
    email: Optional[str] = None
    codigoAcceso: Optional[str] = None
    vidas: int
    puntos: int
    suscripcion: str
    message: str


class UseHintRequest(_EconomyModel):
    game_id: str = Field(..., description="ID del juego: wordle, sudoku, sopa_letras, crucigrama")
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD del desafío")
    difficulty: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_-]{1,32}$", description="Dificultad de la partida; si falta se infiere del intento del usuario")
    hint_index: Optional[int] = Field(0, ge=0, le=1000, description="Índice de la pista a consultar (para Wordle o Sopa de Letras)")
    row: Optional[int] = Field(None, description="Fila de la casilla a revelar (Sudoku / Crucigrama)")
    col: Optional[int] = Field(None, description="Columna de la casilla a revelar (Sudoku / Crucigrama)")


class UseHintResponse(_EconomyModel):
    success: bool
    puntos_restantes: int = Field(..., description="Saldo actualizado de puntos del usuario")
    puntos_descontados: int = Field(20, description="Puntos descontados por solicitar la pista")
    vidas_restantes: Optional[int] = Field(None, description="Deprecado / informativo")
    vidas_descontadas: Optional[int] = Field(0, description="Deprecado / informativo")
    pista: Optional[str] = Field(None, description="Texto de la pista generada o definición RAE")
    valor_revelado: Optional[Any] = Field(None, description="Número o letra revelada si aplica (ej: celda de Sudoku o letra de Crucigrama)")
    message: str


class GuestMigrationRequest(_EconomyModel):
    guest_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,64}$", description="Identificador anónimo (X-Guest-Id) con el que se acumularon puntos sin cuenta")
    puntos: int = Field(..., ge=0, description="Puntos informados por el cliente; el servidor aplica el tope configurado")


class GuestMigrationResponse(_EconomyModel):
    success: bool
    ya_migrado: bool = Field(..., description="True si la cuenta ya había reclamado puntos de invitado")
    puntos_solicitados: int
    puntos_migrados: int
    tope: int
    puntos_totales: int = Field(..., description="Saldo total de puntos de la cuenta tras la migración")
    message: str
