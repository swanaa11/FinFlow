"""Hashing utilities for file identity and record fingerprints.

Content hashes (not filenames or timestamps) are the identity of ingested
files — this is what makes re-processing the same statement a no-op.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK_SIZE = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file (constant memory for arbitrarily large files)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    """SHA-256 of an in-memory byte payload."""
    return hashlib.sha256(payload).hexdigest()


def canonical_row_hash(values: dict[str, Any]) -> str:
    """Deterministic hash of a structured record (used for row fingerprints).

    Keys are sorted and separators are fixed so the same logical row always
    produces the same hash across runs and processes.
    """
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_bytes(canonical.encode("utf-8"))
