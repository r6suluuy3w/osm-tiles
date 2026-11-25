# osm-tiles

Turn a raw OpenStreetMap extract into zoom-indexed GeoJSON tile shards, one
directory per layer, so a downstream tiler (tippecanoe, tilemaker) can pack
PBF without re-doing the selection logic.

Why: the interesting decisions in a tile pipeline are which tags become which
layer and at which zooms. Those decisions belong in a reviewable config file,
not in a shell one-liner that nobody can reproduce six months later.

## Data sources and licence

* Input extracts from <https://download.geofabrik.de/> (`.osm.pbf`, converted
  to `.osm` with `osmium cat --output-format osm`).
* Output data is derived from OpenStreetMap, (c) OpenStreetMap contributors,
  licensed ODbL 1.0. Attribution must survive into the rendered map.
* Pipeline source code: MIT (see `LICENSE`).

Refresh cadence: weekly for the regional extract, and the config is reviewed
before every refresh so that layer changes land as their own commit.

## Install

Python 3.11+, standard library only.

```sh
git clone https://github.com/r6suluuy3w/osm-tiles
cd osm-tiles
python3 -m osm_tiles.pipeline --help
```

## Usage

`config/layers.json` declares layers, their tag selectors and their zoom
range. A selector value of `*` means "key present, any value".

```sh
osmium cat finland-latest.osm.pbf --output-format osm -o finland.osm
python3 -m osm_tiles.pipeline finland.osm \
    --layers config/layers.json \
    --out out/finland --max-zoom 14 --bbox 24.5,60.1,25.2,60.3
tippecanoe -o finland.mbtiles --layer=all out/finland/*/*/*/*.geojson
```

`--manifest PATH` writes per-shard checksums so a refresh can be diffed with
`osm_tiles.manifest.verify` (see `docs/shard-manifest.md`).

`--stats` prints per-layer feature counts and the largest tile fan-out so that
oversized features can be spotted before tiling.

## Layout

```
config/layers.json   layer definitions (tags, zoom range)
osm_tiles/config.py  config loading and tag matching
osm_tiles/geometry.py tile quadtree math
osm_tiles/pipeline.py OSM reader, classifier, tile writer, CLI
```

Ways are emitted as `LineString`, closed ways (>= 4 distinct refs, first ref
repeated) as `Polygon`. Relations are not assembled yet.
