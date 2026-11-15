# Runbook: adding new passes

Run every command in PowerShell from the project folder, after `.venv\Scripts\Activate.ps1`.

**Before you start:** the final thresholds are locked. `BLIND_CUTOFF` in `pipeline/mrw/search.py` sets the last day of passes the pipeline may open. Don't move it unless the owner says so.

Each new pair compares the newest pass on a track with the one 12 days before it: about 10:16 UTC on track 104 (descending) and 21:13 UTC on track 111 (ascending). ASF may take days to list a pass, and its GUNW (coherence) can come later than its GCOV (brightness).

## 1. Check for new passes

This reads product names only.

```powershell
python pipeline/mrw/eruption_run.py check
```

- **"no new pass on ASF yet":** stop and try again later.
- **"NO COHERENCE YET":** wait for the GUNW. Processing now would give a brightness-only result.

## 2. Process

```powershell
python pipeline/mrw/eruption_run.py process
python pipeline/mrw/contract_check.py pipeline/out --unpublished
```

The contract check here reads only the pair folders, so other files under `pipeline/out/` can't block it. The download budget in `download.py` counts every byte logged in `raw/`, up to 20 GB. Each pair should need under 0.2 GB.

## 3. Review the numbers

Name the pairs from step 2, one or both. This reads names from ASF and the cached crops, and downloads nothing.

```powershell
python pipeline/mrw/eruption_run.py review <pair id> <pair id>
```

It prints each pair's far-field coherence change, flagged area beyond 8 km, no-data share and where its change is, next to the published pairs. It says HOLD or LOOK CLOSER where the rule below applies, and exits with code 1 only on a hold. With two pairs, it also says how much the tracks agree.

## 4. Preview

This copies the site to `pipeline/out/preview/`, publishes the pairs into the copy, and serves it on this computer only. Nothing changes in `site/`.

```powershell
python pipeline/mrw/eruption_run.py preview <pair id> <pair id>
```

Open <http://127.0.0.1:8001/>, and press Ctrl+C when finished. Look for reasons (d) and (e) below, on both pairs.

## 5. Apply the rule, and ask the owner

The owner set this rule before any post-eruption product was opened.

**Hold a pair (don't publish it) automatically if any of these is true:**

- **(a)** a product isn't PROVISIONAL or better;
- **(d)** large no-data gaps cover the volcano. `review` calls more than 5% of the land within the danger zone large, and a person also looks at the map;
- **(e)** the map shows stripe or edge patterns. Only a person can check this.

**Look closer if either far-field check is out of range. Neither holds a pair by itself:**

- **(b)** the median coherence change of land more than 8 km from the summit, where an eruption shouldn't reach, falls outside the range of the same measure on the published pairs that used coherence;
- **(c)** the flagged area beyond 8 km from the summit is above the highest of the published 12-day pairs. Longer pairs are left out.

**To look closer:** `review` prints this pair's flagged share inside 6 km, beyond 8 km and in the channels' strips, next to the published pairs and to what change spread evenly would give. If the change is concentrated near the volcano and its channels compared with the quiet pairs, publish. If it's spread evenly across the whole scene, hold.

**A large area alone is NOT a reason to hold.**

**Two tracks or one:** when both tracks have a pair, `review` reports how much they agree, next to the quiet pairs' 17–21% within about 200 m. This supports a decision and never blocks one. If only one track is ready, publish it with the single-track note in step 6.

The reference numbers are saved in `pipeline/reports/hold-check-baseline.json`. Don't rebuild that file after opening a post-eruption product.

Report the numbers and the preview to the owner. **Publish only with the owner's approval.** A held pair stays in `pipeline/out/`.

## 6. Publish

```powershell
python pipeline/mrw/publish.py mayon <pair id>
python pipeline/mrw/contract_check.py site/data
pytest
```

With only one track ready, add `--single-track` to its publish command. When the other track arrives, publish the first pair again without the option, so that its note goes away.

Each publish undoes itself if the contract check fails. The newest pair becomes the one the site opens on. The tests read the latest pair from the data, so they need no edits.

### Then the town reports: draft, review, approve

After publishing any new pair, make its draft data sheet. The script reads only the published files in `site/data`, and never a NISAR product.

```powershell
python pipeline/mrw/town_reports.py mayon
```

It lists the passes waiting for review. For each one, open `pipeline/out/town_sheets/mayon/<pair id>/`:

- `sheet.csv`: one row per town. Check the flagged areas look sensible next to the earlier passes, that towns far from the volcano are near 0, and that no row is missing.
- The 12 `*_map.jpg`: check the marks sit where the map shows change, with no stripes or gaps.

If it looks right, approve it with your real name. Only the owner approves:

```powershell
python pipeline/mrw/town_reports.py mayon --approve <pair id> --by "Your full name"
pytest pipeline/tests/test_town_reports.py pipeline/tests/e2e/test_reports.py
```

Approval is refused if the draft no longer matches the published data; run the first command again and review the new draft. Until a pass is approved, the reports keep showing the last approved pass. Commit `site/report/data/mayon/` in step 7. Drafts in `pipeline/out/` are never committed.

## 7. Push and merge

Only with the owner's go-ahead. Never force-push. Work on a branch, and check first that no radar files are staged.

```powershell
git switch -c new-passes
git add site/data site/report/data/mayon
git status --short
git commit -m "Publish the new passes"
git push -u origin new-passes
```

Wait for CI on the branch to pass on the repository's Actions page, then:

```powershell
git switch main
git pull --ff-only origin main
git merge --no-ff new-passes -m "Merge new-passes"
git push origin main
```

## 8. Check the live site

Wait for "Deploy site" to pass, then open the site with a hard reload (Ctrl+Shift+R), on a computer and a phone:

- [ ] It opens on the newest pair, with the right dates and track, and the label on the map agrees.
- [ ] The dotted 10 km ring and the danger zone show, and the 10 km limit is stated.
- [ ] Compare opens without the map moving, and town labels stay still while dragging.
- [ ] Older pairs still open.
- [ ] The town reports list the new pass after its approval.
- [ ] The browser console shows no errors.

## Practise with a drill

A drill runs steps 2 to 4 on an older pair, from cached data only, in `pipeline/out/drill/`. It refuses any pair from the eruption onward, and it publishes nothing.

```powershell
python pipeline/mrw/eruption_run.py process --drill <older pair id>
python pipeline/mrw/contract_check.py pipeline/out/drill --unpublished
python pipeline/mrw/eruption_run.py review --drill <older pair id>
python pipeline/mrw/eruption_run.py preview --drill <older pair id>
```

## If something goes wrong

- **A bad pair went live:** remove its folder from `site/data/sites/mayon/pairs/`, rebuild the list, and push a new commit. Don't rewrite history. To rebuild the list:

  ```powershell
  python -c "import sys; sys.path.insert(0, 'pipeline'); from pathlib import Path; from mrw.config import utc_now_text; from mrw.publish import rebuild_pairs_list; rebuild_pairs_list(Path('site/data/sites/mayon'), utc_now_text())"
  ```

- **The script says "Stopped":** the thresholds aren't FINAL or the cutoff has been moved back. It stops before contacting ASF. Ask the owner.
- **"This crop isn't in raw/":** `review` and a drill never download. Run step 2 first, or pick a pair that has been processed.
- **Earthdata login fails:** don't open or print `~/.netrc` or `~/_netrc`. Stop, and have the owner log in again with `python pipeline/mrw/check_access.py`.
