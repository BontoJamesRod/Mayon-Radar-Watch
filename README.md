# Mayon Radar Watch

A web app that watches how Mayon Volcano's river channels change between NISAR radar satellite passes. It compares radar images from the same track, usually 12 days apart, and maps where fresh ash, rock and lava may have landed. A channel timeline ranks the channels that the owner has confirmed by how much changed since the last pass. Two pairs in Panama show the same engine on another continent. Built for the NASA Space Apps Challenge 2026, "Dancing with the SARs".

**This is not an official warning service. Follow PHIVOLCS and your LGU.**

## How it works

A Python pipeline compares two NISAR passes from the same track, 12 days or more apart. It uses two signals:

- **Brightness change:** how much the ground's radar reflection changed, in dB (from GCOV products).
- **Coherence loss:** how much less alike the two passes are than the previous two (from GUNW products).

Brightness change alone flags a spot. Coherence loss only raises a flagged spot to high confidence, and it never adds area. The pipeline writes small files into `site/data/`, and the website reads them in the visitor's browser. There is no server.

The detection thresholds are final, and were set before any post-eruption pass was opened. The NISAR products are still PROVISIONAL.

## What's on the site

- **The map** (`index.html`): the flagged spots for each pass, the checked channels, the 6 km Permanent Danger Zone and the channel timeline.
- **The 3D view** (`3d.html`): the same layers draped over the terrain, with a pass selector, Reset view and Orbit Mayon. Mayon and the Panama test site both have one.
- **Town reports** (`report.html`, Mayon only): one printable report per city or municipality near Mayon, for a pass the reader picks, grouped by month. Each has **Save as PDF** and **Download data (ZIP)**.

The town reports are written by code from fixed templates, not by AI, so the same data always gives the same report. A person reviews each pass's numbers before any report shows them.

Channel lines come from OpenStreetMap, © OpenStreetMap contributors. The project owner checked them by eye, and only those lines are used (`pipeline/reports/owner-checks.md`). `channels.geojson` and `channel_areas.json` under `site/data/sites/mayon/` are available under the [ODbL](https://opendatacommons.org/licenses/odbl/).

## Folders

| Folder | What's in it |
| --- | --- |
| `pipeline/mrw/` | Python code that downloads and processes NISAR data |
| `pipeline/sites/` | One settings file per site |
| `pipeline/context/` | Source files for boundaries, events and validation sheets |
| `pipeline/reports/` | Scripts and results behind the thresholds and the channel checks |
| `pipeline/tests/` | Unit and browser tests |
| `site/` | The public website, deployed to GitHub Pages |

These folders are made on your computer and never committed: `raw/` (cropped NISAR data), `pipeline/out/` (processed pairs and draft town sheets) and `pipeline/logs/`.

## Setup on Windows

1. Create a virtual environment: `py -3.12 -m venv .venv`
2. Activate it: `.venv\Scripts\Activate.ps1`
3. Install packages: `pip install -r pipeline/requirements.txt`
4. Run the tests: `pytest`
5. Check NISAR access: `python pipeline/mrw/check_access.py`

Step 5 asks for your NASA Earthdata login the first time and saves it in your home folder, never in this project.

## Run the site

```powershell
python -m http.server 8000 --directory site
```

Then open <http://localhost:8000>.

## Run the pipeline

```powershell
# Rebuild towns, land, events and sources for a site
python pipeline/mrw/context.py mayon

# Process one pair into pipeline/out/, using the names of its two GCOV products
python pipeline/mrw/export.py mayon <before GCOV granule> <after GCOV granule>

# Copy a checked pair into site/data/
python pipeline/mrw/publish.py mayon <pair id>

# Write a validation sheet to pipeline/out/validation_drafts/, or publish it once reviewed
python pipeline/mrw/validation.py mayon <pair id>
python pipeline/mrw/validation.py mayon <pair id> --publish

# Check everything in site/data/ against the data contract
python pipeline/mrw/contract_check.py
```

Publishing only changes files on your computer. A pair reaches the public site when `main` is pushed and CI passes.

The pipeline refuses every product acquired on or after `BLIND_CUTOFF` in `pipeline/mrw/search.py`. It kept the eruption data closed until the final thresholds were set, so the thresholds couldn't be influenced by it. Only the owner moves it.

### Town reports: draft, review, approve

After publishing a pair, make the town reports for it. Nothing reaches the public reports until a named person approves it.

```powershell
# 1. Draft a data sheet and 12 town maps for every pass not yet approved (private, in pipeline/out/town_sheets/)
python pipeline/mrw/town_reports.py mayon

# 2. Review each pass: open its sheet.csv and the maps in pipeline/out/town_sheets/mayon/<pair id>/

# 3. Approve a pass, or all of them, with your real name (it is printed on the reports)
python pipeline/mrw/town_reports.py mayon --approve <pair id> --by "Your full name"
python pipeline/mrw/town_reports.py mayon --approve all --by "Your full name"
```

Then run `pytest`, commit `site/report/data/mayon/` and push. The script refuses an empty name or the example "Your name". If a pair is republished later, for example with coherence, its old approval stops counting and the new draft must be reviewed again. `pipeline/RUNBOOK-eruption.md` has the full steps for a new pass.

## Team

- James Rod B. Bonto (team owner)
- Ivan Mathew C. Esclanda
- Lloyd Ariel Bajada Deputo
- Andrel Jade Cabria
- Julius Dave Fajardo
- Hugh Benedict O. Abante

## Apps and tools used

| What for | Apps and tools |
| --- | --- |
| Writing the code | Visual Studio Code, Python 3.12, PowerShell on Windows |
| Code hosting and the live site | Git, GitHub, GitHub Actions, GitHub Pages |
| The map and the 3D view | Leaflet, MapLibre GL JS |
| Processing the data | NumPy, SciPy, xarray, h5py, rasterio, Shapely, pyproj, Pillow, Matplotlib |
| Finding the radar data | ASF (asf_search), NASA Earthdata (earthaccess) |
| Checking the channel lines | Google Earth Pro, OpenStreetMap |
| Testing | pytest, Playwright with Chromium, axe-core |
| Fonts | IBM Plex Sans, EB Garamond (through Fontsource) |

## AI tools used

All by Anthropic.

- **Apps:** Claude Code (VS Code extension), Claude Cowork, Claude.ai and Claude Desktop
- **Models:** Claude Opus 5.5 and Claude Fable 5.2

The town reports and the detection itself use no AI: they run on fixed rules and templates in the code.

## License and credits

The code and documentation are under the [Apache-2.0 license](LICENSE), with the copyright notice in [NOTICE](NOTICE). The published radar layers in `site/data/sites/mayon/pairs/` are under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), and those in `site/data/sites/panama/pairs/` are under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Credit them to Mayon Radar Watch and NASA–ISRO NISAR data via ASF, adding geoBoundaries for Panama. Data files under their own licenses, such as ODbL and CC BY-SA 4.0, aren't covered by the code license. [CREDITS.md](CREDITS.md) lists every data source, library and tool with its license, and says which files fall under which terms.

## Data sources

- **Radar:** NISAR data, NASA–ISRO, distributed by the Alaska Satellite Facility (ASF DAAC). Products are labeled provisional.
- **Town borders and land:** Mayon: NAMRIA and PSA via OCHA COD-AB, packaged by [faeldon/philippines-json-maps](https://github.com/faeldon/philippines-json-maps), CC BY-IGO. Panama: [geoBoundaries](https://www.geoboundaries.org/), CC BY-SA 4.0.
- **Background map:** a relief made from Copernicus DEM GLO-30, or EOxCloudless Sentinel-2 imagery (CC BY-NC-SA 4.0, non-commercial).
- **Map libraries:** [Leaflet](https://leafletjs.com/) 1.9.4 for the map, and [MapLibre GL JS](https://maplibre.org/) 4.7.1 for the 3D view, both copied into `site/vendor/`. The 3D terrain tiles are made from Copernicus DEM GLO-30.
- **Events:** PHIVOLCS, through the news reports linked in `pipeline/context/mayon_events.json`.
