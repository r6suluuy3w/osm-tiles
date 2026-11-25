"""Shard manifest: per-shard checksums plus per-layer counts.

A refresh is only reviewable if the previous output can be diffed against the
new one. The manifest gives that a fixed shape: every shard with its SHA-256,
grouped counts per layer and zoom, so ``verify`` can point at shards that
changed, disappeared or appeared since the last run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SUFFIX = ".geojson"


def _shards(root: Path) -> list[Path]:
    return sorted(p for p in root.glob(f"*/*/*/*{SUFFIX}") if p.is_file())


def _entry(root: Path, shard: Path) -> dict:
    layer, zoom, x, name = shard.relative_to(root).parts
    return {
        "path": shard.relative_to(root).as_posix(),
        "layer": layer,
        "zoom": int(zoom),
        "x": int(x),
        "y": int(Path(name).stem),
        "sha256": hashlib.sha256(shard.read_bytes()).hexdigest(),
    }


def write(root: str | Path, path: str | Path) -> dict:
    """Checksum the shard tree and emit a manifest document."""

    base = Path(root)
    shards = [_entry(base, shard) for shard in _shards(base)]

    layers: dict[str, dict[int, int]] = {}
    for shard in shards:
        per_zoom = layers.setdefault(shard["layer"], {})
        per_zoom[shard["zoom"]] = per_zoom.get(shard["zoom"], 0) + 1

    document = {
        "shard_count": len(shards),
        "layers": {name: dict(sorted(zooms.items())) for name, zooms in sorted(layers.items())},
        "shards": shards,
    }
    Path(path).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def verify(root: str | Path, path: str | Path) -> dict:
    """Compare a shard tree against a manifest written by ``write``."""

    base = Path(root)
    previous = json.loads(Path(path).read_text(encoding="utf-8"))
    before = {entry["path"]: entry["sha256"] for entry in previous.get("shards", [])}
    now = {entry["path"]: entry for entry in (_entry(base, s) for s in _shards(base))}

    return {
        "changed": sorted(p for p in now.keys() & before.keys() if now[p]["sha256"] != before[p]),
        "added": sorted(now.keys() - before.keys()),
        "removed": sorted(before.keys() - now.keys()),
    }
