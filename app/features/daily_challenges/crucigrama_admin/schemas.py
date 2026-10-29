"""Schemas del diseñador administrativo de máscaras de crucigrama."""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.features.daily_challenges.crucigrama.solver import MAX_WORD_LEN, MIN_WORD_LEN

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
DIFFICULTY_PATTERN = r"^(facil|dificil)$"

MAX_ATTEMPT_BUDGET = 2_000_000
MAX_BANNED_WORDS = 100
MAX_GLOBAL_BANNED_WORDS = 300
MAX_DICTIONARY_WORDS = 60

_LETRAS = re.compile(r"^[A-ZÑÁÉÍÓÚÜ]+$")


def _clean_word_list(values: List[str], limite: int, descripcion: str) -> List[str]:
    limpias: List[str] = []
    for raw in values or []:
        word = str(raw or "").strip().upper()
        if not word:
            continue
        if not _LETRAS.match(word):
            raise ValueError(f"Palabra inválida: '{raw}'. Solo se admiten letras.")
        if word not in limpias:
            limpias.append(word)
    if len(limpias) > limite:
        raise ValueError(f"Se admiten como máximo {limite} {descripcion}.")
    return limpias


def _clean_seed(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    limpia = str(value).strip()
    if not limpia:
        return None
    if len(limpia) > 64:
        raise ValueError("La semilla admite como máximo 64 caracteres.")
    if any(ch.isspace() for ch in limpia):
        raise ValueError("La semilla no puede contener espacios.")
    return limpia


class CrucigramaMaskValidateRequest(BaseModel):
    pattern: List[str] = Field(..., description="Máscara: filas con '.' (letra) y '#' (bloque)")
    anchors: Dict[str, str] = Field(
        default_factory=dict, description="Palabras fijas por id de slot (máximo recomendado: 2)"
    )
    fixed_words: Dict[str, str] = Field(
        default_factory=dict,
        description="Palabras fijadas temporalmente por slot (reemplazos puntuales)",
    )
    banned_words: List[str] = Field(
        default_factory=list, description="Palabras vetadas: no se usan en ningún slot"
    )
    seed: Optional[str] = Field(
        None, description="Semilla de exploración: cambiarla cambia la solución"
    )
    difficulty: Optional[str] = Field(
        None, pattern=DIFFICULTY_PATTERN, description="facil|dificil; define el orden de pistas"
    )
    prefer_curated: Optional[bool] = Field(
        None, description="Priorizar pistas curadas; por defecto depende de la dificultad"
    )
    attempt_budgets: Optional[List[int]] = Field(
        None, description=f"Presupuestos de nodos por intento (1..{MAX_ATTEMPT_BUDGET})"
    )

    @field_validator("attempt_budgets")
    @classmethod
    def _validate_attempt_budgets(cls, value: Optional[List[int]]) -> Optional[List[int]]:
        if value is None:
            return value
        if not value:
            raise ValueError("attempt_budgets no puede estar vacío.")
        if len(value) > 10:
            raise ValueError("Se admiten como máximo 10 intentos.")
        if any(budget <= 0 or budget > MAX_ATTEMPT_BUDGET for budget in value):
            raise ValueError(
                f"Cada presupuesto debe estar entre 1 y {MAX_ATTEMPT_BUDGET} nodos."
            )
        return value

    @field_validator("banned_words")
    @classmethod
    def _validate_banned_words(cls, value: List[str]) -> List[str]:
        return _clean_word_list(value, MAX_BANNED_WORDS, "palabras vetadas")

    @field_validator("seed")
    @classmethod
    def _validate_seed(cls, value: Optional[str]) -> Optional[str]:
        return _clean_seed(value)


class CrucigramaTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    theme: str = Field("Palabras Cruzadas", max_length=120)
    pattern: List[str]
    difficulty: str = Field("facil", pattern=DIFFICULTY_PATTERN)
    anchors: Dict[str, str] = Field(default_factory=dict)
    banned_words: List[str] = Field(default_factory=list)
    clue_overrides: Dict[str, str] = Field(default_factory=dict)
    scheduled_date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    monthly_day: Optional[int] = Field(
        None, ge=1, le=31, description="Día del mes en que se repite la plantilla"
    )
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("banned_words")
    @classmethod
    def _validate_banned_words(cls, value: List[str]) -> List[str]:
        return _clean_word_list(value, MAX_BANNED_WORDS, "palabras vetadas")


class CrucigramaTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    theme: Optional[str] = Field(None, max_length=120)
    pattern: Optional[List[str]] = None
    difficulty: Optional[str] = Field(None, pattern=DIFFICULTY_PATTERN)
    anchors: Optional[Dict[str, str]] = None
    banned_words: Optional[List[str]] = None
    clue_overrides: Optional[Dict[str, str]] = None
    scheduled_date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    monthly_day: Optional[int] = Field(
        None, ge=1, le=31, description="Día del mes en que se repite la plantilla"
    )
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("banned_words")
    @classmethod
    def _validate_banned_words(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        return _clean_word_list(value, MAX_BANNED_WORDS, "palabras vetadas")


class CrucigramaPublishRequest(BaseModel):
    scheduled_date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    monthly_day: Optional[int] = Field(
        None, ge=1, le=31, description="Día del mes en que se repite la plantilla"
    )
    prefer_curated: Optional[bool] = None
    solution_grid: Optional[List[str]] = Field(
        None,
        description="Solución aprobada en el editor; si viene, se publica tal cual",
    )
    banned_words: List[str] = Field(default_factory=list)
    seed: Optional[str] = None

    @field_validator("banned_words")
    @classmethod
    def _validate_banned_words(cls, value: List[str]) -> List[str]:
        return _clean_word_list(value, MAX_BANNED_WORDS, "palabras vetadas")

    @field_validator("seed")
    @classmethod
    def _validate_seed(cls, value: Optional[str]) -> Optional[str]:
        return _clean_seed(value)


class CrucigramaDictionaryRequest(BaseModel):
    words: List[str] = Field(
        ..., min_length=1, max_length=MAX_DICTIONARY_WORDS, description="Palabras a consultar en la RAE"
    )

    @field_validator("words")
    @classmethod
    def _validate_words(cls, value: List[str]) -> List[str]:
        return _clean_word_list(value, MAX_DICTIONARY_WORDS, "palabras")


class CrucigramaGlobalBansRequest(BaseModel):
    banned_words: List[str] = Field(
        default_factory=list,
        description="Palabras vetadas para todos los tableros (reemplaza la lista completa)",
    )

    @field_validator("banned_words")
    @classmethod
    def _validate_banned_words(cls, value: List[str]) -> List[str]:
        limpias = _clean_word_list(value, MAX_GLOBAL_BANNED_WORDS, "palabras vetadas globales")
        invalidas = [
            word for word in limpias if not (MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN)
        ]
        if invalidas:
            raise ValueError(
                f"Las palabras vetadas globales deben tener entre {MIN_WORD_LEN} y "
                f"{MAX_WORD_LEN} letras: {', '.join(invalidas)}."
            )
        return limpias


class CrucigramaApplyRequest(BaseModel):
    date: str = Field(..., pattern=DATE_PATTERN)
    force: bool = Field(True, description="Sobrescribir el desafío si ya existe para esa fecha")


class CrucigramaTemplateSummary(BaseModel):
    id: str
    name: str
    theme: str
    difficulty: str
    size: int
    status: str
    scheduled_date: Optional[str] = None
    monthly_day: Optional[int] = None
    total_words: int = 0
    anchors: Dict[str, str] = Field(default_factory=dict)
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    published_at: Optional[str] = None
    archived_at: Optional[str] = None


class CrucigramaTemplateDetail(CrucigramaTemplateSummary):
    pattern: List[str]
    banned_words: List[str] = Field(default_factory=list)
    clue_overrides: Dict[str, str] = Field(default_factory=dict)
    solution_grid: Optional[List[str]] = None
    clues: Dict[str, str] = Field(default_factory=dict)
    published_config: Optional[Dict[str, Any]] = None
    last_seed: Optional[str] = None
    notes: Optional[str] = None
    published_by: Optional[str] = None
    archived_by: Optional[str] = None


class CrucigramaTemplateListResponse(BaseModel):
    total: int
    limit: int
    skip: int
    items: List[CrucigramaTemplateSummary]
