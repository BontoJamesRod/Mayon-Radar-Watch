"""T-148: the 3D page's terrain tiles (F-25, FR-102, ADR-015)."""
import json

import numpy as np
import pytest
from PIL import Image

from mrw.contract_check import relief_tile_range
from mrw.context import DATA_FOLDER
from mrw.terrain import (SIZE_LIMIT_BYTES, TERRAIN_MAX_ZOOM, TERRAIN_MIN_ZOOM, TilesTooLarge, check_size,
                         decode_terrarium, encode_terrarium)

SITES = {site["id"]: site for site in json.loads((DATA_FOLDER / "sites.json").read_text(encoding="utf-8"))["data"]}
TERRAIN = DATA_FOLDER / "sites" / "mayon" / "terrain"
MAYON = SITES["mayon"]


def relief_bounds(site):
    return tuple(site[f"relief_bounds_{side}"] for side in ("west", "south", "east", "north"))


def test_heights_survive_the_terrarium_colours():
    heights = np.array([[0.0, 1.5, 2462.25], [-3.0, 100.0, 8848.0]])
    assert np.allclose(decode_terrarium(encode_terrarium(heights)), heights, atol=1 / 256)


def test_the_size_limit_stops_tiles_that_are_too_large():
    assert check_size(SIZE_LIMIT_BYTES - 1) == SIZE_LIMIT_BYTES - 1
    with pytest.raises(TilesTooLarge):
        check_size(SIZE_LIMIT_BYTES)


@pytest.mark.parametrize("site_id", ["mayon", "panama"])
def test_every_terrain_tile_is_there(site_id):
    folder = DATA_FOLDER / "sites" / site_id / "terrain"
    for zoom in range(TERRAIN_MIN_ZOOM, TERRAIN_MAX_ZOOM + 1):
        x_low, y_low, x_high, y_high = relief_tile_range(relief_bounds(SITES[site_id]), zoom)
        for x in range(x_low, x_high + 1):
            for y in range(y_low, y_high + 1):
                assert (folder / str(zoom) / str(x) / f"{y}.png").exists()


def test_all_the_terrain_tiles_together_are_under_the_limit():
    total = sum(path.stat().st_size for path in (DATA_FOLDER / "sites").glob("*/terrain/**/*.png"))
    assert 0 < total < SIZE_LIMIT_BYTES


def test_the_summit_is_about_as_high_as_mayon():
    """Mayon is 2,463 m high. The tile holding the summit must reach close to that, and the sea stays at 0."""
    x, y = relief_tile_range((MAYON["summit_lon"], MAYON["summit_lat"], MAYON["summit_lon"], MAYON["summit_lat"]), TERRAIN_MAX_ZOOM)[:2]
    heights = decode_terrarium(np.asarray(Image.open(TERRAIN / str(TERRAIN_MAX_ZOOM) / str(x) / f"{y}.png").convert("RGB")))
    assert 2300 < heights.max() < 2600
    assert heights.min() >= 0
