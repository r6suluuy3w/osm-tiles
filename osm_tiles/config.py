"""Layer definitions: which OSM tags become which layer, at which zooms.

A selector is a mapping of tag key to required value. The value ``*`` means
the key must be present with any non-empty value. All pairs must match, so a
layer can be as narrow as ``{"highway": "primary", "bridge": "yes"}``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ANY = "*"


class ConfigError(ValueError):
    """Raised for layer configs that cannot produce usable tiles."""


@dataclass(frozen=True)
class Layer:
    name: str
    selectors: tuple[tuple[str, str], ...]
    min_zoom: int
    max_zoom: int

    def matches(self, tags: dict[str, str]) -> bool:
        for key, wanted in self.selectors:
            actual = tags.get(key)
            if actual is None:
                return False
            if wanted != ANY and actual != wanted:
                return False
        return True

    def zooms(self, limit: int) -> range:
        return range(self.min_zoom, min(self.max_zoom, limit) + 1)


def _layer(raw: dict, index: int) -> Layer:
    try:
        name = raw["name"]
        selectors = tuple(sorted(raw["selectors"].items()))
        min_zoom = int(raw.get("min_zoom", 6))
        max_zoom = int(raw.get("max_zoom", 14))
    except (KeyError, AttributeError) as exc:
        raise ConfigError(f"layer #{index}: {exc}") from exc

    if not selectors:
        raise ConfigError(f"layer {name!r}: empty selector set would match every feature")
    if not 0 <= min_zoom <= max_zoom <= 22:
        raise ConfigError(f"layer {name!r}: bad zoom range {min_zoom}..{max_zoom}")
    return Layer(name=name, selectors=selectors, min_zoom=min_zoom, max_zoom=max_zoom)


def load(path: str | Path) -> list[Layer]:
    """Read and validate a layer config file."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    layers = [_layer(entry, i) for i, entry in enumerate(raw.get("layers", []))]
    if not layers:
        raise ConfigError(f"{path}: no layers defined")

    seen: set[str] = set()
    for layer in layers:
        if layer.name in seen:
            raise ConfigError(f"duplicate layer name {layer.name!r}")
        if "/" in layer.name:
            raise ConfigError(f"layer {layer.name!r} must not contain '/'")
        seen.add(layer.name)
    return layers
