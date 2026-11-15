"""Town reports: one printable summary per city or municipality near Mayon.

What this does, in plain words:
- For every town in the site's towns.geojson, it measures how far the town is from the summit,
  how much of it lies in the Permanent Danger Zone and inside the area the radar check covers,
  and which checked channels pass through or near it.
- For every published pair, it counts the flagged cells of the new-material grid that fall
  inside the town. A cell is about 20 m across, so these areas are approximate.
- For every published pair that isn't approved yet, it writes a draft data sheet (one row per town)
  and each town's map into pipeline/out/town_sheets/<site>/<pair>/. That folder isn't public.
- The owner reviews a draft and approves it by name, which copies it into site/report/data/<site>/passes/.
- It writes everything the report page (site/report.html) needs into site/report/data/<site>/, from the
  approved sheets only, plus a data bundle (GeoJSON and CSV) per town. That folder sits outside site/data
  on purpose, so the data contract check doesn't cover it yet (ADR-016, ADR-017).

It reads only files that are already published in site/data. It never opens NISAR products.

Run:  python pipeline/mrw/town_reports.py mayon
      python pipeline/mrw/town_reports.py mayon --approve <pair id> --by "Your name"
"""

import csv
import io
import json
import math
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch, PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from PIL import Image  # noqa: E402
from shapely import contains_xy  # noqa: E402
from shapely.geometry import Point, box, mapping, shape  # noqa: E402
import warnings  # noqa: E402

from shapely.ops import transform  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
REPORT_VERSION = "0.1.0"

# One basketball court is 28 m x 15 m, the same comparison the app uses.
COURT_KM2 = 0.028 * 0.015
KM_PER_DEG_LAT = 110.574


def km_per_deg_lon(lat):
    return 111.320 * math.cos(math.radians(lat))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_km(summit_lat, summit_lon):
    """A flat map in kilometres centred on the summit. Fine for distances under about 50 km."""
    kx = km_per_deg_lon(summit_lat)

    def f(x, y, z=None):
        return ((np.asarray(x) - summit_lon) * kx, (np.asarray(y) - summit_lat) * KM_PER_DEG_LAT)

    return f


def round2(x):
    return round(float(x), 2)


def round3(x):
    return round(float(x), 3)


# ---------- reading the site's published files ----------

def load_site(site_id):
    sites = read_json(SITE / "data" / "sites.json")["data"]
    site = next(s for s in sites if s["id"] == site_id)
    folder = SITE / "data" / "sites" / site_id
    towns = read_json(folder / "towns.geojson")["features"]
    channels = read_json(folder / "channels.geojson")["features"]
    pairs = [p for p in read_json(folder / "pairs.json")["data"] if p["status"] == "published"]
    pairs.sort(key=lambda p: (p["after_acquired_start"], p["track"]))
    channel_areas = read_json(folder / "channel_areas.json")["data"]
    events = read_json(folder / "events.json")["data"]
    return site, folder, towns, channels, pairs, channel_areas, events


def load_grid(folder, pair_id):
    """The new-material class grid: 0 no change, 1 possible, 2 likely, 253-255 no data."""
    record = read_json(folder / "pairs" / pair_id / "pair.json")["data"]
    layer = next(l for l in record["layers"] if l["kind"] == "new_material")
    grid = np.fromfile(folder / "pairs" / pair_id / layer["grid_path"], dtype=np.uint8)
    grid = grid.reshape(layer["grid_height"], layer["grid_width"])
    return grid, layer, record


def cell_centres(layer):
    w, h = layer["grid_width"], layer["grid_height"]
    dx = (layer["bounds_east"] - layer["bounds_west"]) / w
    dy = (layer["bounds_north"] - layer["bounds_south"]) / h
    lons = layer["bounds_west"] + (np.arange(w) + 0.5) * dx
    lats = layer["bounds_north"] - (np.arange(h) + 0.5) * dy  # row 0 is the northern edge
    return np.meshgrid(lons, lats), dx, dy


# ---------- relief background from the site's own tiles ----------

def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile_to_lonlat(x, y, z):
    n = 2 ** z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def relief_image(folder, west, south, east, north, z):
    """Stitch the site's relief tiles that cover the box. Returns (image, extent) or None."""
    x0, y0 = lonlat_to_tile(west, north, z)
    x1, y1 = lonlat_to_tile(east, south, z)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (246, 244, 239))
    found = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            tile = folder / "relief" / str(z) / str(tx) / f"{ty}.webp"
            if tile.exists():
                canvas.paste(Image.open(tile).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
                found += 1
    if not found:
        return None
    w_lon, n_lat = tile_to_lonlat(tx0, ty0, z)
    e_lon, s_lat = tile_to_lonlat(tx1 + 1, ty1 + 1, z)
    # Grayscale, so the report stays black and white apart from the flagged marks.
    return np.asarray(canvas.convert("L").convert("RGB")), (w_lon, e_lon, s_lat, n_lat)


# ---------- the numbers for one town ----------

def town_numbers(site, town, channels, km):
    geom = shape(town["geometry"])
    geom_km = transform(km, geom)
    summit = Point(0, 0)
    pdz = summit.buffer(site["danger_zone_radius_km"], 256)
    reach = summit.buffer(site["detection_reach_km"], 256)
    label_km = transform(km, Point(town["properties"]["label_lon"], town["properties"]["label_lat"]))

    # A channel counts for this town when at least 300 m of its checked line runs inside the town,
    # or when the channel record lists the town. Towns meet at the summit, so distance alone isn't enough.
    near_channels = []
    for ch in channels:
        p = ch["properties"]
        line_km = transform(km, shape(p["checked_geometry"]))
        inside_km = line_km.intersection(geom_km).length
        listed = town["properties"]["id"] in p.get("town_ids", [])
        if inside_km >= 0.3 or listed:
            near_channels.append({
                "id": p["id"],
                "name": p["name"],
                "km_inside_town": round2(inside_km),
                "listed_for_town": listed,
                "name_source": p["name_source"],
                "name_source_url": p["name_source_url"],
                "confirmed_on": p["confirmed_on"],
            })

    return {
        "area_km2": round2(geom_km.area),
        "nearest_km_to_summit": round2(geom_km.distance(summit)),
        "centre_km_to_summit": round2(label_km.distance(summit)),
        "pdz_km2": round2(geom_km.intersection(pdz).area),
        "pdz_share": round3(geom_km.intersection(pdz).area / geom_km.area),
        "checked_km2": round2(geom_km.intersection(reach).area),
        "checked_share": round3(geom_km.intersection(reach).area / geom_km.area),
        "channels": near_channels,
    }


def flagged_in_town(grid, inside, lat_mid, dx, dy):
    cell_km2 = dx * km_per_deg_lon(lat_mid) * dy * KM_PER_DEG_LAT
    possible = int(np.count_nonzero(inside & (grid == 1)))
    likely = int(np.count_nonzero(inside & (grid == 2)))
    nodata = int(np.count_nonzero(inside & (grid >= 253) & (grid != 254)))
    return possible * cell_km2, likely * cell_km2, nodata * cell_km2


# ---------- maps ----------

def draw_town_map(path, site, folder, town, towns, channels, grid, layer, pair):
    geom = shape(town["geometry"])
    w, s, e, n = geom.bounds
    # Keep the summit in view so the reader always sees which way the volcano is.
    w, e = min(w, site["summit_lon"]), max(e, site["summit_lon"])
    s, n = min(s, site["summit_lat"]), max(n, site["summit_lat"])
    pad_x, pad_y = (e - w) * 0.08 + 0.01, (n - s) * 0.08 + 0.01
    w, e, s, n = w - pad_x, e + pad_x, s - pad_y, n + pad_y
    lat_mid = (s + n) / 2
    aspect = 1 / math.cos(math.radians(lat_mid))

    fig, ax = plt.subplots(figsize=(7.2, 7.2 * (n - s) * aspect / (e - w)), dpi=170)
    span_km = (e - w) * km_per_deg_lon(lat_mid)
    z = 13 if span_km < 22 else 12
    relief = relief_image(folder, w, s, e, n, z)
    if relief is not None:
        ax.imshow(relief[0], extent=relief[1], zorder=0, interpolation="bilinear")

    # Dim everything outside this town so the town stands out.
    outside = box(w - 1, s - 1, e + 1, n + 1).difference(geom)
    for poly in getattr(outside, "geoms", [outside]):
        # A polygon with holes needs one compound path, so the holes stay clear.
        rings = [np.asarray(poly.exterior.coords)] + [np.asarray(h.coords) for h in poly.interiors]
        ring_path = MplPath.make_compound_path(*[MplPath(r, closed=True) for r in rings])
        ax.add_patch(PathPatch(ring_path, facecolor="white", alpha=0.45, lw=0, zorder=1))

    for other in towns:
        g = shape(other["geometry"])
        for poly in getattr(g, "geoms", [g]):
            xs, ys = poly.exterior.xy
            ax.plot(xs, ys, color="#8a8a8a", lw=0.5, zorder=2)
        lx, ly = other["properties"]["label_lon"], other["properties"]["label_lat"]
        if w < lx < e and s < ly < n and other is not town:
            ax.text(lx, ly, other["properties"]["name"], fontsize=5.5, color="#6b6b6b", ha="center", zorder=6, clip_on=True)
    for poly in getattr(geom, "geoms", [geom]):
        xs, ys = poly.exterior.xy
        ax.plot(xs, ys, color="black", lw=1.8, zorder=5)

    # Danger zone and the edge of the area the radar check covers.
    for radius, style, colour in ((site["danger_zone_radius_km"], "-", "black"),
                                  (site["detection_reach_km"], "--", "#444444")):
        t = np.linspace(0, 2 * math.pi, 361)
        ax.plot(site["summit_lon"] + radius * np.cos(t) / km_per_deg_lon(site["summit_lat"]),
                site["summit_lat"] + radius * np.sin(t) / KM_PER_DEG_LAT,
                ls=style, color=colour, lw=0.9, zorder=4)

    for ch in channels:
        p = ch["properties"]
        line = shape(p["checked_geometry"])
        ax.plot(*line.xy, color="#3a3a3a", lw=1.3, zorder=5)
        if p.get("not_checked_geometry"):
            ax.plot(*shape(p["not_checked_geometry"]).xy, color="#3a3a3a", lw=1.0, ls=":", zorder=5)
        ax.text(p["label_lon"], p["label_lat"], p["name"], fontsize=5.5, color="#3a3a3a", style="italic", zorder=6,
                clip_on=True)

    # Flagged cells. Each mark is drawn a little larger than the 20 m cell, so it stays visible.
    (lons, lats), dx, dy = cell_centres(layer)
    # Orange is the only colour on the map. "Likely" also gets a black edge, so it still reads in grayscale.
    for value, colour, size, edge in ((1, "#E69F00", 1.6, 0), (2, "#D55E00", 3.0, 0.4)):
        mask = grid == value
        if mask.any():
            ax.scatter(lons[mask], lats[mask], s=size, c=colour, marker="s", linewidths=edge, edgecolors="black",
                       zorder=7)

    ax.plot(site["summit_lon"], site["summit_lat"], marker="^", color="black", ms=6, zorder=8)
    ax.text(site["summit_lon"], site["summit_lat"] + 0.004, "Mayon summit", fontsize=6, ha="center", zorder=8, clip_on=True)
    ax.text(town["properties"]["label_lon"], town["properties"]["label_lat"], town["properties"]["name"],
            fontsize=9, fontweight="bold", color="black", ha="center", zorder=8,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.2))

    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(aspect)
    ax.tick_params(labelsize=5.5, length=2)
    ax.set_xticks(np.round(np.linspace(w, e, 5)[1:-1], 3))
    ax.set_yticks(np.round(np.linspace(s, n, 5)[1:-1], 3))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.2f}°E"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.2f}°N"))
    ax.grid(color="white", lw=0.3, alpha=0.6)

    # Scale bar and north arrow.
    bar_km = 2 if span_km < 15 else 5
    bx, by = w + (e - w) * 0.04, s + (n - s) * 0.04
    bar_deg = bar_km / km_per_deg_lon(lat_mid)
    ax.plot([bx, bx + bar_deg], [by, by], color="black", lw=2.2, zorder=9, solid_capstyle="butt")
    ax.text(bx + bar_deg / 2, by + (n - s) * 0.015, f"{bar_km} km", fontsize=6, ha="center", zorder=9)
    ax.annotate("N", xy=(e - (e - w) * 0.05, n - (n - s) * 0.05), xytext=(e - (e - w) * 0.05, n - (n - s) * 0.13),
                arrowprops=dict(arrowstyle="-|>", color="black", lw=1), ha="center", fontsize=8, fontweight="bold",
                zorder=9)

    handles = [
        Patch(facecolor="#E69F00", edgecolor="none", label="Possible new material (brightness only)"),
        Patch(facecolor="#D55E00", edgecolor="black", lw=0.6, label="Likely new material (brightness and coherence agree)"),
        Line2D([], [], color="#3a3a3a", lw=1.3, label="Channel, checked by eye (dotted: not checked)"),
        Line2D([], [], color="black", lw=0.9, label=f"Permanent Danger Zone ({site['danger_zone_radius_km']} km)"),
        Line2D([], [], color="#444444", lw=0.9, ls="--", label=f"Edge of radar check ({site['detection_reach_km']} km)"),
        Line2D([], [], color="black", lw=1.8, label="Town border"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=5.2, framealpha=0.9, borderpad=0.6)
    fig.tight_layout(pad=0.3)
    fig.savefig(path, dpi=170, pil_kwargs={"quality": 82})
    plt.close(fig)


def draw_locator(path, site, towns, town):
    lat_mid = site["summit_lat"]
    fig, ax = plt.subplots(figsize=(2.6, 2.6), dpi=200)
    for other in towns:
        g = shape(other["geometry"])
        mine = other is town
        for poly in getattr(g, "geoms", [g]):
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, color="#222222" if mine else "#e8e8e8", ec="#8a8a8a", lw=0.4)
    t = np.linspace(0, 2 * math.pi, 181)
    ax.plot(site["summit_lon"] + site["danger_zone_radius_km"] * np.cos(t) / km_per_deg_lon(lat_mid),
            site["summit_lat"] + site["danger_zone_radius_km"] * np.sin(t) / KM_PER_DEG_LAT, color="black", lw=0.8)
    ax.plot(site["summit_lon"], site["summit_lat"], marker="^", color="black", ms=4)
    ax.set_aspect(1 / math.cos(math.radians(lat_mid)))
    ax.axis("off")
    fig.tight_layout(pad=0.1)
    fig.savefig(path, dpi=200)
    plt.close(fig)


# ---------- the main run: drafts, approval, then the public files ----------
#
# T-159 (FR-116, FR-117, FR-120). Every pass goes through three steps:
#   1. draft:   its numbers and maps are written to pipeline/out/town_sheets/<site>/<pair>/, which isn't public;
#   2. approve: the owner checks the draft and approves it by name, which copies it into
#               site/report/data/<site>/passes/<pair>/ with the name and the time;
#   3. build:   the public report files are made from the approved sheets only.

DRAFTS = REPO / "pipeline" / "out" / "town_sheets"
PUBLIC = SITE / "report" / "data"
# A fixed date inside the data ZIPs, so a rebuild makes the same bytes (FR-120).
ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def pair_label(p):
    b = datetime.fromisoformat(p["before_acquired_start"].replace("Z", "+00:00"))
    a = datetime.fromisoformat(p["after_acquired_start"].replace("Z", "+00:00"))
    # b.day, not %-d: Windows doesn't know %-d, and this gives the day without a leading zero everywhere.
    return f"{b:%b} {b.day} – {a:%b} {a.day}, {a.year}"


def pair_days(p):
    return (datetime.fromisoformat(p["after_acquired_start"][:10]) - datetime.fromisoformat(p["before_acquired_start"][:10])).days


class Measures:
    """Everything measured once and shared by the steps: the site, its towns and the grids of every pair."""

    def __init__(self, site_id):
        (self.site, self.folder, self.towns, self.channels, self.pairs,
         self.channel_areas, self.events) = load_site(site_id)
        self.site_id = site_id
        self.km = to_km(self.site["summit_lat"], self.site["summit_lon"])
        self.grids = {p["id"]: load_grid(self.folder, p["id"]) for p in self.pairs}
        first_layer = next(iter(self.grids.values()))[1]
        (self.lons, self.lats), self.dx, self.dy = cell_centres(first_layer)
        self.lat_mid = (first_layer["bounds_north"] + first_layer["bounds_south"]) / 2
        self.map_bounds = {side: first_layer[f"bounds_{side}"] for side in ("west", "south", "east", "north")}
        # Which grid cells lie inside each town. This is the slow part, so it's done once.
        self.inside = {t["properties"]["id"]: contains_xy(shape(t["geometry"]), self.lons, self.lats) for t in self.towns}
        self.numbers = {t["properties"]["id"]: town_numbers(self.site, t, self.channels, self.km) for t in self.towns}
        self.pairs_by_id = {p["id"]: p for p in self.pairs}

    def sheet(self, pair_id):
        """The data sheet for one pair: one row per town, and the channel strips. Numbers only, no maps."""
        p = self.pairs_by_id[pair_id]
        grid = self.grids[pair_id][0]
        rows = []
        for town in self.towns:
            tid = town["properties"]["id"]
            possible, likely, nodata = flagged_in_town(grid, self.inside[tid], self.lat_mid, self.dx, self.dy)
            rows.append({
                "town_id": tid,
                "town_name": town["properties"]["name"],
                "possible_km2": round3(possible),
                "likely_km2": round3(likely),
                "flagged_km2": round3(possible + likely),
                "no_data_km2": round3(nodata),
                "checked_share": self.numbers[tid]["checked_share"],
            })
        return {
            "site_id": self.site_id,
            "pair_id": pair_id,
            "label": pair_label(p),
            "before": p["before_acquired_start"],
            "after": p["after_acquired_start"],
            "days": pair_days(p),
            "track": p["track"],
            "orbit_direction": p["orbit_direction"],
            "coherence_used": p["coherence_used"],
            "granules": self.grids[pair_id][1]["source_granule_ids"],
            "whole_site_km2": p["new_material_area_km2"],
            "towns": rows,
            "channel_rows": [{"channel_id": r["channel_id"], "flagged_km2": r["flagged_area_km2"],
                              "checked_km2": r["checked_area_km2"]}
                             for r in self.channel_areas if r["pair_id"] == pair_id],
        }


def numbers_only(sheet):
    """The parts of a sheet that must still match the published data before it can be approved."""
    keep = ("pair_id", "before", "after", "track", "coherence_used", "granules", "whole_site_km2", "towns", "channel_rows")
    return {key: sheet[key] for key in keep}


def read_sheet(folder):
    path = Path(folder) / "sheet.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def write_sheet_csv(path, sheet):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(sheet["towns"][0].keys()))
        writer.writeheader()
        writer.writerows(sheet["towns"])


def approved_sheets(m, public_root=PUBLIC):
    """The approved sheets for pairs that are still published, oldest first. Stale ones are left out."""
    sheets = []
    for folder in sorted((Path(public_root) / m.site_id / "passes").glob("*")):
        sheet = read_sheet(folder)
        if not sheet or sheet.get("status") != "approved":
            continue
        if sheet["pair_id"] not in m.pairs_by_id:
            print(f"warning: {sheet['pair_id']} is approved but no longer published, so the reports leave it out")
            continue
        if numbers_only(sheet) != numbers_only(m.sheet(sheet["pair_id"])):
            print(f"warning: {sheet['pair_id']} was approved, but the published data has changed since. "
                  "Review its new draft and approve it again.")
            continue
        sheets.append(sheet)
    return sorted(sheets, key=lambda s: (s["after"], s["track"]))


def make_drafts(m, drafts_root=DRAFTS, public_root=PUBLIC):
    """Step 1: a draft sheet and maps for every published pair that isn't approved yet (FR-116)."""
    approved = {s["pair_id"] for s in approved_sheets(m, public_root)}
    waiting = []
    for p in m.pairs:
        if p["id"] in approved:
            continue
        folder = Path(drafts_root) / m.site_id / p["id"]
        folder.mkdir(parents=True, exist_ok=True)
        sheet = {**m.sheet(p["id"]), "status": "draft"}
        old = read_sheet(folder)
        maps_ready = all((folder / f"{t['properties']['id']}_map.jpg").exists() for t in m.towns)
        # A draft whose numbers haven't changed keeps its maps, so a rerun is quick.
        if not (old and numbers_only(old) == numbers_only(sheet) and maps_ready):
            grid, layer, _ = m.grids[p["id"]]
            for town in m.towns:
                draw_town_map(folder / f"{town['properties']['id']}_map.jpg", m.site, m.folder, town, m.towns,
                              m.channels, grid, layer, p)
        write_json(folder / "sheet.json", sheet)
        write_sheet_csv(folder / "sheet.csv", sheet)
        waiting.append(p["id"])
    return waiting


def approve(m, pair_id, by, drafts_root=DRAFTS, public_root=PUBLIC, now=None):
    """Step 2: copy a reviewed draft into the public folder with the reviewer's name (FR-117)."""
    # "Your name" is the example in the help text, not a reviewer, so it's refused too.
    if not by or not by.strip() or by.strip().lower() == "your name":
        raise ValueError("Say who reviewed the sheet, with your real name: --by \"Juan dela Cruz\"")
    draft_folder = Path(drafts_root) / m.site_id / pair_id
    draft = read_sheet(draft_folder)
    if draft is None:
        raise ValueError(f"No draft for {pair_id}. Run: python pipeline/mrw/town_reports.py {m.site_id}")
    if pair_id not in m.pairs_by_id:
        raise ValueError(f"{pair_id} isn't published, so it can't be approved")
    if numbers_only(draft) != numbers_only(m.sheet(pair_id)):
        raise ValueError(f"The draft for {pair_id} no longer matches the published data. Run the script again "
                         "to make a fresh draft, review it, then approve it.")
    out = Path(public_root) / m.site_id / "passes" / pair_id
    out.mkdir(parents=True, exist_ok=True)
    for town in m.towns:
        name = f"{town['properties']['id']}_map.jpg"
        (out / name).write_bytes((draft_folder / name).read_bytes())
    when = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sheet = {**draft, "status": "approved", "reviewed_by": by.strip(), "reviewed_at": when}
    write_json(out / "sheet.json", sheet)
    write_sheet_csv(out / "sheet.csv", sheet)
    print(f"Approved {pair_id}, reviewed by {sheet['reviewed_by']} at {when}")


def zip_text(bundle, name, text):
    """Add a text file to a ZIP with a fixed date, so the same data always gives the same ZIP."""
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, text)


def write_bundle(path, m, town, rows, sheets):
    """One ZIP per town: its border, nearby checked channels, the flagged cells of every approved pass, and a table."""
    names = {c["id"] for c in m.numbers[town["properties"]["id"]]["channels"]}
    near = [{"type": "Feature", "properties": {"id": ch["properties"]["id"], "name": ch["properties"]["name"]},
             "geometry": ch["properties"]["checked_geometry"]} for ch in m.channels if ch["properties"]["id"] in names]
    inside = m.inside[town["properties"]["id"]]
    cells = []
    for sheet in sheets:
        grid = m.grids[sheet["pair_id"]][0]
        for r, c in zip(*np.nonzero(inside & ((grid == 1) | (grid == 2)))):
            x, y = float(m.lons[r, c]), float(m.lats[r, c])
            cells.append({"type": "Feature", "properties": {
                "class": int(grid[r, c]),
                "label": "Likely new material" if grid[r, c] == 2 else "Possible new material",
                "pair_id": sheet["pair_id"]},
                "geometry": mapping(box(x - m.dx / 2, y - m.dy / 2, x + m.dx / 2, y + m.dy / 2))})
    csv_text = io.StringIO()
    columns = [key for key in rows[0] if key not in ("map_image", "granules")]
    writer = csv.DictWriter(csv_text, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    readme = (
        f"Mayon Radar Watch town data: {town['properties']['name']}\n\n"
        "town.geojson            Town border (NAMRIA and PSA via OCHA COD-AB, CC BY-IGO)\n"
        "channels.geojson        Checked channel lines near the town (OpenStreetMap contributors, ODbL 1.0)\n"
        "flagged_cells.geojson   Flagged cells inside the town for every approved pass, by pair_id (about 20 m squares, EPSG:4326)\n"
        "passes.csv              Flagged area inside the town for every approved pass, in km², with who reviewed it\n\n"
        "Radar results: Mayon Radar Watch and NASA-ISRO NISAR data via ASF, CC BY 4.0. PROVISIONAL products.\n"
        "Not an official warning. Follow PHIVOLCS and your LGU.\n"
    )
    with zipfile.ZipFile(path, "w") as bundle:
        zip_text(bundle, "town.geojson", json.dumps({"type": "FeatureCollection", "features": [town]}))
        zip_text(bundle, "channels.geojson", json.dumps({"type": "FeatureCollection", "features": near}))
        zip_text(bundle, "flagged_cells.geojson", json.dumps({"type": "FeatureCollection", "features": cells}))
        zip_text(bundle, "passes.csv", csv_text.getvalue())
        zip_text(bundle, "README.txt", readme)


def thresholds(pairs):
    """The flag lines, from the published pairs. A pair without coherence has no coherence line,
    so that one comes from the newest pair that used coherence."""
    with_coherence = [p for p in pairs if p.get("coherence_loss_threshold") is not None]
    return {"brightness_db": pairs[-1]["brightness_threshold_db"],
            "coherence_loss": with_coherence[-1]["coherence_loss_threshold"] if with_coherence else None}


def build_public(m, public_root=PUBLIC):
    """Step 3: the public report files, made from approved sheets only (FR-118, FR-120)."""
    out = Path(public_root) / m.site_id
    out.mkdir(parents=True, exist_ok=True)
    sheets = approved_sheets(m, public_root)
    # Files from before the review step, or for a town no longer listed, are removed.
    keep = {"index.json"} | {f"{t['properties']['id']}{end}" for t in m.towns for end in (".json", "_locator.png", "_data.zip")}
    for path in out.glob("*.*"):
        if path.name not in keep:
            path.unlink()
    # The newest review time stands for when the reports were made, so a rebuild doesn't change it.
    made_at = max((s["reviewed_at"] for s in sheets), default=None)
    passes = [{key: s[key] for key in ("pair_id", "label", "before", "after", "days", "track", "orbit_direction",
                                        "coherence_used", "reviewed_by", "reviewed_at")} for s in sheets]
    index = []
    for town in m.towns:
        tp = town["properties"]
        tid = tp["id"]
        numbers = m.numbers[tid]
        loc_name = f"{tid}_locator.png"
        if not (out / loc_name).exists():
            draw_locator(out / loc_name, m.site, m.towns, town)
        rows = []
        for s in sheets:
            mine = next(r for r in s["towns"] if r["town_id"] == tid)
            rows.append({
                "pair_id": s["pair_id"], "label": s["label"], "before": s["before"], "after": s["after"],
                "days": s["days"], "track": s["track"], "orbit_direction": s["orbit_direction"],
                "coherence_used": s["coherence_used"], "possible_km2": mine["possible_km2"],
                "likely_km2": mine["likely_km2"], "flagged_km2": mine["flagged_km2"],
                "no_data_km2": mine["no_data_km2"], "whole_site_km2": s["whole_site_km2"],
                "granules": s["granules"], "map_image": f"passes/{s['pair_id']}/{tid}_map.jpg",
                "reviewed_by": s["reviewed_by"], "reviewed_at": s["reviewed_at"],
            })
        index.append({"town_id": tid, "town_name": tp["name"], "town_kind": tp["kind"],
                      "nearest_km_to_summit": numbers["nearest_km_to_summit"],
                      "checked_share": numbers["checked_share"],
                      "channel_names": [c["name"] for c in numbers["channels"]],
                      "flagged_by_pass": {r["pair_id"]: r["flagged_km2"] for r in rows}})
        if not sheets:
            for end in (".json", "_data.zip"):
                (out / f"{tid}{end}").unlink(missing_ok=True)
            continue
        channel_ids = {c["id"] for c in numbers["channels"]}
        approved_ids = {s["pair_id"] for s in sheets}
        report = {
            "data": {
                "id": f"{tid}_report",
                "site_id": m.site_id,
                "town_id": tid,
                "town_name": tp["name"],
                "town_kind": tp["kind"],
                "psgc_code": tp.get("source_code"),
                "province": "Albay",
                "report_version": REPORT_VERSION,
                "generated_at": made_at,
                "map_bounds": m.map_bounds,
                # FR-119: the report reads these instead of typing them.
                "thresholds": thresholds(m.pairs),
                "site_channel_names": [ch["properties"]["name"] for ch in m.channels],
                "summit": {"lat": m.site["summit_lat"], "lon": m.site["summit_lon"]},
                "danger_zone_radius_km": m.site["danger_zone_radius_km"],
                "detection_reach_km": m.site["detection_reach_km"],
                "channel_strip_half_width_m": m.site["channel_strip_half_width_m"],
                "court_km2": COURT_KM2,
                **numbers,
                "pairs": rows,
                "channel_rows": [{"channel_id": r["channel_id"], "pair_id": r["pair_id"], "flagged_km2": r["flagged_area_km2"],
                                  "checked_km2": r["checked_area_km2"]}
                                 for r in m.channel_areas if r["channel_id"] in channel_ids and r["pair_id"] in approved_ids],
                "events": [{"name": e["name"], "date": e["event_date"], "source_name": e["source_name"],
                            "source_url": e["source_url"]} for e in m.events],
                "locator_image": loc_name,
                "bundle": f"{tid}_data.zip",
            },
            "meta": {"generated_at": made_at, "schema_version": "1.0"},
        }
        write_json(out / f"{tid}.json", report)
        write_bundle(out / f"{tid}_data.zip", m, town, rows, sheets)
    index.sort(key=lambda r: r["nearest_km_to_summit"])
    write_json(out / "index.json", {"data": index, "meta": {"generated_at": made_at, "passes": passes,
                                                           "schema_version": "1.0"}})
    return sheets


def main(argv):
    """Run:  python pipeline/mrw/town_reports.py mayon
       or:   python pipeline/mrw/town_reports.py mayon --approve <pair id>|all --by "Your name"
    """
    site_id = argv[0] if argv and not argv[0].startswith("--") else "mayon"
    m = Measures(site_id)
    if "--approve" in argv:
        start = argv.index("--approve") + 1
        chosen = [a for a in argv[start:] if not a.startswith("--")]
        if "--by" in argv:
            by_at = argv.index("--by")
            chosen = [a for a in chosen if a not in argv[by_at + 1:by_at + 2]]
            by = argv[by_at + 1] if by_at + 1 < len(argv) else ""
        else:
            by = ""
        if chosen == ["all"]:
            chosen = [p.name for p in sorted((DRAFTS / site_id).glob("*")) if (p / "sheet.json").exists()]
        for pair_id in chosen:
            approve(m, pair_id, by)
    else:
        waiting = make_drafts(m)
        if waiting:
            print(f"Waiting for review ({len(waiting)}): open sheet.csv and the maps in {DRAFTS / site_id}/<pair id>/,")
            print(f"then run: python pipeline/mrw/town_reports.py {site_id} --approve <pair id> --by \"Your name\"")
            for pair_id in waiting:
                print(f"  {pair_id}")
    sheets = build_public(m)
    print(f"Public town reports: {len(sheets)} approved {'pass' if len(sheets) == 1 else 'passes'}"
          f"{', newest ' + sheets[-1]['pair_id'] if sheets else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
