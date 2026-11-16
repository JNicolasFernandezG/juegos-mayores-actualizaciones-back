from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PeriodoPerfil(BaseModel):
    mes: str = Field(..., description="Mes consultado en formato YYYY-MM")
    desde: str = Field(..., description="Primer día de la ventana de actividad (YYYY-MM-DD)")
    hasta: str = Field(..., description="Último día con datos considerados (YYYY-MM-DD)")


class MedallasBloque(BaseModel):
    mes_actual: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Conteo de calificaciones del mes por juego: {juego: {S,A,B,C,F}}",
    )
    historico: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Conteo histórico de calificaciones por juego: {juego: {S,A,B,C,F}}",
    )


class RendimientoJuego(BaseModel):
    completadas: int = Field(0, ge=0, description="Días con desafío completado")
    mejor_tiempo_segundos: Optional[int] = Field(None, description="Mejor tiempo registrado en segundos")
    promedio_tiempo_segundos: Optional[int] = Field(None, description="Tiempo promedio en segundos")
    ultima_fecha: Optional[str] = Field(None, description="Último día jugado (YYYY-MM-DD)")


class PerfilResumenResponse(BaseModel):
    periodo: PeriodoPerfil
    medallas: MedallasBloque
    rendimiento: Dict[str, RendimientoJuego] = Field(
        default_factory=dict,
        description="Métricas por juego para los juegos con calificación",
    )
    actividad: List[str] = Field(
        default_factory=list,
        description="Días con ingreso registrado dentro de la ventana, ordenados",
    )
