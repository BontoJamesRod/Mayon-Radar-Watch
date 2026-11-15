"""Task T-148: the 3D page's terrain tiles (F-25, FR-102, ADR-015).

Terrain tiles hold the ground's height, not a picture. Each pixel's colour is a height in metres,
written the "Terrarium" way that MapLibre reads:
    height = red * 256 + green + blue / 256 - 32768
Like the relief, they come from the Copernicus DEM GLO-30. No radar product is read here.

Run from the project folder, after relief.py has saved the height files in raw/:
    python pipeline/mrw/terrain.py mayon
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

# Lets this file run as a script from the project folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mrw.config import load_site
from mrw.context import DATA_FOLDER
from mrw.contract_check import relief_tile_range
from mrw.relief import DEM_FOLDER, EARTH_HALF_WIDTH_M, LOG_FOLDER, NO_HEIGHT, TILE_PIXELS, dem_names

# The 3D view looks far across the land when tilted, and far away MapLibre asks for low zooms.
TERRAIN_MIN_ZOOM = 8
# At zoom 12 one pixel is about 37 m at Mayon, close to the DEM's 30 m, so more would only enlarge it.
TERRAIN_MAX_ZOOM = 12
SIZE_LIMIT_BYTES = 300_000_000  # the owner's limit for the stored tiles
TERRARIUM_OFFSET_M = 32768


class TilesTooLarge(Exception):
    """The terrain tiles would go over the owner's size limit."""


def encode_terrarium(height):
    """Turn heights in metres into red, green and blue, the Terrarium way."""
    value = np.clip(height, -TERRARIUM_OFFSET_M, TERRARIUM_OFFSET_M - 1) + TERRARIUM_OFFSET_M
    red = np.floor(value / 256)
    green = np.floor(value - red * 256)
    blue = np.floor((value - np.floor(value)) * 256)
    return np.stack([red, green, blue], axis=-1).astype("uint8")


def decode_terrarium(rgb):
    """The reverse, used by the tests: colours back to metres."""
    rgb = rgb.astype("float64")
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - TERRARIUM_OFFSET_M


def saved_dem_files(bounds):
    """The height files relief.py saved. This script never downloads."""
    paths = [DEM_FOLDER / f"{name}.tif" for name in dem_names(bounds)]
    found = [path for path in paths if path.exists()]  # open sea has no file
    if not found:
        raise FileNotFoundError(f"No height files in {DEM_FOLDER}. Run: python pipeline/mrw/relief.py <site>")
    return found


def render_zoom(sources, bounds, zoom, out_folder):
    """Make every terrain tile of one zoom from one big height grid, like the relief does."""
    x_low, y_low, x_high, y_high = relief_tile_range(bounds, zoom)
    columns, rows = x_high - x_low + 1, y_high - y_low + 1
    tile_m = 2 * EARTH_HALF_WIDTH_M / 2 ** zoom
    left = -EARTH_HALF_WIDTH_M + x_low * tile_m
    top = EARTH_HALF_WIDTH_M - y_low * tile_m
    width, height = columns * TILE_PIXELS, rows * TILE_PIXELS
    transform = from_bounds(left, top - rows * tile_m, left + columns * tile_m, top, width, height)
    ground = np.zeros((height, width), dtype="float32")
    data, data_transform = merge(sources)
    # Zoomed out, each pixel averages the heights under it; zoomed in, it blends the nearest ones.
    reproject(data[0], ground, src_transform=data_transform, src_crs="EPSG:4326", dst_transform=transform,
              dst_crs="EPSG:3857", resampling=Resampling.average if zoom < TERRAIN_MAX_ZOOM else Resampling.bilinear,
              dst_nodata=NO_HEIGHT)
    ground[ground == NO_HEIGHT] = 0  # past the height files, and open sea: flat at sea level
    ground[ground < 0] = 0
    picture = encode_terrarium(ground)
    for column in range(columns):
        folder = out_folder / str(zoom) / str(x_low + column)
        folder.mkdir(parents=True, exist_ok=True)
        for row in range(rows):
            piece = picture[row * TILE_PIXELS:(row + 1) * TILE_PIXELS, column * TILE_PIXELS:(column + 1) * TILE_PIXELS]
            # PNG keeps every colour exactly. A lossy format would change the heights.
            Image.fromarray(piece).save(folder / f"{y_low + row}.png", optimize=True)
    return columns * rows


def check_size(total, limit=SIZE_LIMIT_BYTES):
    if total >= limit:
        raise TilesTooLarge(f"The terrain tiles total {total} bytes, and the limit is under {limit} bytes")
    return total


def main(site_id):
    site = load_site(site_id)
    bounds = tuple(site[f"relief_bounds_{side}"] for side in ("west", "south", "east", "north"))
    out_folder = DATA_FOLDER / "sites" / site_id / "terrain"
    sources = [rasterio.open(path) for path in saved_dem_files(bounds)]
    try:
        for zoom in range(TERRAIN_MIN_ZOOM, TERRAIN_MAX_ZOOM + 1):
            print(f"Zoom {zoom}: {render_zoom(sources, bounds, zoom, out_folder)} tiles")
    finally:
        for source in sources:
            source.close()
    files = list(out_folder.rglob("*.png"))
    total = sum(path.stat().st_size for path in files)
    # The owner's limit is for every site's terrain together.
    all_sites = sum(path.stat().st_size for path in (DATA_FOLDER / "sites").glob("*/terrain/**/*.png"))
    LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (LOG_FOLDER / f"{now}_terrain_tiles_{site_id}.json").write_text(json.dumps(
        {"site_id": site_id, "tiles": len(files), "total_bytes": total, "all_sites_bytes": all_sites,
         "limit_bytes": SIZE_LIMIT_BYTES, "zooms": [TERRAIN_MIN_ZOOM, TERRAIN_MAX_ZOOM], "encoding": "terrarium"},
        indent=1), encoding="utf-8")
    print(f"Terrain: {len(files)} tiles, {total} bytes ({total / 1e6:.1f} MB). "
          f"All sites: {all_sites / 1e6:.1f} MB, limit {SIZE_LIMIT_BYTES / 1e6:.0f} MB")
    check_size(all_sites)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
