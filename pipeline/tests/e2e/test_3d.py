"""TC-114 to TC-117: the 3D view (F-25, US-035, SCR-15)."""
import json

import pytest
from playwright.sync_api import expect

from .conftest import ROOT, SITE, go_to_panama, latest_pair, prepare_page, wait_until_ready
from .test_accessibility import problems_on

pytestmark = pytest.mark.e2e

SCREENS = ROOT / "pipeline" / "out" / "screens" / "3d"
CHANNELS = json.loads((SITE / "data" / "sites" / "mayon" / "channels.geojson").read_text(encoding="utf-8"))
CHANNEL_NAMES = sorted(feature["properties"]["name"] for feature in CHANNELS["features"])
DISCLAIMER_SHORT = "Not an official warning · Follow PHIVOLCS"
NO_WEBGL = """
const original = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
  return String(kind).startsWith("webgl") ? null : original.call(this, kind, ...rest);
};
"""


def open_3d(page, site_url, width=1280, height=800, problems=None):
    prepare_page(page, width=width, height=height)
    if problems is not None:
        page.on("pageerror", lambda error: problems.append(str(error)))
    page.goto(f"{site_url}3d.html")
    page.wait_for_function("document.body.dataset.state === 'ready'", timeout=30000)


def boxes_overlap(a, b):
    return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_tc114_the_3d_page_loads_with_terrain_and_the_latest_pass(page, site_url, width, height):
    problems = []
    open_3d(page, site_url, width, height, problems)
    assert page.evaluate("window.map3d.getTerrain().exaggeration") == 1.5
    assert page.evaluate("window.map3d.getLayoutProperty('relief', 'visibility')") != "none"
    assert page.evaluate("window.map3d.getLayoutProperty('satellite', 'visibility')") == "none"
    assert page.evaluate("window.map3d.getLayer('new-material') !== undefined")
    expect(page.locator("#pair-list")).to_have_value(latest_pair()["id"])
    expect(page.locator("#pair-label")).not_to_be_empty()
    assert problems == []
    page.wait_for_function("window.map3d.areTilesLoaded()", timeout=30000)
    SCREENS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENS / f"3d-{width}.png"))


def test_tc114_the_pass_selector_changes_the_image_and_the_label(page, site_url):
    open_3d(page, site_url)
    before = page.text_content("#product-label")
    page.click("#previous")
    expect(page.locator("#product-label")).not_to_have_text(before)
    expect(page.locator("#pair-list")).not_to_have_value(latest_pair()["id"])


def test_tc115_only_the_confirmed_channels_appear(page, site_url):
    requested = []
    page.on("request", lambda request: requested.append(request.url))
    open_3d(page, site_url)
    drawn = page.evaluate("window.map3d.getStyle().sources.channels.data.features.map((f) => f.properties.name)")
    assert sorted(drawn) == CHANNEL_NAMES and len(drawn) == 4
    expect(page.locator(".channel-label-3d")).to_have_count(4)
    assert sorted(page.locator(".channel-label-3d").all_text_contents()) == CHANNEL_NAMES
    assert not [url for url in requested if "candidate" in url]


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_tc116_the_disclaimer_the_nisar_label_and_the_2d_link_are_visible(page, site_url, width, height):
    open_3d(page, site_url, width, height)
    expect(page.locator(".disclaimer-tag")).to_have_text(DISCLAIMER_SHORT)
    expect(page.locator(".disclaimer-tag")).to_be_in_viewport()
    label = page.locator("#product-label")
    expect(label).to_be_in_viewport()
    expect(label).to_contain_text("NISAR GCOV")
    back = page.locator(".back-link")
    expect(back).to_be_in_viewport()
    assert back.get_attribute("href") == "./"
    # The NISAR label, the credits and the controls never cover each other.
    credits = page.locator(".maplibregl-ctrl-attrib").bounding_box()
    controls = page.locator(".controls").bounding_box()
    assert not boxes_overlap(label.bounding_box(), credits)
    assert not boxes_overlap(credits, controls)


def test_satellite_keeps_the_eox_credit_in_full(page, site_url):
    open_3d(page, site_url)
    credits = page.locator(".maplibregl-ctrl-attrib")
    expect(credits).not_to_contain_text("EOxCloudless")
    page.click("#basemap-satellite")
    expect(page.locator("#basemap-satellite")).to_have_attribute("aria-pressed", "true")
    expect(credits).to_contain_text("EOxCloudless by EOX IT Services GmbH")
    expect(credits.get_by_role("link", name="EOxCloudless")).to_be_in_viewport()
    assert "maplibregl-compact" not in (credits.get_attribute("class") or "")


def test_orbit_turns_the_view_and_a_second_press_stops_it(page, site_url):
    open_3d(page, site_url)
    start = page.evaluate("window.map3d.getBearing()")
    page.click("#orbit")
    expect(page.locator("#orbit")).to_have_attribute("aria-pressed", "true")
    page.wait_for_function(f"Math.abs(window.map3d.getBearing() - ({start})) > 2")
    page.click("#orbit")
    expect(page.locator("#orbit")).to_have_attribute("aria-pressed", "false")
    stopped = page.evaluate("window.map3d.getBearing()")
    page.wait_for_timeout(500)
    assert page.evaluate("window.map3d.getBearing()") == stopped


def test_with_reduced_motion_orbit_steps_and_nothing_moves_on_its_own(page, site_url):
    page.emulate_media(reduced_motion="reduce")
    open_3d(page, site_url)
    start = page.evaluate("window.map3d.getBearing()")
    page.click("#orbit")
    turned = page.evaluate("window.map3d.getBearing()")
    assert round((turned - start) % 360) == 45
    expect(page.locator("#orbit-note")).to_be_visible()
    page.wait_for_timeout(500)
    assert page.evaluate("window.map3d.getBearing()") == turned
    page.click("#reset-view")
    assert round(page.evaluate("window.map3d.getBearing()")) == -20


def test_tc117_axe_passes(page, site_url):
    open_3d(page, site_url)
    assert problems_on(page) == []


def test_tc117_without_webgl_the_page_says_so_and_links_to_the_2d_map(page, site_url):
    prepare_page(page)
    page.add_init_script(NO_WEBGL)
    page.goto(f"{site_url}3d.html")
    problem = page.locator("#problem")
    expect(problem).to_be_visible()
    expect(problem).to_contain_text("The 3D view needs WebGL")
    assert problem.get_by_role("link", name="Open the 2D map").get_attribute("href") == "./"
    expect(page.locator(".disclaimer-tag")).to_have_text(DISCLAIMER_SHORT)
    assert problems_on(page) == []


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_tc118_the_2d_map_and_the_3d_view_link_both_ways(page, site_url, width, height):
    prepare_page(page, width=width, height=height)
    page.goto(site_url)
    wait_until_ready(page)
    link = page.locator("#view-3d")
    expect(link).to_have_text("3D view")
    expect(link).to_be_in_viewport()
    assert link.bounding_box()["height"] >= 44
    link.click()
    page.wait_for_function("document.body.dataset.state === 'ready'", timeout=30000)
    assert page.url.endswith("/3d.html")
    page.click(".back-link")
    wait_until_ready(page)
    expect(page.locator("#view-3d")).to_be_visible()


def test_tc118_the_panama_test_site_links_to_its_own_3d_view_and_back(page, site_url):
    prepare_page(page)
    page.goto(site_url)
    wait_until_ready(page)
    go_to_panama(page)
    link = page.locator("#view-3d")
    expect(link).to_be_visible()
    assert link.get_attribute("href") == "3d.html?site=panama"
    link.click()
    page.wait_for_function("document.body.dataset.state === 'ready'", timeout=30000)
    expect(page.locator("#site-name")).to_have_text("Azuero Peninsula, Panama")
    page.click(".back-link")
    wait_until_ready(page)
    expect(page.locator("#site-name")).to_have_text("Azuero Peninsula, Panama")
    expect(page.locator("#test-banner")).to_be_visible()


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_tc119_panama_in_3d(page, site_url, width, height):
    problems = []
    prepare_page(page, width=width, height=height)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.goto(f"{site_url}3d.html?site=panama")
    page.wait_for_function("document.body.dataset.state === 'ready'", timeout=30000)
    assert page.evaluate("window.map3d.getTerrain().exaggeration") == 1.5
    assert page.evaluate("window.map3d.getStyle().sources.terrain.tiles[0]").endswith("data/sites/panama/terrain/{z}/{x}/{y}.png")
    # Panama has no channels, summit or danger zone, so none of those are drawn.
    assert page.evaluate("window.map3d.getStyle().sources.channels.data.features.length") == 0
    assert page.evaluate("window.map3d.getStyle().sources.rings.data.features.length") == 0
    expect(page.locator(".channel-label-3d, .zone-label-3d")).to_have_count(0)
    expect(page.locator("#test-banner")).to_be_visible()
    expect(page.locator("#disclaimer-tag")).to_have_text("Not an official warning · Follow SINAPROC")
    expect(page.locator("#product-label")).to_contain_text("NISAR")
    expect(page.locator(".maplibregl-ctrl-attrib")).to_contain_text("geoBoundaries")
    expect(page.locator(".maplibregl-ctrl-attrib")).not_to_contain_text("OpenStreetMap")
    expect(page.locator("#orbit")).to_have_text("Orbit the map")
    expect(page.locator("#pair-list")).to_have_value("panama_D141F085_20260927_20261009")
    assert page.locator(".back-link").get_attribute("href") == "./?site=panama"
    assert problems_on(page) == []
    assert problems == []
    page.wait_for_function("window.map3d.areTilesLoaded()", timeout=30000)
    SCREENS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENS / f"3d-panama-{width}.png"))
    page.click(".test-back")
    page.wait_for_function("document.body.dataset.state === 'ready'", timeout=30000)
    expect(page.locator("#site-name")).to_have_text("Mayon Volcano, Albay")
    expect(page.locator("#test-banner")).to_be_hidden()
