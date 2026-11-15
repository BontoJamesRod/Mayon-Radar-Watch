"""TC-120, TC-121, TC-128, TC-129, TC-133: the town reports' numbers, files and review step
(F-26, FR-109, FR-110, FR-116, FR-117, FR-120).

The first tests read the approved sheets in site/report/data/mayon/. The review tests work on a
copy in a temporary folder, so they never change the real files.
"""
import hashlib
import json
import shutil
import zipfile

import numpy as np
import pytest

from mrw.town_reports import (SITE, KM_PER_DEG_LAT, Measures, approve, approved_sheets, build_public, cell_centres,
                              km_per_deg_lon, load_grid, make_drafts, pair_label, read_sheet)

SITE_ID = "mayon"
SITE_DATA = SITE / "data" / "sites" / SITE_ID
REPORTS = SITE / "report" / "data" / SITE_ID
TOWNS = json.loads((SITE_DATA / "towns.geojson").read_text(encoding="utf-8"))["features"]
TOWN_IDS = sorted(town["properties"]["id"] for town in TOWNS)
PAIRS = {p["id"]: p for p in json.loads((SITE_DATA / "pairs.json").read_text(encoding="utf-8"))["data"]}
APPROVED = sorted(path.parent for path in (REPORTS / "passes").glob("*/sheet.json"))
# The grid is about 20 m, while the published area is measured at full resolution and rounded to
# 0.01 km², so the two differ a little. The towns must still add up to the grid (TC-120).
GRID_TOLERANCE_KM2 = 0.02
PUBLISHED_TOLERANCE_KM2 = 0.03


@pytest.fixture(scope="module")
def measures():
    """Measuring every town on every grid takes a while, so it's done once for these tests."""
    return Measures(SITE_ID)


def grid_flagged_km2(pair_id):
    """The flagged area of the whole published grid, counted the same way as the script counts a town."""
    grid, layer, _ = load_grid(SITE_DATA, pair_id)
    _, dx, dy = cell_centres(layer)
    lat_mid = (layer["bounds_north"] + layer["bounds_south"]) / 2
    return np.count_nonzero((grid == 1) | (grid == 2)) * dx * km_per_deg_lon(lat_mid) * dy * KM_PER_DEG_LAT


def file_hashes(folder):
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


# ---------- the approved sheets in the repo ----------

@pytest.mark.parametrize("folder", APPROVED, ids=lambda folder: folder.name)
def test_tc120_the_towns_add_up_to_each_approved_pass(folder):
    sheet = read_sheet(folder)
    assert sorted(row["town_id"] for row in sheet["towns"]) == TOWN_IDS
    towns_total = sum(row["flagged_km2"] for row in sheet["towns"])
    assert abs(towns_total - grid_flagged_km2(sheet["pair_id"])) <= GRID_TOLERANCE_KM2
    assert abs(towns_total - PAIRS[sheet["pair_id"]]["new_material_area_km2"]) <= PUBLISHED_TOLERANCE_KM2
    for row in sheet["towns"]:
        assert row["flagged_km2"] == pytest.approx(row["possible_km2"] + row["likely_km2"], abs=0.002)


@pytest.mark.parametrize("folder", APPROVED, ids=lambda folder: folder.name)
def test_tc121_every_approved_pass_has_a_map_per_town_and_a_real_reviewer(folder):
    sheet = read_sheet(folder)
    assert sheet["status"] == "approved" and sheet["reviewed_at"]
    # A trial approval must never be committed: only the owner's own review counts.
    assert sheet["reviewed_by"].strip() and "TEST RUN" not in sheet["reviewed_by"].upper()
    assert sheet["reviewed_by"].strip().lower() != "your name", "the example name from the help text was used"
    for town_id in TOWN_IDS:
        assert (folder / f"{town_id}_map.jpg").stat().st_size > 0


def test_tc121_every_approved_sheet_still_matches_the_published_data(measures):
    """A pair republished after its sheet was approved must be reviewed again (FR-117)."""
    assert [sheet["pair_id"] for sheet in approved_sheets(measures)] == sorted(
        (read_sheet(folder)["pair_id"] for folder in APPROVED), key=lambda pid: (PAIRS[pid]["after_acquired_start"], PAIRS[pid]["track"]))


@pytest.mark.skipif(not APPROVED, reason="no pass is approved yet")
@pytest.mark.parametrize("town_id", TOWN_IDS)
def test_tc121_every_town_has_its_json_locator_and_zip(town_id):
    report = json.loads((REPORTS / f"{town_id}.json").read_text(encoding="utf-8"))["data"]
    assert (REPORTS / report["locator_image"]).stat().st_size > 0
    assert [row["pair_id"] for row in report["pairs"]] == [read_sheet(f)["pair_id"] for f in sorted(
        APPROVED, key=lambda f: (PAIRS[f.name]["after_acquired_start"], PAIRS[f.name]["track"]))]
    for row in report["pairs"]:
        assert (REPORTS / row["map_image"]).exists()
    with zipfile.ZipFile(REPORTS / report["bundle"]) as bundle:
        assert sorted(bundle.namelist()) == ["README.txt", "channels.geojson", "flagged_cells.geojson", "passes.csv", "town.geojson"]


def test_tc121_the_index_lists_every_town_nearest_first_and_only_approved_passes():
    index = json.loads((REPORTS / "index.json").read_text(encoding="utf-8"))
    assert sorted(row["town_id"] for row in index["data"]) == TOWN_IDS
    distances = [row["nearest_km_to_summit"] for row in index["data"]]
    assert distances == sorted(distances)
    assert sorted(p["pair_id"] for p in index["meta"]["passes"]) == sorted(f.name for f in APPROVED)


def test_nothing_from_before_the_review_step_is_left_public():
    """The old one-map-per-town files are gone; maps now live with each approved pass."""
    assert not list(REPORTS.glob("*_map.jpg"))


# ---------- the review step, on a copy ----------

@pytest.fixture
def one_pair(measures):
    """The measures, cut down to the newest pair, so a draft only draws 12 maps."""
    newest = measures.pairs[-1]
    measures.pairs, saved = [newest], measures.pairs
    yield measures, newest["id"]
    measures.pairs = saved


def test_tc128_a_draft_is_written_outside_the_site(one_pair, tmp_path):
    m, pair_id = one_pair
    drafts, public = tmp_path / "drafts", tmp_path / "public"
    assert make_drafts(m, drafts, public) == [pair_id]
    draft = drafts / SITE_ID / pair_id
    assert read_sheet(draft)["status"] == "draft"
    assert (draft / "sheet.csv").read_text(encoding="utf-8").startswith("town_id,town_name,possible_km2")
    assert len(list(draft.glob("*_map.jpg"))) == len(TOWN_IDS)
    build_public(m, public)
    assert not (public / SITE_ID / "passes").exists()
    assert json.loads((public / SITE_ID / "index.json").read_text(encoding="utf-8"))["meta"]["passes"] == []


def test_tc129_approving_needs_a_name_stamps_the_sheet_and_refuses_a_changed_draft(one_pair, tmp_path):
    m, pair_id = one_pair
    drafts, public = tmp_path / "drafts", tmp_path / "public"
    make_drafts(m, drafts, public)
    with pytest.raises(ValueError, match="who reviewed"):
        approve(m, pair_id, " ", drafts, public)
    with pytest.raises(ValueError, match="who reviewed"):
        approve(m, pair_id, "Your name", drafts, public)
    # A draft whose numbers no longer match the published data is refused, and nothing is copied.
    path = drafts / SITE_ID / pair_id / "sheet.json"
    good = path.read_text(encoding="utf-8")
    changed = json.loads(good)
    changed["towns"][0]["flagged_km2"] += 1
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="no longer matches"):
        approve(m, pair_id, "Owner", drafts, public)
    assert not (public / SITE_ID / "passes").exists()
    path.write_text(good, encoding="utf-8")
    approve(m, pair_id, "Owner", drafts, public, now="2026-11-15T00:00:00Z")
    sheet = read_sheet(public / SITE_ID / "passes" / pair_id)
    assert (sheet["status"], sheet["reviewed_by"], sheet["reviewed_at"]) == ("approved", "Owner", "2026-11-15T00:00:00Z")
    assert [s["pair_id"] for s in build_public(m, public)] == [pair_id]
    # Once approved, the pass gets no new draft.
    assert make_drafts(m, drafts, public) == []


def test_tc133_building_twice_changes_no_public_file(measures, tmp_path):
    public = tmp_path / "public"
    if APPROVED:
        shutil.copytree(REPORTS / "passes", public / SITE_ID / "passes")
    build_public(measures, public)
    first = file_hashes(public)
    build_public(measures, public)
    assert file_hashes(public) == first


def test_pair_labels_work_on_every_computer():
    """%-d isn't known on Windows, so the label is built without it."""
    pair = {"before_acquired_start": "2026-10-07T21:13:19Z", "after_acquired_start": "2026-10-19T21:13:19Z"}
    assert pair_label(pair) == "Oct 7 – Oct 19, 2026"
