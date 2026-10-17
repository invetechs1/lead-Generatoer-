"""Shared helpers for routers: templates, settings lookup, public base URL, client IP, rate limiting, upload checks."""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import settings
from .models import Setting

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

_SAFE_URL = re.compile(r"^(https?://|/|#|tel:\+?\d|mailto:[^\s]+)", re.I)


def safe_href(value) -> str:
    """Template filter: only http(s), site-relative, anchor, tel: and mailto: URLs reach an href/src; anything else becomes '#'."""
    v = str(value or "").strip()
    return v if v and _SAFE_URL.match(v) else "#"


TEMPLATES.env.filters["safe_href"] = safe_href


def setting(db: Session, key: str, default: str = "") -> str:
    s = db.get(Setting, key)
    return s.value if s and s.value else default


def base_url(request: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


def client_ip(request: Request) -> str:
    """Behind nginx the real address is the first X-Forwarded-For entry (nginx overwrites the header)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "?")[:64]


class RateLimiter:
    """Small in-memory sliding-window limiter per (bucket, ip). Good enough for a single api process behind nginx."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, bucket: str, ip: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        key = (bucket, ip)
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 20000:  # keep memory bounded under abuse
                self._hits.clear()
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def rate_limit(bucket: str, limit: int, window: int = 60):
    """FastAPI dependency: `Depends(rate_limit("answers", 10))` → 429 when an IP exceeds `limit` calls per `window` seconds."""
    def dep(request: Request) -> None:
        if not limiter.check(bucket, client_ip(request), limit, window):
            raise HTTPException(429, "Too many requests, try again shortly")
    return dep


# ---- uploads ----
MAGIC = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",), ".pdf": (b"%PDF-",),
}


def upload_ok(ext: str, data: bytes, max_bytes: int) -> bool:
    """Extension allow-list + magic-byte check + size cap. Rejects HTML/SVG/scripts dressed up as images."""
    if ext not in MAGIC or not data or len(data) > max_bytes:
        return False
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(m) for m in MAGIC[ext])


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
KIND_RE = re.compile(r"^[a-z0-9-]{1,40}$")
