"""Put a version on each JS and CSS link in site/index.html, so visitors don't get stale code.

Run from the project folder after changing anything in site/js or site/css:
    python pipeline/mrw/stamp_assets.py

The version is a short hash of the file, so it only changes when the file does, and a test
fails if someone forgets to run this. JavaScript modules import each other by plain names,
so the page's import map says which version each name means.
"""
import hashlib
import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "site"
INDEX = SITE / "index.html"
PAGE_3D = SITE / "3d.html"  # the 3D view (T-149), with its own CSS and module
PAGE_REPORT = SITE / "report.html"  # the town reports (T-154)
MAP_START = '<script type="importmap">'
MAP_PATTERN = re.compile(r'[ \t]*<script type="importmap">.*?</script>\r?\n', re.DOTALL)


def version_of(path):
    """Return a short hash of a file, ignoring line endings, which differ between computers."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]


def versioned(relative_path, site=SITE):
    return f"{relative_path}?v={version_of(site / relative_path)}"


def stamped_page(text, site=SITE):
    """Return the page's text with up-to-date links and import map."""
    text = re.sub(r'href="css/app\.css[^"]*"', f'href="{versioned("css/app.css", site)}"', text)
    text = re.sub(r'src="js/main\.js[^"]*"', f'src="{versioned("js/main.js", site)}"', text)
    names = sorted(path.name for path in (site / "js").glob("*.js"))
    imports = {f"./js/{name}": f"./{versioned(f'js/{name}', site)}" for name in names}
    block = f"  {MAP_START}\n{json.dumps({'imports': imports}, indent=2)}\n  </script>\n"
    text = MAP_PATTERN.sub("", text)
    return text.replace('  <script type="module"', block + '  <script type="module"')


def stamped_3d_page(text, site=SITE):
    """The same for the 3D page. Its import map also covers the 2D modules it borrows."""
    text = re.sub(r'href="3d/3d\.css[^"]*"', f'href="{versioned("3d/3d.css", site)}"', text)
    text = re.sub(r'src="3d/3d\.js[^"]*"', f'src="{versioned("3d/3d.js", site)}"', text)
    imports = {f"./{folder}/{path.name}": f"./{versioned(f'{folder}/{path.name}', site)}"
               for folder in ("js", "3d") for path in sorted((site / folder).glob("*.js"))}
    block = f"  {MAP_START}\n{json.dumps({'imports': imports}, indent=2)}\n  </script>\n"
    text = MAP_PATTERN.sub("", text)
    return text.replace('  <script type="module"', block + '  <script type="module"')


def stamped_report_page(text, site=SITE):
    """The town reports page (T-154). Its script is a plain script, not a module, so it needs no import map."""
    text = re.sub(r'href="report/report\.css[^"]*"', f'href="{versioned("report/report.css", site)}"', text)
    return re.sub(r'src="report/report\.js[^"]*"', f'src="{versioned("report/report.js", site)}"', text)


if __name__ == "__main__":
    for page, stamp in ((INDEX, stamped_page), (PAGE_3D, stamped_3d_page), (PAGE_REPORT, stamped_report_page)):
        text = page.read_bytes().decode("utf-8").replace("\r\n", "\n")
        new_text = stamp(text)
        # A page that's already up to date isn't rewritten, so its file stays exactly as it is.
        if new_text != text:
            page.write_bytes(new_text.encode("utf-8"))
        print("Stamped" if new_text != text else "Already up to date:", page)
