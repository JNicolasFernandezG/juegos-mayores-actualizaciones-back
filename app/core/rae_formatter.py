"""Funciones puras de formato, candidatos y selección de definiciones RAE."""

import re
import urllib.parse
from typing import Any, Dict, List, Optional


def _strip_rae_markers(raw_text: str, word: str, mask_spoiler: bool) -> str:
    """Limpia marcas técnicas, número de acepción, abreviaturas y referencias finales."""
    replacement = "___" if mask_spoiler else word.lower()
    text = raw_text.replace("\u2016", " - ").replace("~", replacement)
    text = re.sub(r"^\s*\d+\.\s*", "", text)
    text = re.sub(r"^(?:[a-záéíóúñ]+\.\s*)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*(?:Sin\.:|Ant\.:|V\.:|Comp\.:|U\. t\. c\.).*$", "", text, flags=re.IGNORECASE)
    return text.lstrip(":.,; ").strip()


def _mask_word_mentions(text: str, word: str) -> str:
    """Reemplaza apariciones de la palabra raíz (>=4 letras) por '___'."""
    root_word = word.lower()
    if len(root_word) < 4:
        return text
    pattern = re.compile(rf"\b{re.escape(root_word)}\w*\b", re.IGNORECASE)
    return pattern.sub("___", text)


def clean_and_mask_definition(raw_text: str, word: str, mask_spoiler: bool = True) -> Optional[str]:
    """Limpia etiquetas gramaticales de la RAE y opcionalmente enmascara la palabra objetivo."""
    if not raw_text:
        return None
    text = _strip_rae_markers(raw_text, word, mask_spoiler)
    if not text or len(text) < 6:
        return None
    if mask_spoiler:
        text = _mask_word_mentions(text, word)
    if not text.endswith("."):
        text += "."
    return text[0].upper() + text[1:]


def build_search_candidates(word_upper: str, acentos_map: Dict[str, str]) -> List[str]:
    """Genera candidatos de búsqueda ordenados por probabilidad de éxito en la RAE."""
    candidates: List[str] = []
    if word_upper in acentos_map:
        candidates.append(acentos_map[word_upper])
    candidates.append(word_upper.lower())
    if word_upper.endswith("ES") and len(word_upper) >= 5:
        candidates.append(word_upper[:-2].lower())
    elif word_upper.endswith("S") and len(word_upper) >= 4:
        candidates.append(word_upper[:-1].lower())
    return list(dict.fromkeys(candidates))


def build_rae_url(term: str) -> str:
    """Construye la URL de consulta de palabra en la API de la RAE."""
    return f"https://rae-api.com/api/words/{urllib.parse.quote(term)}"


def build_rae_headers(api_key: str) -> Dict[str, str]:
    """Construye cabeceras HTTP para la API de la RAE."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def select_best_definition(
    data: Dict[str, Any], word_upper: str, mask_spoiler: bool = True
) -> Optional[str]:
    """Elige la mejor acepción pedagógica (>3 palabras sin spoiler) de una respuesta RAE."""
    meanings = (data.get("data") or {}).get("meanings", [])
    senses = (meanings[0] or {}).get("senses", []) if meanings else []
    best_cleaned: Optional[str] = None
    for sense in senses:
        cleaned = clean_and_mask_definition(sense.get("raw", ""), word_upper, mask_spoiler=mask_spoiler)
        if not cleaned:
            continue
        if len(cleaned.split()) >= 4 and not cleaned.startswith("___"):
            return cleaned
        if not best_cleaned:
            best_cleaned = cleaned
    return best_cleaned
