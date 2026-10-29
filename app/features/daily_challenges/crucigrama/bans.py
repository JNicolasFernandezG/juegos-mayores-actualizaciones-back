"""
bans.py
Vetos globales de palabras del crucigrama.

Se guardan una sola vez y se aplican a toda la generación de tableros (mensual y
reintentos) y al diseñador administrativo. No modifican desafíos ya generados.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.database import get_database
from app.features.daily_challenges.crucigrama.solver import (
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    normalize_word,
)

COLLECTION = "crucigrama_settings"
DOC_ID = "global_bans"


def clean_words(words: Iterable[str], estricto: bool = False) -> List[str]:
    """
    Normaliza, deduplica y ordena. En modo estricto rechaza palabras no alfabéticas
    o con longitud fuera del rango del juego (3..10).
    """
    limpias: List[str] = []
    for raw in words or []:
        word = normalize_word(raw)
        if not word:
            continue
        if not word.isalpha():
            if estricto:
                raise ValueError(f"Palabra inválida: '{raw}'. Solo se admiten letras.")
            continue
        if not (MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN):
            if estricto:
                raise ValueError(
                    f"'{raw}' debe tener entre {MIN_WORD_LEN} y {MAX_WORD_LEN} letras."
                )
            continue
        if word not in limpias:
            limpias.append(word)
    return sorted(limpias)


async def get_global_banned_words() -> List[str]:
    doc = await get_database()[COLLECTION].find_one({"_id": DOC_ID})
    return clean_words((doc or {}).get("banned_words") or [])


async def get_global_bans_doc() -> Dict[str, Any]:
    doc = await get_database()[COLLECTION].find_one({"_id": DOC_ID}) or {}
    return {
        "banned_words": clean_words(doc.get("banned_words") or []),
        "updated_by": doc.get("updated_by"),
        "updated_at": doc.get("updated_at"),
    }


async def set_global_banned_words(
    words: Iterable[str], updated_by: Optional[str] = None
) -> List[str]:
    limpias = clean_words(words, estricto=True)
    changes: Dict[str, Any] = {
        "banned_words": limpias,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if updated_by:
        changes["updated_by"] = updated_by
    await get_database()[COLLECTION].update_one(
        {"_id": DOC_ID}, {"$set": changes}, upsert=True
    )
    return limpias
