# Shard manifest

`--manifest PATH` writes a JSON document describing every shard the run
produced: one entry per `layer/zoom/x/y.geojson` with its SHA-256, plus shard
counts per layer and zoom.

Shape:

```json
{
  "shard_count": 18,
  "layers": {"roads": {"6": 2, "14": 4}},
  "shards": [
    {"path": "roads/14/9315/4741.geojson", "layer": "roads", "zoom": 14,
     "x": 9315, "y": 4741, "sha256": "..."}
  ]
}
```

`osm_tiles.manifest.verify(out_dir, manifest)` returns `changed`, `added` and
`removed` path lists, which is what a refresh job inspects before uploading.
It hashes and compares only; it does not delete anything.

Commit the manifest next to the tiled output, not next to the config: it
describes bytes, so a config-only change with an identical shard tree shows an
empty diff.
