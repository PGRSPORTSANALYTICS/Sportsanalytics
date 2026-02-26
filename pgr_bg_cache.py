"""
Module-level persistent cache for dashboard DB queries.
Survives across exec() calls and Streamlit re-renders within the same process.
"""
import time
import threading
import logging

logger = logging.getLogger("pgr_bg_cache")

_store = {}
_lock = threading.RLock()


def get(key: str):
    with _lock:
        if key in _store:
            val, expires = _store[key]
            if time.time() < expires:
                return val, True
    return None, False


def set_cache(key: str, value, ttl: int = 300) -> None:
    with _lock:
        _store[key] = (value, time.time() + ttl)


def cached(key: str, loader_fn, ttl: int = 300):
    val, hit = get(key)
    if hit:
        return val
    try:
        result = loader_fn()
        set_cache(key, result, ttl=ttl)
        return result
    except Exception as e:
        logger.error(f"Cache loader error for {key}: {e}")
        with _lock:
            if key in _store:
                return _store[key][0]
        return None
