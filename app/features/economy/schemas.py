from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any


class TiendaPaquete(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Identificador único del paquete")
    vidas: int = Field(..., ge=1, description="Cantidad de vidas otorgadas")
    puntos: int = Field(..., ge=1, description="Costo en puntos del paquete")
    popular: bool = Field(False, description="Destacar como paquete popular")
    badge: Optional[str] = Field(None, description="Etiqueta visible ej: 'Popular', 'Mejor Ahorro'")
    descuento: Optional[str] = Field(None, description="Leyenda de ahorro ej: 'Ahorrá 30 pts'")


class EconomyConfigResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vidas_iniciales: int = Field(5, ge=1, description="Vidas con las que arranca cada cuenta nueva")
    costo_vida_puntos: int = Field(50, ge=1, description="Costo base de 1 vida en puntos")
    costo_desbloqueo_dia_puntos: int = Field(100, ge=0, description="Costo en puntos para desbloquear un día histórico")
    paquetes_tienda: List[TiendaPaquete] = Field(default_factory=list, description="Opciones de canje en la mini-tienda")
    puntos_por_juego: Dict[str, int] = Field(
        default_factory=lambda: {
            "wordle": 50,
            "sopa_letras": 50,
            "sudoku": 60,
            "crucigrama": 70,
            "narrativo": 80,
        },
        description="Puntos que otorga cada juego al completar un desafío",
    )
    vidas_maximas: Optional[int] = Field(None, description="Tope de vidas acumulables (null para ilimitado)")
    updated_at: Optional[str] = None


class EconomyConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vidas_iniciales: Optional[int] = Field(None, ge=1, description="Vidas iniciales para cuentas nuevas")
    costo_vida_puntos: Optional[int] = Field(None, ge=1, description="Costo base de 1 vida en puntos")
    costo_desbloqueo_dia_puntos: Optional[int] = Field(None, ge=0, description="Costo en puntos para desbloquear un día histórico")
    paquetes_tienda: Optional[List[TiendaPaquete]] = None
    puntos_por_juego: Optional[Dict[str, int]] = None
    vidas_maximas: Optional[int] = None


class UserEconomyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: int
    vidas: int
    puntos: int
    racha: int = 1
    suscripcion: str = Field("basica", description="'basica' | 'premium'")
    dias_desbloqueados: List[str] = Field(default_factory=list, description="Días históricos desbloqueados ej: ['crucigrama:2026-10-15']")
    updated_at: Optional[str] = None


class ConsumeLifeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    game_id: Optional[str] = Field(None, description="Juego en el que se consumió la vida")
    motivo: Optional[str] = Field("error", description="error | reintento | inicio")


class ConsumeLifeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    vidas_restantes: int
    consumidas: int = 1
    message: Optional[str] = None


class BuyLivesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    package_id: Optional[str] = Field(None, description="ID del paquete de tienda seleccionado (ej: pack_1, pack_3)")
    vidas: Optional[int] = Field(None, ge=1, description="Cantidad directa de vidas a comprar si no se usa paquete")


class BuyLivesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    vidas: int
    puntos: int
    compradas: int
    costo: int
    message: str


class UnlockDayRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    game_id: str = Field(..., description="ID del juego: wordle, crucigrama, sopa_letras, sudoku")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha YYYY-MM-DD del día a desbloquear")


class UnlockDayResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    unlocked: bool
    puntos: int
    costo: int
    date: str
    game_id: str
    message: str


class CambiarSuscripcionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    suscripcion: str = Field("basica", pattern=r"^(basica|premium)$", description="'basica' o 'premium'")


class SearchUserEconomyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    email: Optional[str] = None
    codigoAcceso: Optional[str] = None
    vidas: int
    puntos: int
    suscripcion: str = "basica"
    dias_desbloqueados: List[str] = []


class AdjustUserEconomyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    identificador: str = Field(..., description="Email, código de acceso PIN o ID del usuario")
    vidas_sumar: Optional[int] = Field(None, description="Cantidad de vidas a sumar (positivo) o restar (negativo)")
    puntos_sumar: Optional[int] = Field(None, description="Cantidad de puntos a sumar (positivo) o restar (negativo)")
    vidas_set: Optional[int] = Field(None, ge=0, description="Fijar vidas a un valor exacto")
    puntos_set: Optional[int] = Field(None, ge=0, description="Fijar puntos a un valor exacto")
    suscripcion_set: Optional[str] = Field(None, pattern=r"^(basica|premium)$", description="Cambiar suscripción a 'basica' o 'premium'")


class AdjustUserEconomyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    user_id: int
    name: str
    email: Optional[str] = None
    codigoAcceso: Optional[str] = None
    vidas: int
    puntos: int
    suscripcion: str
    message: str
