"""Slippy-map quadtree math.

Tiles use the standard web mercator scheme: zoom 0 is the whole world and each
level quadruples the index. Latitude is clamped to the mercator limit, so polar
input still lands on a valid tile instead of raising.
"""

from __future__ import annotations

import math

MAX_ZOOM = 22
LAT_LIMIT = 85.05112878


def clamp_zoom(zoom: int) -> None:
    if not 0 <= zoom <= MAX_ZOOM:
        raise ValueError(f"zoom {zoom} outside 0..{MAX_ZOOM}")


def tile_index(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """Return the (x, y) tile containing a lon/lat point at ``zoom``."""

    clamp_zoom(zoom)
    n = 1 << zoom
    lat = max(-LAT_LIMIT, min(LAT_LIMIT, lat))
    x = math.floor((lon + 180.0) / 360.0 * n)
    y = math.floor((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Return the (west, south, east, north) bounds of a tile."""

    clamp_zoom(zoom)
    n = 1 << zoom
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def bbox_tiles(
    west: float, south: float, east: float, north: float, zoom: int
) -> set[tuple[int, int]]:
    """Tiles intersecting a bbox, inclusive of both corners.

    The antimeridian is not handled: a bbox crossing it must be split by the
    caller before it reaches this function.
    """

    if west > east or south > north:
        raise ValueError(f"bad bbox {west},{south},{east},{north}")
    x0, y0 = tile_index(west, north, zoom)
    x1, y1 = tile_index(east, south, zoom)
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
