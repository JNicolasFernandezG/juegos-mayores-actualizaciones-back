"""Cliente centralizado y reutilizable para la API no oficial de la RAE (rae-api.com)."""

import atexit
import concurrent.futures
import json
import logging
import os
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, Iterable, Optional, Tuple

from app.core.config import settings
from app.core.rae_formatter import (  # noqa: F401
    build_rae_headers, build_rae_url, build_search_candidates,
    clean_and_mask_definition, select_best_definition,
)

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CACHE_PATH = os.path.join(DATA_DIR, "definiciones_cache.json")
ACENTOS_PATH = os.path.join(DATA_DIR, "acentos_todas_palabras.json")

_DEFINICIONES_CACHE: Dict[str, str] = {}
_ACENTOS_MAP: Dict[str, str] = {}
_CACHE_LOCK = threading.RLock()
_NEGATIVE_CACHE: Dict[str, float] = {}
_NEGATIVE_LOCK = threading.Lock()
_CALL_GATE = threading.Lock()
_NEXT_CALL_AT = 0.0
_FLUSH_LOCK = threading.Lock()
_FLUSH_TIMER: Optional[threading.Timer] = None
_DIRTY = False
_LAST_FLUSH = 0.0

def _read_json_dict(path: str, label: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"[RAE] Error al leer {label}: {e}")
        return {}

def _load_definitions_cache() -> Dict[str, str]:
    """Carga la caché local de definiciones desde el archivo JSON en disco."""
    global _DEFINICIONES_CACHE
    if _DEFINICIONES_CACHE:
        return _DEFINICIONES_CACHE
    with _CACHE_LOCK:
        if not _DEFINICIONES_CACHE:
            _DEFINICIONES_CACHE = _read_json_dict(CACHE_PATH, "caché de definiciones")
    return _DEFINICIONES_CACHE

def _write_definitions_cache() -> None:
    """Escritura atómica: el archivo final nunca queda a medio escribir."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _CACHE_LOCK:
            payload = dict(_DEFINICIONES_CACHE)
        tmp_path = f"{CACHE_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CACHE_PATH)
    except Exception as e:
        logger.warning(f"[RAE] Error al persistir caché de definiciones: {e}")

def _flush_locked() -> None:
    global _DIRTY, _LAST_FLUSH
    _DIRTY = False
    _LAST_FLUSH = time.monotonic()
    _write_definitions_cache()

def _flush_definitions_cache() -> None:
    with _FLUSH_LOCK:
        if _DIRTY:
            _flush_locked()

def _save_definitions_cache() -> None:
    """Marca la caché como sucia y la persiste como máximo cada RAE_CACHE_FLUSH_SECONDS."""
    global _DIRTY, _FLUSH_TIMER
    interval = max(0.0, float(settings.RAE_CACHE_FLUSH_SECONDS))
    with _FLUSH_LOCK:
        _DIRTY = True
        if interval == 0:
            _flush_locked()
            return
        if _FLUSH_TIMER is None or not _FLUSH_TIMER.is_alive():
            espera = max(0.0, interval - (time.monotonic() - _LAST_FLUSH))
            _FLUSH_TIMER = threading.Timer(espera, _flush_definitions_cache)
            _FLUSH_TIMER.daemon = True
            _FLUSH_TIMER.start()

atexit.register(_flush_definitions_cache)

def _load_acentos_map() -> Dict[str, str]:
    """Carga el diccionario completo de palabras normalizadas a sus formas oficiales con tilde."""
    global _ACENTOS_MAP
    if not _ACENTOS_MAP:
        _ACENTOS_MAP = _read_json_dict(ACENTOS_PATH, "mapa de acentos")
    return _ACENTOS_MAP

def _is_negative(word: str) -> bool:
    key = word.upper().strip()
    with _NEGATIVE_LOCK:
        expiry = _NEGATIVE_CACHE.get(key)
        if expiry is None or expiry <= time.monotonic():
            _NEGATIVE_CACHE.pop(key, None)
            return False
        return True

def _mark_negative(word: str) -> None:
    ttl = max(0.0, float(settings.RAE_NEGATIVE_CACHE_TTL_SECONDS))
    if ttl > 0:
        with _NEGATIVE_LOCK:
            _NEGATIVE_CACHE[word.upper().strip()] = time.monotonic() + ttl

def _wait_for_call_slot() -> None:
    """Espacia las llamadas HTTP a nivel global, aunque haya varios hilos consultando."""
    global _NEXT_CALL_AT
    interval = max(0.0, float(settings.RAE_MIN_INTERVAL_MS) / 1000.0)
    if interval == 0:
        return
    with _CALL_GATE:
        now = time.monotonic()
        wait = max(0.0, _NEXT_CALL_AT - now)
        _NEXT_CALL_AT = max(now, _NEXT_CALL_AT) + interval
    if wait > 0:
        time.sleep(wait)

def _backoff_delay(attempt: int) -> float:
    base = max(0.0, float(settings.RAE_RETRY_BASE_SECONDS))
    delay = base * (2 ** attempt) + random.uniform(0.0, 0.3)
    max_backoff = max(0.0, float(settings.RAE_MAX_BACKOFF_SECONDS))
    return max(0.0, min(delay, max_backoff))

def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    raw = error.headers.get("Retry-After") if error.headers else None
    try:
        if raw is not None:
            return max(0.0, min(float(raw), max(0.0, float(settings.RAE_MAX_BACKOFF_SECONDS))))
    except (TypeError, ValueError):
        pass
    return _backoff_delay(attempt)

def _classify_request_error(exc: Exception, term: str, attempt: int, max_retries: int) -> Tuple[str, float]:
    """Decide si reintentar, probar el siguiente candidato o abortar por 429 agotado."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429 and attempt >= max_retries:
            return ("abort", 0.0)
        if exc.code in (429, 500, 502, 503, 504) and attempt < max_retries:
            delay = _retry_delay(exc, attempt)
            msg = (
                f"[RAE] Límite de tasa (429) para '{term}'. Reintentando en {delay:.2f}s ({attempt + 1}/{max_retries})."
                if exc.code == 429
                else f"[RAE] Error {exc.code} para '{term}'. Reintentando en {delay:.2f}s."
            )
            logger.warning(msg)
            return ("retry", delay)
        return ("next", 0.0)
    if isinstance(exc, (urllib.error.URLError, TimeoutError)) and attempt < max_retries:
        delay = _backoff_delay(attempt)
        logger.warning(f"[RAE] Error de red para '{term}'. Reintentando en {delay:.2f}s.")
        return ("retry", delay)
    if not isinstance(exc, (urllib.error.URLError, TimeoutError)):
        logger.debug(f"[RAE] Error consultando candidato '{term}': {exc}")
    return ("next", 0.0)

def _fetch_candidate(
    term: str, headers: Dict[str, str], word_upper: str, mask_spoiler: bool, max_retries: int
) -> Tuple[str, Optional[str]]:
    req = urllib.request.Request(build_rae_url(term), headers=headers)
    for attempt in range(max_retries + 1):
        _wait_for_call_slot()
        try:
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            best = select_best_definition(data, word_upper, mask_spoiler=mask_spoiler)
            return ("hit", best) if best else ("next", None)
        except Exception as exc:
            action, delay = _classify_request_error(exc, term, attempt, max_retries)
            if action != "retry":
                return (action, None)
            time.sleep(delay)
    return ("next", None)

def fetch_rae_definition(word: str, mask_spoiler: bool = True) -> Optional[str]:
    """Consulta la definición de una palabra en la RAE usando caché local, negativa y reintentos."""
    cache = _load_definitions_cache()
    word_upper = word.upper().strip()
    if mask_spoiler and word_upper in cache:
        return cache[word_upper]
    if _is_negative(word_upper):
        return None
    candidates = build_search_candidates(word_upper, _load_acentos_map())
    headers = build_rae_headers((settings.RAE_API_KEY or os.environ.get("RAE_API_KEY", "")).strip())
    max_retries = max(0, int(settings.RAE_MAX_RETRIES))
    for term in candidates:
        outcome, definition = _fetch_candidate(term, headers, word_upper, mask_spoiler, max_retries)
        if outcome == "hit" and definition:
            if mask_spoiler:
                with _CACHE_LOCK:
                    cache[word_upper] = definition
                _save_definitions_cache()
            return definition
        if outcome == "abort":
            _mark_negative(word_upper)
            return None
    _mark_negative(word_upper)
    return None

def get_masked_definition(word: str) -> Optional[str]:
    """Obtiene la definición de la RAE con la palabra tapada mediante '___'."""
    return fetch_rae_definition(word, mask_spoiler=True)


def fetch_rae_definitions_batch(
    words: Iterable[str], *, mask_spoiler: bool = True
) -> Dict[str, Optional[str]]:
    """Consulta definiciones RAE en paralelo acotadas por RAE_MAX_CONCURRENCY."""
    unique = list(dict.fromkeys(w for w in words if w))
    if not unique:
        return {}
    workers = max(1, min(int(settings.RAE_MAX_CONCURRENCY), len(unique)))
    fn = fetch_rae_definition if mask_spoiler else (lambda w: fetch_rae_definition(w, mask_spoiler=False))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return dict(zip(unique, executor.map(fn, unique)))
