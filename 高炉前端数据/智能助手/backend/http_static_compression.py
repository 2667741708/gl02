"""HTTP compression helpers for the 8093 static dashboard.

REQ-8093-FRONTEND-PERF-R1 keeps the source bytes authoritative and applies
content negotiation only to the response representation. Brotli is optional
at import time so a missing wheel cannot prevent the proxy from starting;
gzip remains the mandatory fallback.
"""

from __future__ import annotations

import gzip
import os
from collections.abc import Mapping

try:
    import brotli
except ImportError:  # pragma: no cover - exercised on minimal production hosts
    brotli = None


MIN_BYTES = max(0, int(os.environ.get("BF_HTTP_COMPRESSION_MIN_BYTES", "1024")))
COMPRESSIBLE_PREFIXES = ("text/",)
COMPRESSIBLE_TYPES = {
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "image/svg+xml",
}


def accepted_encodings(header: str) -> Mapping[str, float]:
    """Parse Accept-Encoding into normalized positive quality values."""

    result: dict[str, float] = {}
    for item in str(header or "").split(","):
        parts = [part.strip() for part in item.split(";") if part.strip()]
        if not parts:
            continue
        encoding = parts[0].lower()
        quality = 1.0
        for parameter in parts[1:]:
            if not parameter.lower().startswith("q="):
                continue
            try:
                quality = min(1.0, max(0.0, float(parameter[2:])))
            except ValueError:
                quality = 0.0
        result[encoding] = quality
    return result


def is_compressible(content_type: str) -> bool:
    """Return whether the media type benefits from HTTP compression."""

    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    return media_type.startswith(COMPRESSIBLE_PREFIXES) or media_type in COMPRESSIBLE_TYPES


def compress_static_payload(
    data: bytes,
    content_type: str,
    accept_encoding: str,
) -> tuple[bytes, str | None]:
    """Return the negotiated representation and its Content-Encoding value."""

    if len(data) < MIN_BYTES or not is_compressible(content_type):
        return data, None
    accepted = accepted_encodings(accept_encoding)
    wildcard = accepted.get("*", 0.0)
    br_quality = accepted.get("br", wildcard)
    gzip_quality = accepted.get("gzip", wildcard)
    candidates = [("br", br_quality), ("gzip", gzip_quality)]
    candidates.sort(key=lambda item: (item[1], item[0] == "br"), reverse=True)
    for encoding, quality in candidates:
        if quality <= 0:
            continue
        if encoding == "br" and brotli is not None:
            return brotli.compress(data, quality=5), "br"
        if encoding == "gzip":
            return gzip.compress(data, compresslevel=6, mtime=0), "gzip"
    return data, None


def brotli_available() -> bool:
    """Expose runtime capability for health checks and tests."""

    return brotli is not None

