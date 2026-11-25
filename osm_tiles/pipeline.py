"""Pipeline stages: read an OSM extract, classify features, emit tile shards.

The reader is a single streaming pass that keeps node coordinates in memory
while buffering way references, which is fine for regional extracts. Relations
are counted but not assembled yet.

Run it as ``python3 -m osm_tiles.pipeline``.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import config, geometry, manifest


@dataclass
class Feature:
    osm_type: str
    osm_id: int
    tags: dict[str, str]
    coords: list[tuple[float, float]] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return len(self.coords) >= 4 and self.coords[0] == self.coords[-1]

    @property
    def geometry_type(self) -> str:
        return "Polygon" if self.closed else "LineString"


@dataclass
class Extract:
    features: list[Feature]
    skipped_relations: int
    missing_nodes: int


def _tags(element: ET.Element) -> dict[str, str]:
    return {
        tag.get("k", ""): tag.get("v", "")
        for tag in element.findall("tag")
        if tag.get("k")
    }


def read_extract(path: str | Path) -> Extract:
    """Parse nodes and ways, dropping references to nodes outside the extract."""

    nodes: dict[int, tuple[float, float]] = {}
    ways: list[tuple[int, list[int], dict[str, str]]] = []
    relations = 0

    for _event, element in ET.iterparse(path, events=("end",)):
        if element.tag == "node":
            nodes[int(element.get("id"))] = (
                float(element.get("lon")),
                float(element.get("lat")),
            )
            element.clear()
        elif element.tag == "way":
            refs = [int(nd.get("ref")) for nd in element.findall("nd")]
            ways.append((int(element.get("id")), refs, _tags(element)))
            element.clear()
        elif element.tag == "relation":
            relations += 1
            element.clear()

    features: list[Feature] = []
    missing = 0
    for osm_id, refs, tags in ways:
        if not tags:
            continue
        coords = [nodes[ref] for ref in refs if ref in nodes]
        if len(coords) < len(refs):
            missing += len(refs) - len(coords)
        if len(coords) >= 2:
            features.append(Feature("way", osm_id, tags, coords))
    return Extract(features=features, skipped_relations=relations, missing_nodes=missing)


def classify(features: list[Feature], layers: list[config.Layer]) -> dict[str, list[Feature]]:
    """Bucket features into layers; first matching layer wins."""

    buckets: dict[str, list[Feature]] = {layer.name: [] for layer in layers}
    for feature in features:
        for layer in layers:
            if layer.matches(feature.tags):
                buckets[layer.name].append(feature)
                break
    return buckets


def _tile_ids(feature: Feature, zoom: int) -> set[tuple[int, int]]:
    lons = [lon for lon, _ in feature.coords]
    lats = [lat for _, lat in feature.coords]
    return geometry.bbox_tiles(min(lons), min(lats), max(lons), max(lats), zoom)


def plan_tiles(
    buckets: dict[str, list[Feature]],
    layers: list[config.Layer],
    max_zoom: int,
) -> tuple[dict[tuple[str, int, int, int], list[Feature]], int]:
    """Fan each layer's features out over its zoom range.

    Returns the tile map keyed by (layer, zoom, x, y) plus the largest per
    feature tile count, which is the tiling budget signal.
    """

    plan: dict[tuple[str, int, int, int], list[Feature]] = {}
    worst = 0
    for layer in layers:
        for feature in buckets[layer.name]:
            for zoom in layer.zooms(max_zoom):
                ids = _tile_ids(feature, zoom)
                worst = max(worst, len(ids))
                for x, y in ids:
                    plan.setdefault((layer.name, zoom, x, y), []).append(feature)
    return plan, worst


def write_tiles(
    plan: dict[tuple[str, int, int, int], list[Feature]],
    out_dir: str | Path,
    layers: list[config.Layer],
) -> int:
    """Write one GeoJSON FeatureCollection per (layer, zoom, x, y) tile."""

    root = Path(out_dir)
    wanted = {layer.name: layer for layer in layers}
    for (layer_name, zoom, x, y), features in plan.items():
        layer = wanted[layer_name]
        shard = {
            "type": "FeatureCollection",
            "properties": {"layer": layer_name, "zoom": zoom, "x": x, "y": y},
            "features": [
                {
                    "type": "Feature",
                    "id": f"{f.osm_type}/{f.osm_id}",
                    "properties": {
                        **f.tags,
                        "layer": layer_name,
                        "min_zoom": layer.min_zoom,
                    },
                    "geometry": {
                        "type": f.geometry_type,
                        "coordinates": [list(pair) for pair in f.coords],
                    },
                }
                for f in features
            ],
        }
        path = root / layer_name / str(zoom) / str(x) / f"{y}.geojson"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(shard, separators=(",", ":")), encoding="utf-8")
    return len(plan)


def _bbox(text: str | None) -> tuple[float, float, float, float] | None:
    if not text:
        return None
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox wants west,south,east,north")
    return parts[0], parts[1], parts[2], parts[3]


def _inside(feature: Feature, box: tuple[float, float, float, float]) -> bool:
    west, south, east, north = box
    return any(west <= lon <= east and south <= lat <= north for lon, lat in feature.coords)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osm_tiles.pipeline")
    parser.add_argument("extract", help="OSM XML file (.osm)")
    parser.add_argument("--layers", required=True, help="layer config JSON")
    parser.add_argument("--out", required=True, help="output directory for tile shards")
    parser.add_argument("--max-zoom", type=int, default=14)
    parser.add_argument("--bbox", help="west,south,east,north clip before tiling")
    parser.add_argument("--manifest", help="write a checksum manifest of the shard tree")
    parser.add_argument("--stats", action="store_true", help="print per-layer counts")
    args = parser.parse_args(argv)

    layers = config.load(args.layers)
    box = _bbox(args.bbox)
    extract = read_extract(args.extract)
    features = [f for f in extract.features if box is None or _inside(f, box)]
    buckets = classify(features, layers)
    plan, worst = plan_tiles(buckets, layers, args.max_zoom)
    written = write_tiles(plan, args.out, layers)
    if args.manifest:
        manifest.write(args.out, args.manifest)

    if args.stats:
        for name, items in buckets.items():
            print(f"{name}: {len(items)}", file=sys.stderr)
        print(
            f"relations skipped: {extract.skipped_relations}, "
            f"missing node refs: {extract.missing_nodes}",
            file=sys.stderr,
        )
        print(f"worst feature fan-out: {worst} tiles", file=sys.stderr)
        print(f"layers hit: {sum(1 for v in buckets.values() if v)}", file=sys.stderr)

    print(f"wrote {written} tile shards to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
