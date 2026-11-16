"""Contratos del catálogo de planes de suscripción."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class PrecioPlan(BaseModel):
    monto: Optional[float] = Field(
        None,
        ge=0,
        description="Importe mensual en la moneda del plan; nulo si todavía no se definió",
    )
    moneda: str = Field("ARS", pattern=r"^[A-Z]{3}$", description="Código ISO de la moneda")


def _limpiar_beneficios(valores: List[str]) -> List[str]:
    limpios: List[str] = []
    for valor in valores:
        texto = valor.strip()
        if not texto:
            continue
        if len(texto) > 120:
            raise ValueError("Cada beneficio admite hasta 120 caracteres.")
        if texto not in limpios:
            limpios.append(texto)
    return limpios


class PlanSuscripcion(BaseModel):
    codigo: str = Field(..., description="Identificador estable del plan")
    nombre: str
    descripcion: str = ""
    precio: PrecioPlan = Field(default_factory=PrecioPlan, description="Precio del cobro mensual")
    descuento_anual_pct: float = Field(
        0, ge=0, le=100, description="Descuento aplicado al total de doce meses"
    )
    precio_anual: PrecioPlan = Field(
        default_factory=PrecioPlan,
        description="Precio anual derivado del mensual y el descuento; solo lectura",
    )
    beneficios: List[str] = Field(default_factory=list)
    orden: int = 0
    visible: bool = Field(True, description="Se muestra en la sección de planes del jugador")
    habilitado: bool = Field(False, description="El botón de compra del plan está activo")
    updated_at: Optional[str] = None


class CatalogoPlanes(BaseModel):
    anual_habilitado: bool = Field(
        False, description="El jugador puede elegir el cobro anual en el catálogo"
    )
    planes: List[PlanSuscripcion] = Field(default_factory=list)


class ConfigSuscripcion(BaseModel):
    anual_habilitado: bool = False
    updated_at: Optional[str] = None


class ConfigSuscripcionUpdate(BaseModel):
    anual_habilitado: bool


class PlanCreateRequest(BaseModel):
    codigo: str = Field(
        ...,
        pattern=r"^[a-z0-9][a-z0-9_-]{1,31}$",
        description="Slug en minúsculas, sin espacios",
    )
    nombre: str = Field(..., min_length=2, max_length=60)
    descripcion: str = Field("", max_length=240)
    precio: PrecioPlan = Field(default_factory=PrecioPlan)
    descuento_anual_pct: float = Field(0, ge=0, le=100)
    beneficios: List[str] = Field(default_factory=list, max_length=8)
    orden: int = Field(0, ge=0, le=999)
    visible: bool = True
    habilitado: bool = False

    @field_validator("nombre", "descripcion")
    @classmethod
    def _limpiar_texto(cls, valor: str) -> str:
        return valor.strip()

    @field_validator("beneficios")
    @classmethod
    def _validar_beneficios(cls, valores: List[str]) -> List[str]:
        return _limpiar_beneficios(valores)


class PlanUpdateRequest(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=240)
    precio: Optional[PrecioPlan] = None
    descuento_anual_pct: Optional[float] = Field(None, ge=0, le=100)
    beneficios: Optional[List[str]] = Field(None, max_length=8)
    orden: Optional[int] = Field(None, ge=0, le=999)
    visible: Optional[bool] = None
    habilitado: Optional[bool] = None

    @field_validator("nombre", "descripcion")
    @classmethod
    def _limpiar_texto(cls, valor: Optional[str]) -> Optional[str]:
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("beneficios")
    @classmethod
    def _validar_beneficios(cls, valores: Optional[List[str]]) -> Optional[List[str]]:
        return _limpiar_beneficios(valores) if valores is not None else None
