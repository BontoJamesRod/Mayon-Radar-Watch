"""TC-122 to TC-125, TC-127 and TC-130 to TC-132: the town reports in a browser (F-26, US-036, SCR-16)."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import expect

from .conftest import SITE, go_to_panama, prepare_page, wait_until_ready
from .test_accessibility import problems_on

pytestmark = pytest.mark.e2e

REPORTS = SITE / "report" / "data" / "mayon"
INDEX_FILE = json.loads((REPORTS / "index.json").read_text(encoding="utf-8"))
INDEX = INDEX_FILE["data"]
# Approved passes, newest first, as the Pass list shows them (FR-118).
PASSES = sorted(INDEX_FILE["meta"]["passes"], key=lambda p: (p["after"], p["track"]), reverse=True)
NOTICE = "Not an official warning"
# Without an approved pass there is no report to test, so these tests wait for the owner's review.
needs_a_pass = pytest.mark.skipif(not PASSES, reason="no pass is approved yet")


def town_report(town_id):
    return json.loads((REPORTS / f"{town_id}.json").read_text(encoding="utf-8"))["data"]


def open_report(page, site_url, query="", width=1280, height=900, problems=None):
    """Open the report page and wait until the list or the report is drawn."""
    prepare_page(page, width=width, height=height)
    if problems is not None:
        page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: problems.append(str(error)))
    page.goto(f"{site_url}report.html{query}")
    page.wait_for_selector("#report .paper")


def test_at_least_one_pass_is_approved():
    """The reports show nothing until the owner approves a data sheet (FR-117).
    Review the drafts, then run: python pipeline/mrw/town_reports.py mayon --approve <pair id> --by "Your name"."""
    assert PASSES, "no pass is approved for the town reports yet"


@needs_a_pass
def test_tc122_the_list_has_every_town_nearest_first(page, site_url):
    open_report(page, site_url)
    links = page.locator("#report table tbody tr td:first-child a")
    expect(links).to_have_count(len(INDEX))
    assert links.all_text_contents() == [town["town_name"] for town in INDEX]
    assert links.first.get_attribute("href") == f"?site=mayon&town={INDEX[0]['town_id']}&pass={PASSES[0]['pair_id']}"
    # The list has no town, so it offers no town's data.
    expect(page.locator("#bundle-link")).to_be_hidden()


@needs_a_pass
def test_tc130_the_pass_list_holds_only_approved_passes_newest_first(page, site_url):
    open_report(page, site_url)
    options = page.locator("#pass-select option")
    assert [options.nth(i).get_attribute("value") for i in range(options.count())] == [p["pair_id"] for p in PASSES]
    expect(page.locator("#pass-select")).to_have_value(PASSES[0]["pair_id"])


@needs_a_pass
def test_tc130_the_pass_list_is_grouped_by_month_and_labels_the_newest_and_long_gaps(page, site_url):
    """T-163: one group per month of the later pass (Manila time), newest month first."""
    open_report(page, site_url)
    groups = page.locator("#pass-select optgroup")
    labels = [groups.nth(i).get_attribute("label") for i in range(groups.count())]
    manila = [datetime.fromisoformat(p["after"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8)))
              for p in PASSES]
    expected = list(dict.fromkeys(f"{d:%B %Y}" for d in manila))
    assert labels == expected
    texts = page.locator("#pass-select option").all_text_contents()
    assert "(newest" in texts[0] and not any("newest" in t for t in texts[1:])
    for p, text in zip(PASSES, texts):
        assert (f"{p['days']}-day gap" in text) == (p["days"] > 12), text


@needs_a_pass
def test_tc130_an_unapproved_pass_in_the_address_falls_back_to_the_newest(page, site_url):
    open_report(page, site_url, "?town=mayon_daraga&pass=mayon_A111F008_20990101_20990113")
    expect(page.locator("#pass-select")).to_have_value(PASSES[0]["pair_id"])


@pytest.mark.skipif(len(PASSES) < 2, reason="needs two approved passes")
def test_tc131_choosing_an_older_pass_shows_that_pass(page, site_url):
    older = PASSES[-1]
    open_report(page, site_url, "?town=mayon_daraga")
    page.select_option("#pass-select", older["pair_id"])
    page.wait_for_url(re.compile(rf"pass={older['pair_id']}"))
    page.wait_for_selector("#report .paper")
    row = next(r for r in town_report("mayon_daraga")["pairs"] if r["pair_id"] == older["pair_id"])
    assert page.locator("figure.map img").get_attribute("src").endswith(row["map_image"])
    expect(page.locator(".abstract")).to_contain_text("The passes of this report flagged")
    expect(page.locator("#report table tbody tr", has_text="▶")).to_have_count(1)
    expect(page.locator(".chosen-mark")).to_have_count(1)
    expect(page.locator(".appendix")).to_contain_text(f"Data sheet reviewed{row['reviewed_by']}")
    expect(page.locator("#town-select")).to_have_value("mayon_daraga")


@needs_a_pass
def test_tc132_the_wording_comes_from_the_data(page, site_url):
    report = town_report("mayon_camalig")
    names = report["site_channel_names"]
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    for p in PASSES:
        row = next(r for r in report["pairs"] if r["pair_id"] == p["pair_id"])
        page.goto(f"{site_url}report.html?town=mayon_camalig&pass={p['pair_id']}")
        page.wait_for_selector("#report .paper")
        text = page.locator("#report").inner_text()
        # Camalig has no checked channel, so the report names how many there are, and which.
        assert f"None of the {words[len(names)]} checked channels runs through the town." in text
        assert ", ".join(names[:-1]) + " and " + names[-1] in text
        assert f"a coherence loss above {report['thresholds']['coherence_loss']:g} raises it" in text
        assert ("This pass is brightness only" in text) == (not row["coherence_used"])
        versions = {re.search(r"_(P\d{5})_", g).group(1) for g in row["granules"]}
        assert ("different ASF processor versions" in text) == (len(versions) > 1), p["pair_id"]


@needs_a_pass
def test_tc122_a_town_in_the_list_opens_its_report(page, site_url):
    open_report(page, site_url)
    page.click("#report a:text('Daraga')")
    expect(page.locator(".doc-sub")).to_contain_text("Daraga, Albay")
    expect(page.locator("#town-select")).to_have_value("mayon_daraga")


@needs_a_pass
def test_tc123_daragas_report_renders_with_no_console_errors(page, site_url):
    problems = []
    open_report(page, site_url, "?town=mayon_daraga", problems=problems)
    expect(page.locator(".doc-sub")).to_contain_text("Daraga")
    headings = page.locator("#report h2").all_text_contents()
    for title in ("Basic Information", "Abstract", "Introduction", "Data and Methods", "Results", "Discussion",
                  "Conclusion and Public Notice", "Acknowledgement", "Data Availability", "References"):
        assert any(title in heading for heading in headings), title
    # Every picture loaded, and the data link points at Daraga's bundle.
    assert page.evaluate("[...document.querySelectorAll('#report img')].every((img) => img.complete && img.naturalWidth > 0)")
    assert page.locator("#bundle-link").get_attribute("href").endswith("mayon_daraga_data.zip")
    assert problems == []


@needs_a_pass
@pytest.mark.parametrize("town_id", ["mayon_daraga", "mayon_santo_domingo", "mayon_polangui"])
def test_tc124_figures_and_tables_are_numbered_in_order(page, site_url, town_id):
    open_report(page, site_url, f"?town={town_id}")
    labels = page.locator("#report .cap-label").all_text_contents()
    for kind in ("Figure", "Table"):
        numbers = [int(re.match(rf"{kind} (\d+)\.", label).group(1)) for label in labels if label.startswith(kind)]
        assert numbers == list(range(1, len(numbers) + 1)), kind
    # Every "Figure n" or "Table n" in the text names a caption that exists, and none is left as "?".
    body = page.locator("#report").inner_text()
    named = {label.rstrip(".") for label in labels}
    assert set(re.findall(r"\b(?:Figure|Table) \d+\b", body)) <= named
    assert not re.search(r"\b(?:Figure|Table) \?", body) and " ?)" not in body


@needs_a_pass
def test_tc125_the_notice_shows_on_the_list_and_on_a_report(page, site_url):
    open_report(page, site_url)
    expect(page.locator("#report")).to_contain_text(NOTICE)
    page.goto(f"{site_url}report.html?town=mayon_daraga")
    page.wait_for_selector("#report .paper")
    expect(page.locator(".notice-line")).to_have_text("Not an official warning. Follow PHIVOLCS and your LGU.")
    expect(page.locator(".notice .head")).to_have_text("Public Notice")
    for name in ("Save as PDF", "Download data (ZIP)", "← Back to map"):
        expect(page.locator("header.toolbar").get_by_text(name)).to_be_visible()


@needs_a_pass
@pytest.mark.parametrize("query", ["", "?town=mayon_daraga"])
def test_tc125_axe_passes(page, site_url, query):
    open_report(page, site_url, query)
    assert problems_on(page) == []


@needs_a_pass
def test_a_strange_site_in_the_address_cant_reach_the_page(page, site_url):
    """T-154: ?site= goes into the list's links, so only a plain site id is used."""
    # "/.." cancels the planted folder name, so the data still loads and the list is drawn.
    open_report(page, site_url, "?site=mayon/%22%3E%3Cimg%20id%3Dplanted%20src%3Dx%3E/..")
    expect(page.locator("#planted")).to_have_count(0)
    assert page.locator("#report table a").first.get_attribute("href").startswith("?site=mayon&town=")


@pytest.mark.parametrize("width,height", [(1280, 800), (360, 740)])
def test_tc127_the_2d_map_links_to_the_town_reports_on_mayon(page, site_url, width, height):
    prepare_page(page, width=width, height=height)
    page.goto(site_url)
    wait_until_ready(page)
    link = page.locator("#town-reports")
    expect(link).to_be_visible()
    expect(link).to_have_accessible_name("Town reports")
    box = link.bounding_box()
    assert box["height"] >= 44 and box["width"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert problems_on(page) == []
    link.click()
    page.wait_for_selector("#report .paper")
    assert page.url.endswith("/report.html")


def test_tc127_the_panama_test_site_has_no_town_reports_link(page, site_url):
    prepare_page(page)
    page.goto(site_url)
    wait_until_ready(page)
    go_to_panama(page)
    expect(page.locator("#town-reports")).to_be_hidden()
