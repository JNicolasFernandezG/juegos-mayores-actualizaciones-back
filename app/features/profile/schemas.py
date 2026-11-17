from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SituacionConsejo = Literal["eje_desequilibrado", "racha_reanudada", "mes_en_mejora"]


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


class MedallasMes(BaseModel):
    mes: str = Field(..., description="Mes en formato YYYY-MM")
    juegos: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Conteo por juego: {juego: {S,A,B,C,F}}",
    )


class ConsejoPerfil(BaseModel):
    id: str = Field(..., description="Identificador estable del consejo")
    texto: str = Field(..., description="Mensaje del consejo")
    fuente: str = Field(..., description="Referencia bibliográfica corta")
    url: str = Field(..., description="Enlace a la fuente")
    situacion: Optional[SituacionConsejo] = Field(
        None,
        description=(
            "Situación del progreso con la que se empareja el consejo; "
            "vacío significa que sirve para cualquier momento"
        ),
    )


class ConsejoAdmin(ConsejoPerfil):
    orden: int = Field(0, description="Orden de aparición; menor primero")
    activo: bool = Field(True, description="Si se muestra en el perfil")
    updated_at: Optional[str] = Field(None, description="Última edición (ISO 8601)")


class ConsejoUpsert(BaseModel):
    texto: str = Field(..., min_length=1, max_length=280)
    fuente: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=8, max_length=300, pattern=r"^https?://\S+$")
    orden: int = Field(0, ge=0, le=9999)
    activo: bool = True
    situacion: Optional[SituacionConsejo] = Field(
        None,
        description="Situación del progreso a la que responde; vacío = consejo general",
    )

    @field_validator("texto", "fuente")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El campo no puede quedar vacío.")
        return limpio

    @field_validator("url")
    @classmethod
    def _url_limpia(cls, valor: str) -> str:
        return valor.strip()


class RendimientoJuego(BaseModel):
    completadas: int = Field(0, ge=0, description="Días con desafío completado")
    mejor_tiempo_segundos: Optional[int] = Field(None, description="Mejor tiempo registrado en segundos")
    promedio_tiempo_segundos: Optional[int] = Field(None, description="Tiempo promedio en segundos")
    ultima_fecha: Optional[str] = Field(None, description="Último día jugado (YYYY-MM-DD)")


class PerfilResumenResponse(BaseModel):
    periodo: PeriodoPerfil
    medallas: MedallasBloque
    meses: List[MedallasMes] = Field(
        default_factory=list,
        description="Conteos por mes de los últimos doce, incluido el mes actual con ceros",
    )
    rendimiento: Dict[str, RendimientoJuego] = Field(
        default_factory=dict,
        description="Métricas por juego para los juegos con calificación",
    )
    actividad: List[str] = Field(
        default_factory=list,
        description="Días con ingreso registrado dentro de la ventana, ordenados",
    )
    completadas_por_dia: Dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Desafíos completados por día dentro de la ventana, incluido el narrativo"
        ),
    )
    consejos: List[ConsejoPerfil] = Field(
        default_factory=list,
        description="Consejos activos del perfil, ordenados",
    )
