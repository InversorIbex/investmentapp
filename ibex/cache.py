"""Caché en memoria y en disco para no martillear las fuentes."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# En Vercel el disco del proyecto es de solo lectura. /tmp dura lo que vive la función.
if os.environ.get("VERCEL"):
    CACHE_DIR = Path(tempfile.gettempdir()) / "ibex-cache"
else:
    CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_mem: dict[str, tuple[float, object]] = {}


def _path(key: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
    return CACHE_DIR / f"{safe}.json"


def remember(key: str, ttl: float, builder, disk: bool = False):
    now = time.time()
    with _lock:
        hit = _mem.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    path = _path(key)
    if disk and path.exists():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            saved = float(blob.get("_saved") or 0)
            if now - saved < ttl:
                payload = blob["payload"]
                with _lock:
                    _mem[key] = (saved, payload)
                return payload
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        payload = builder()
    except Exception as exc:
        fallback = _fallback(key, path, disk, exc)
        if fallback is not None:
            return fallback
        raise
    with _lock:
        _mem[key] = (now, payload)
    if disk and isinstance(payload, (dict, list)):
        try:
            path.write_text(
                json.dumps({"_saved": now, "payload": payload}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
    return payload


def _fallback(key: str, path: Path, disk: bool, exc: Exception):
    with _lock:
        hit = _mem.get(key)
    payload = hit[1] if hit else None
    if payload is None and disk and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
        except (OSError, ValueError, KeyError, TypeError):
            payload = None
    if isinstance(payload, dict):
        stale = dict(payload)
        stale["stale"] = True
        stale["error"] = f"Sin actualización: {exc}"
        return stale
    return None
