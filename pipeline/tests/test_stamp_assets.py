"""The page must link the current version of every JS and CSS file."""
from mrw.stamp_assets import INDEX, PAGE_3D, PAGE_REPORT, SITE, stamped_3d_page, stamped_page, stamped_report_page, version_of


def page_text():
    return INDEX.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_the_page_is_stamped_with_the_current_files():
    assert page_text() == stamped_page(page_text()), "Run: python pipeline/mrw/stamp_assets.py"


def test_every_module_is_in_the_import_map():
    for path in (SITE / "js").glob("*.js"):
        assert f'"./js/{path.name}": "./js/{path.name}?v={version_of(path)}"' in page_text()


def test_stamping_twice_changes_nothing():
    once = stamped_page(page_text())
    assert stamped_page(once) == once


def test_changing_a_file_changes_its_version(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "css").mkdir()
    (tmp_path / "css" / "app.css").write_text("a", encoding="utf-8")
    module = tmp_path / "js" / "main.js"
    module.write_text("one", encoding="utf-8")
    page = '<link href="css/app.css"><script type="module" src="js/main.js"></script>'
    first = stamped_page(page.replace("<script", "  <script"), tmp_path)
    module.write_text("two", encoding="utf-8")
    assert stamped_page(first, tmp_path) != first


def test_the_3d_page_is_stamped_with_the_current_files():
    text = PAGE_3D.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert text == stamped_3d_page(text), "Run: python pipeline/mrw/stamp_assets.py"
    for folder in ("js", "3d"):
        for path in (SITE / folder).glob("*.js"):
            assert f'"./{folder}/{path.name}": "./{folder}/{path.name}?v={version_of(path)}"' in text


def test_the_report_page_is_stamped_with_the_current_files():
    text = PAGE_REPORT.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert text == stamped_report_page(text), "Run: python pipeline/mrw/stamp_assets.py"
    assert f'report/report.js?v={version_of(SITE / "report" / "report.js")}' in text
