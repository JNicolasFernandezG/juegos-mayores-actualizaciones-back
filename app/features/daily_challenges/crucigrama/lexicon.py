"""
lexicon.py
Índice del léxico, normalización, parsing de slots, anclas/vetos y grilla resuelta.
"""

import json
import logging
from pathlib import Path
from typing import AbstractSet, Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DICTIONARY_PATH = DATA_DIR / "acentos_todas_palabras.json"
MIN_WORD_LEN, MAX_WORD_LEN = 3, 11

# Mutar siempre in-place (.clear()/.update()) para conservar la identidad en reexports.
_WORDS_BY_LEN: Dict[int, List[str]] = {}
_WORDS_SET: Set[str] = set()
_LETTER_POS_INDEX: Dict[Tuple[int, int, str], Set[str]] = {}
_IS_INITIALIZED: bool = False
_ACCENT_MAP = str.maketrans("ÁÉÍÓÚÜ", "AEIOUU")


def _normalize_word(word: str) -> str:
    return str(word or "").strip().upper().translate(_ACCENT_MAP)


def normalize_word(word: str) -> str:
    """Normaliza una palabra igual que el índice del léxico (mayúsculas, sin tildes)."""
    return _normalize_word(word)


def normalize_banned(banned_words: Optional[Iterable[str]]) -> Set[str]:
    """Normaliza y filtra palabras vacías de una colección de vetos."""
    return {_normalize_word(w) for w in (banned_words or ()) if _normalize_word(w)}


def is_known_word(word: str) -> bool:
    """Indica si la palabra existe en el léxico indexado del juego."""
    _init_word_index()
    return _normalize_word(word) in _WORDS_SET


def _init_word_index() -> None:
    """Inicializa el índice de palabras en memoria para búsqueda de candidatos O(1)."""
    global _IS_INITIALIZED
    if _IS_INITIALIZED:
        return
    _WORDS_BY_LEN.clear()
    _WORDS_BY_LEN.update({length: [] for length in range(MIN_WORD_LEN, MAX_WORD_LEN + 1)})
    _WORDS_SET.clear()
    _LETTER_POS_INDEX.clear()
    if not DICTIONARY_PATH.exists():
        logger.warning(f"[CRUCIGRAMA] No se encontró el diccionario en {DICTIONARY_PATH}.")
        _IS_INITIALIZED = True
        return
    try:
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            raw_dict = json.load(f)
        for w in raw_dict.keys():
            if MIN_WORD_LEN <= len(w) <= MAX_WORD_LEN and w.isalpha():
                w_upper = w.upper()
                _WORDS_BY_LEN[len(w)].append(w_upper)
                _WORDS_SET.add(w_upper)
                for pos, ch in enumerate(w_upper):
                    _LETTER_POS_INDEX.setdefault((len(w), pos, ch), set()).add(w_upper)
        logger.info(f"[CRUCIGRAMA] Diccionario indexado: {len(_WORDS_SET)} palabras.")
    except Exception as e:
        logger.error(f"[CRUCIGRAMA] Error inicializando índice de palabras: {e}")
    _IS_INITIALIZED = True


def _scan_slots(grid_pattern: List[str], direction: str) -> List[Dict]:
    rows, cols = len(grid_pattern), len(grid_pattern[0]) if grid_pattern else 0
    outer, inner = (rows, cols) if direction == "H" else (cols, rows)
    slots: List[Dict] = []
    for a in range(outer):
        b = 0
        while b < inner:
            r, c = (a, b) if direction == "H" else (b, a)
            if grid_pattern[r][c] == "#":
                b += 1
                continue
            start_b, coords = b, []
            while b < inner:
                rr, cc = (a, b) if direction == "H" else (b, a)
                if grid_pattern[rr][cc] == "#":
                    break
                coords.append((rr, cc))
                b += 1
            if len(coords) > 1:
                sr, sc = (a, start_b) if direction == "H" else (start_b, a)
                slots.append({
                    "id": f"{direction}_{sr}_{sc}", "dir": direction,
                    "r": sr, "c": sc, "len": len(coords), "coords": coords,
                })
    return slots


def _parse_template_slots(
    grid_pattern: List[str],
) -> Tuple[List[Dict], Dict[str, List[Tuple[int, str, int]]]]:
    """Identifica slots H/V en la plantilla y precalcula sus intersecciones."""
    slots = _scan_slots(grid_pattern, "H") + _scan_slots(grid_pattern, "V")
    intersections: Dict[str, List[Tuple[int, str, int]]] = {s["id"]: [] for s in slots}
    for i, s1 in enumerate(slots):
        for j, s2 in enumerate(slots):
            if i != j and s1["dir"] != s2["dir"]:
                for p1, c1 in enumerate(s1["coords"]):
                    for p2, c2 in enumerate(s2["coords"]):
                        if c1 == c2:
                            intersections[s1["id"]].append((p1, s2["id"], p2))
    return slots, intersections


def _validate_anchor_entry(
    raw_id: Any, raw_word: str, slots_by_id: Dict[str, Dict], used_words: AbstractSet[str]
) -> Tuple[str, str]:
    s_id = str(raw_id).strip()
    slot = slots_by_id.get(s_id)
    if slot is None:
        raise ValueError(f"El slot '{s_id}' no existe en la máscara.")
    word = _normalize_word(raw_word)
    if not word:
        raise ValueError(f"El ancla del slot '{s_id}' está vacía.")
    if not word.isalpha():
        raise ValueError(f"El ancla '{word}' del slot '{s_id}' solo puede contener letras.")
    if len(word) != slot["len"]:
        raise ValueError(f"El ancla '{word}' tiene {len(word)} letras y el slot '{s_id}' requiere {slot['len']}.")
    if word not in _WORDS_SET:
        raise ValueError(f"El ancla '{word}' no está en el léxico del juego.")
    if word in used_words:
        raise ValueError(f"La palabra '{word}' está asignada a más de un slot.")
    return s_id, word


def normalize_preassigned(
    preassigned: Dict[str, str],
    slots: List[Dict],
    intersections: Dict[str, List[Tuple[int, str, int]]],
) -> Dict[str, str]:
    """Valida y normaliza palabras ancla (slot_id -> palabra)."""
    if not preassigned:
        return {}
    _init_word_index()
    slots_by_id = {s["id"]: s for s in slots}
    normalized: Dict[str, str] = {}
    for raw_id, raw_word in preassigned.items():
        s_id, word = _validate_anchor_entry(raw_id, raw_word, slots_by_id, normalized.values())
        normalized[s_id] = word

    for s_id, word in normalized.items():
        for my_pos, other_id, other_pos in intersections[s_id]:
            other_word = normalized.get(other_id)
            if other_word is not None and word[my_pos] != other_word[other_pos]:
                r, c = slots_by_id[s_id]["coords"][my_pos]
                raise ValueError(
                    f"Cruce incompatible entre '{word}' y '{other_word}' en la celda ({r}, {c}): "
                    f"'{word[my_pos]}' ≠ '{other_word[other_pos]}'."
                )
    return normalized


def prepare_anchors_and_bans(
    preassigned: Optional[Dict[str, str]], banned_words: Optional[Iterable[str]],
    slots: List[Dict], intersections: Dict[str, List[Tuple[int, str, int]]],
    *, already_normalized: bool = False,
) -> Tuple[Dict[str, str], Set[str]]:
    """Normaliza anclas y vetos y verifica que no exista conflicto entre ambos."""
    anchors = (
        dict(preassigned or {}) if already_normalized
        else normalize_preassigned(preassigned or {}, slots, intersections)
    )
    banned = normalize_banned(banned_words)
    conflicts = sorted(set(anchors.values()) & banned)
    if conflicts:
        raise ValueError(f"La palabra '{conflicts[0]}' está fijada y vetada al mismo tiempo.")
    return anchors, banned


def query_candidates(
    length: int, constraints: Sequence[Tuple[int, str]],
    used: AbstractSet[str], banned: AbstractSet[str],
) -> List[str]:
    """Devuelve palabras candidatas ordenadas que cumplen las letras fijadas."""
    if not constraints:
        return sorted(w for w in _WORDS_BY_LEN.get(length, []) if w not in used and w not in banned)
    cands: Optional[Set[str]] = None
    for pos, ch in constraints:
        bucket = _LETTER_POS_INDEX.get((length, pos, ch))
        if not bucket:
            return []
        cands = bucket if cands is None else cands & bucket
        if not cands:
            return []
    return sorted(w for w in cands if w not in used and w not in banned)


def build_solution_grid(
    pattern: List[str], slots: List[Dict[str, Any]], assignment: Dict[str, str]
) -> Optional[List[str]]:
    """Construye la grilla resuelta a partir del patrón, slots y asignación."""
    rows, cols = len(pattern), len(pattern[0]) if pattern else 0
    grid = [["#" if pattern[r][c] == "#" else "" for c in range(cols)] for r in range(rows)]
    for slot in slots:
        word = assignment.get(slot["id"])
        if word is None:
            return None
        for (r, c), ch in zip(slot["coords"], word):
            grid[r][c] = ch
    if any(grid[r][c] == "" for r in range(rows) for c in range(cols)):
        return None
    return ["".join(row) for row in grid]
