// Town reports (prototype), in research-paper format.
// Reads report/data/<site>/<town>.json (written by pipeline/mrw/town_reports.py) and builds one A4 paper.
//
// The paper is a list of sections (TEMPLATE below). Each section is a small function, so a section can be
// moved, removed or reused for another site without touching the others. Figures and tables are numbered
// automatically in the order they appear, and the text refers to them by name.
(function () {
  "use strict";

  // ---------- template: the order of the paper ----------
  const TEMPLATE = [
    "title", "basicInfo", "abstract", "introduction", "methods", "results",
    "discussion", "conclusion", "acknowledgement", "dataAvailability", "references", "appendix",
  ];
  // The letterhead, in black. Edit these four lines to re-brand the report.
  const LETTERHEAD = [
    "NASA Space Apps Challenge 2026 · Local Event: Legazpi City",
    "MAYON RADAR WATCH",
    "Dancing with the SARs",
    "Radar change monitoring for the towns around Mayon Volcano",
  ];

  const params = new URLSearchParams(location.search);
  // Only a plain site id: the value goes into links on the page, so anything else falls back to Mayon.
  const SITE = /^[a-z0-9_]+$/.test(params.get("site") || "") ? params.get("site") : "mayon";
  const BASE = `report/data/${SITE}/`;
  // The chosen pass, a pair id like mayon_A111F008_20261019_20261031. Anything else means the newest.
  const PASS = /^[a-z0-9_]+$/i.test(params.get("pass") || "") ? params.get("pass") : null;
  const TZ = "Asia/Manila";
  const root = document.getElementById("report");
  const select = document.getElementById("town-select");
  const passSelect = document.getElementById("pass-select");
  const bundleLink = document.getElementById("bundle-link");

  // ---------- writing helpers (house style from the research-paper guide) ----------
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
  const count = (n) => (n >= 0 && n <= 9 ? WORDS[n] : String(n)); // spell out one to nine
  const km = (v) => `${v.toFixed(1)} km`; // a space between a number and its unit
  const area = (v) => (v === 0 ? "0 km²" : v < 0.01 ? "less than 0.01 km²" : `${v.toFixed(2)} km²`);
  const pct = (v) => `${Math.round(v * 100)}%`; // no space before %
  const day = (iso, opt = {}) => new Date(iso).toLocaleDateString("en-GB", { timeZone: TZ, day: "numeric", month: opt.short ? "short" : "long", year: opt.noYear ? undefined : "numeric" });
  const span = (r) => `${day(r.before, { noYear: true })} to ${day(r.after)}`;
  const utcDay = (iso) => iso.slice(0, 10);
  const plural = (n, one, many) => `${count(n)} ${n === 1 ? one : many}`;
  const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1); // a sentence never starts with a small letter
  const shortSpan = (r) => `${day(r.before, { short: true, noYear: true })} to ${day(r.after, { short: true })}`;

  async function getJSON(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: ${res.status}`);
    return res.json();
  }

  // ---------- figure and table numbering ----------
  const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
  function numbering() {
    const n = { figure: 0, table: 0, section: 0, sub: 0 };
    const ids = {};
    return {
      add(kind, id) { ids[id] = `${kind === "figure" ? "Figure" : "Table"} ${++n[kind]}`; return ids[id]; },
      ref(id) { return ids[id] || "?"; },
      // Main sections get Roman numerals and sub-sections get letters, in the order they appear.
      h2(title) { n.sub = 0; return `<h2><span class="no">${ROMAN[n.section++]}.</span>${title}</h2>`; },
      h3(title) { return `<h3><span class="no">${"abcdefghij"[n.sub++]}.</span> ${title}</h3>`; },
      plain(title) { return `<h2 class="plain">${title}</h2>`; },
    };
  }

  function table(num, id, title, head, rows, note) {
    const label = num.add("table", id);
    return `<div class="table-wrap"><div class="table-caption"><span class="cap-label">${label}.</span><span class="cap-title">${title}</span></div>
      <table><thead><tr>${head.map((h) => `<th class="${h.n ? "n" : ""}">${h.t}</th>`).join("")}</tr></thead>
      <tbody>${rows.join("")}</tbody></table>${note ? `<p class="table-note"><i>Note.</i> ${note}</p>` : ""}</div>`;
  }

  function figure(num, id, inner, caption, cls = "") {
    const label = num.add("figure", id);
    return `<figure class="${cls}">${inner}<figcaption><span class="cap-label">${label}.</span> ${caption}</figcaption></figure>`;
  }

  // A list of names as a sentence: "Basud, Lidong, Mi-isi and Padang".
  const andList = (names) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);
  // The ASF processor version in a granule name, like P05023.
  const processor = (granule) => (granule.match(/_(P\d{5})_/) || [])[1];

  // ---------- facts every section can use ----------
  // FR-118: everything is about the chosen pass. FR-119: what depends on the data is read from it.
  function facts(d, passId) {
    const chosen = d.pairs.find((r) => r.pair_id === passId) || d.pairs[d.pairs.length - 1];
    const chosenDay = utcDay(chosen.after);
    // The passes that ended the same day, on the other track too.
    const latest = d.pairs.filter((r) => utcDay(r.after) === chosenDay);
    // The eruption is the newest event with "eruption" in its name, from the events file.
    const eruptions = d.events.filter((e) => /eruption/i.test(e.name)).map((e) => e.date).sort();
    const eruption = eruptions.length ? eruptions[eruptions.length - 1] : null;
    const afterEruption = (r) => Boolean(eruption) && utcDay(r.after) >= eruption;
    // Quiet passes: earlier 12-day passes on the same track, before the eruption.
    const quiet = d.pairs.filter((r) => r.pair_id !== chosen.pair_id && r.track === chosen.track && r.days <= 12
      && utcDay(r.after) < chosenDay && !afterEruption(r)).map((r) => r.flagged_km2);
    const t = { earlier_count: quiet.length, earlier_min_km2: Math.min(...quiet), earlier_max_km2: Math.max(...quiet) };
    let position = null;
    if (t.earlier_count) position = chosen.flagged_km2 > t.earlier_max_km2 ? "above" : chosen.flagged_km2 < t.earlier_min_km2 ? "below" : "within";
    const kind = d.town_kind === "city" ? "city" : "municipality";
    const versions = [...new Set(chosen.granules.map(processor).filter(Boolean))].sort();
    const isNewest = chosen === d.pairs[d.pairs.length - 1];
    return {
      latest, newest: chosen, chosen, position, kind, trend: t, eruption, isNewest, versions,
      littleChecked: d.checked_share < 0.05,
      first: d.pairs[0],
      last: d.pairs[d.pairs.length - 1],
      tracks: [...new Set(d.pairs.map((r) => r.track))].sort(),
      anyLikely: latest.some((r) => r.coherence_used),
      afterEruption,
      // "The newest passes", or for an older choice "The passes of this report". The dates follow in the sentence.
      passesPhrase: isNewest ? "The newest passes" : "The passes of this report",
      passPhrase: isNewest ? "the newest pass" : "the pass of this report",
      channelCount: d.site_channel_names.length,
    };
  }

  function latestSentence(d, f) {
    return f.latest.map((r) => `${area(r.flagged_km2)} on track ${r.track} (${span(r)})`).join(" and ");
  }

  function trendSentence(d, f) {
    const t = f.trend;
    if (f.littleChecked || !t.earlier_count) return "";
    const range = `${area(t.earlier_min_km2)} to ${area(t.earlier_max_km2)}`;
    const verdict = { within: "within that range, so it is not clearly different from quiet passes", above: "above that range", below: "below that range" }[f.position];
    const before = f.eruption ? ` before ${day(f.eruption, { noYear: true })}` : "";
    return `On the ${count(t.earlier_count)} earlier 12-day passes on track ${f.chosen.track}${before}, the town had ${range} flagged; ${f.passPhrase} on that track is ${verdict}.`;
  }

  // Why this pass is brightness only, or why its two images may differ a little (FR-119).
  function passNotes(f) {
    const notes = [];
    if (!f.chosen.coherence_used) notes.push("This pass is brightness only, because no coherence product was available for it.");
    if (f.versions.length > 1) notes.push(`Its two images come from different ASF processor versions (${andList(f.versions)}), so their calibration may differ slightly.`);
    return notes;
  }

  // ---------- sections ----------
  const SECTIONS = {
    title(d, f) {
      return `<div class="letterhead">${LETTERHEAD.map((t, i) => `<div class="lh-${i + 1}">${esc(t)}</div>`).join("")}</div>
        <p class="doc-title flush">Town Change Report</p>
        <p class="doc-sub flush">Radar-Detected Surface Change near Mayon Volcano: ${esc(d.town_name)}, Albay</p>
        <div class="notice-line">Not an official warning. Follow PHIVOLCS and your LGU.</div>`;
    },

    basicInfo(d, f, num) {
      const rows = [
        ["Town", `${esc(d.town_name)} (${f.kind})`],
        ["Province", "Albay, Philippines"],
        ["PSGC code", esc(d.psgc_code || "not listed")],
        ["Report number", `${esc(d.id)}, version ${esc(d.report_version)} (prototype)`],
        ["Pass reported", `${esc(day(f.chosen.before))} to ${esc(day(f.chosen.after))}, track ${f.chosen.track}`],
        ["Data", "NASA–ISRO NISAR Level-2 GCOV and GUNW (provisional)"],
        ["Prepared by", "Mayon Radar Watch"],
        ["Date prepared", esc(day(d.generated_at))],
      ];
      return `${num.h2("Basic Information")}<div class="basic">${rows.map(([k, v], i) => `<span>${"abcdefghij"[i]}.</span><span>${k}</span><span class="v">${v}</span>`).join("")}</div>`;
    },

    abstract(d, f, num) {
      const ch = d.channels.length
        ? `${cap(plural(d.channels.length, "checked channel runs", "checked channels run"))} through the town (${d.channels.map((c) => esc(c.name)).join(", ")}).`
        : `None of the ${count(f.channelCount)} checked channels runs through the town.`;
      const findings = f.littleChecked
        ? `Only ${pct(d.checked_share)} of ${esc(d.town_name)} lies within the radar check, so the report has little to say about it.`
        : `Of the town's mapped area, ${pct(d.checked_share)} lies within the radar check and ${pct(d.pdz_share)} within the Permanent Danger Zone. ${f.passesPhrase} flagged ${latestSentence(d, f)} inside the town. ${trendSentence(d, f)} ${ch}`;
      const erupted = f.eruption ? `Mayon Volcano erupted on ${day(f.eruption)}, and PHIVOLCS raised it to Alert Level 3. ` : "";
      return `${num.h2("Abstract")}<section class="abstract">
        <p><span class="label">Background.</span> ${erupted}Heavy rain can carry loose deposits in the river channels downstream as lahars.</p>
        <p><span class="label">Objective.</span> To report where NISAR radar flagged possible new surface material inside ${esc(d.town_name)} between consecutive satellite passes.</p>
        <p><span class="label">Data.</span> The study uses ${d.pairs.length} pairs of NISAR Level-2 GCOV images (NASA–ISRO, via the Alaska Satellite Facility) on tracks ${f.tracks.join(" and ")}, with GUNW coherence where available.</p>
        <p><span class="label">Method.</span> A brightness change above ${d.thresholds.brightness_db} dB flags a cell of about 20 m; a coherence loss above ${d.thresholds.coherence_loss} raises it from “possible” to “likely”. Only land within ${d.detection_reach_km} km of the summit is checked.</p>
        <p><span class="label">Findings.</span> ${findings}</p>
        <p><span class="label">Note.</span> The radar products are provisional. This report is not an official warning.</p>
        <p class="keywords"><span class="label">Keywords:</span> NISAR; synthetic aperture radar; change detection; Mayon Volcano; ${esc(d.town_name)}; river channels</p></section>`;
    },

    introduction(d, f, num) {
      const fig = figure(num, "locator", `<img src="${BASE}${esc(d.locator_image)}" alt="Map of the towns around Mayon with ${esc(d.town_name)} shaded">`,
        `Location of ${esc(d.town_name)} (black) among the cities and municipalities around Mayon Volcano. The ring is the ${d.danger_zone_radius_km} km Permanent Danger Zone; the triangle is the summit.`, "locator");
      return `${num.h2("Introduction")}
        ${num.h3("Study area")}
        ${fig}
        <p>${esc(d.town_name)} is a ${f.kind} of Albay, Philippines (PSGC ${esc(d.psgc_code || "not listed")}). Its border comes within ${km(d.nearest_km_to_summit)} of the summit of Mayon Volcano, and its centre lies about ${km(d.centre_km_to_summit)} away (${num.ref("locator")}). Of its ${area(d.area_km2)} inside the app's map area, ${area(d.pdz_km2)} (${pct(d.pdz_share)}) lies within the ${d.danger_zone_radius_km} km Permanent Danger Zone, which the public may not enter.</p>
        ${num.h3("Background")}
        <p>Mayon is the most active volcano in the Philippines. After an eruption, fresh ash, rock and lava rest on its slopes and in the gullies that drain it. PHIVOLCS names the river channels that carry this material and asks communities beside them to stay alert during heavy rain (Philippine Daily Inquirer, 2024). Clouds and ash often hide the slopes from ordinary satellite photographs. Radar does not have this problem: it sends its own microwave signal and sees through cloud, ash and darkness.</p>
        ${num.h3("Objective")}
        <p>This report answers one question for ${esc(d.town_name)}: between consecutive NISAR passes, where did the radar flag possible new surface material, and in which checked channels? It describes change only. It does not assess hazard, and it does not replace advice from PHIVOLCS or the local government.</p>`;
    },

    methods(d, f, num) {
      return `${num.h2("Data and Methods")}
        ${num.h3("Radar data")}
        <p>NISAR is a joint NASA and ISRO satellite with an L-band radar (24 cm wavelength) that images the same place every 12 days (NASA Jet Propulsion Laboratory, n.d.). This report uses its Level-2 GCOV product (radar brightness) and, where available, its GUNW product (interferogram and coherence), both distributed by the Alaska Satellite Facility (Alaska Satellite Facility, n.d.). The products are labelled PROVISIONAL: calibrated, but not yet fully validated.</p>
        ${num.h3("Change detection")}
        <p>Two images from the same track and frame are compared. A cell is flagged when its brightness changed by more than ${d.thresholds.brightness_db} dB. When coherence is available, a flagged cell whose coherence also fell by more than ${d.thresholds.coherence_loss} against the previous pair is marked “likely”; coherence never adds area. Only land within ${d.detection_reach_km} km of the summit is checked. The thresholds were fixed on 1 November 2026, before any image taken after the eruption was opened.</p>
        ${num.h3("Town and channel measures")}
        <p>Town borders come from NAMRIA and PSA via OCHA COD-AB. Flagged cells are counted inside each border on the published grid of about 20 m. Channel lines come from OpenStreetMap and are used only where the project owner checked them against imagery; each channel is measured within a strip ${d.channel_strip_half_width_m * 2} m wide. Distances are measured from the summit (${d.summit.lat}° N, ${d.summit.lon}° E).</p>`;
    },

    results(d, f, num) {
      // Table: key facts
      const factRows = [
        ["Area inside the app's map area", area(d.area_km2)],
        ["Nearest point of the border to the summit", km(d.nearest_km_to_summit)],
        ["Centre of the town to the summit", km(d.centre_km_to_summit)],
        [`Share inside the ${d.danger_zone_radius_km} km Permanent Danger Zone`, `${pct(d.pdz_share)} (${area(d.pdz_km2)})`],
        [`Share inside the radar check (${d.detection_reach_km} km)`, `${pct(d.checked_share)} (${area(d.checked_km2)})`],
        ["Checked channels in the town", d.channels.length ? d.channels.map((c) => esc(c.name)).join(", ") : "None"],
        ...f.latest.map((r) => [`Flagged in the town, ${span(r)} (track ${r.track})`, area(r.flagged_km2)]),
      ].map(([a, b]) => `<tr><td>${a}</td><td class="n">${b}</td></tr>`);
      const t1 = table(num, "facts", `Key measures for ${esc(d.town_name)}`, [{ t: "Measure" }, { t: "Value", n: true }], factRows,
        "Areas are measured inside the app's map area (" + `${d.map_bounds.west}° to ${d.map_bounds.east}° E, ${d.map_bounds.south}° to ${d.map_bounds.north}° N); parts of the town outside it are not counted.`);

      const r = f.newest;
      const fig2 = figure(num, "map", `<img src="${BASE}${esc(r.map_image)}" alt="Map of ${esc(d.town_name)} with flagged cells, checked channels, the Permanent Danger Zone and the edge of the radar check">`,
        `Flagged cells in and around ${esc(d.town_name)}, ${span(r)}, track ${r.track}. Light orange: possible new material (brightness only). Dark orange with a black edge: likely (brightness and coherence agree). Marks are drawn larger than the 20 m cells so they stay visible. Solid ring: Permanent Danger Zone; dashed ring: edge of the radar check. Background: relief from Copernicus DEM GLO-30, produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Borders: NAMRIA and PSA via OCHA COD-AB. Channels: © OpenStreetMap contributors.`, "map");

      const fig3 = figure(num, "chart", `<div class="chart">${chart(d, f)}</div>`,
        `Area flagged inside ${esc(d.town_name)} for every reviewed pass, by the date of the later pass (Manila time). Dark grey: track 111. Light grey: track 104. ${f.eruption ? `Hatched: pairs after the eruption of ${day(f.eruption)}. ` : ""}Outlined: a 24-day gap between passes. The arrow marks the pass of this report.`);

      const passRows = d.pairs.slice().reverse().map((p) => `<tr class="${f.afterEruption(p) ? "after" : ""}"><td>${p.pair_id === f.chosen.pair_id ? "▶ " : ""}${esc(shortSpan(p))}</td><td>${p.track} ${p.orbit_direction === "ascending" ? "asc." : "desc."}</td><td class="n">${p.days}</td><td>${p.coherence_used ? "Yes" : "No"}</td><td class="n">${p.possible_km2.toFixed(3)}</td><td class="n">${p.likely_km2.toFixed(3)}</td><td class="n">${p.flagged_km2.toFixed(3)}</td><td class="n">${p.whole_site_km2.toFixed(2)}</td></tr>`);
      const t2 = table(num, "passes", `Flagged area inside ${esc(d.town_name)}, every reviewed pass (km²)`,
        [{ t: "Passes (Manila dates)" }, { t: "Track" }, { t: "Days", n: true }, { t: "Coherence" }, { t: "Possible", n: true }, { t: "Likely", n: true }, { t: "Town total", n: true }, { t: "Whole map", n: true }],
        passRows, `${f.eruption ? `Bold rows are pairs after the eruption of ${day(f.eruption)}. ` : ""}The row marked ▶ is the pass of this report. “Whole map” is the area flagged across the app's full map, for comparison.`);

      let channelBlock;
      if (d.channels.length) {
        const byPair = Object.fromEntries(d.pairs.map((p) => [p.pair_id, p]));
        const rows = d.channels.map((c) => {
          const mine = d.channel_rows.filter((x) => x.channel_id === c.id && byPair[x.pair_id]);
          const vals = mine.map((x) => x.flagged_km2);
          const newest = mine.filter((x) => f.latest.some((l) => l.pair_id === x.pair_id)).map((x) => `${x.flagged_km2.toFixed(3)} (track ${byPair[x.pair_id].track})`).join("; ");
          return `<tr><td>${esc(c.name)}</td><td class="n">${c.km_inside_town.toFixed(1)}</td><td class="n">${vals.length ? `${Math.min(...vals).toFixed(3)} to ${Math.max(...vals).toFixed(3)}` : "–"}</td><td class="n">${newest || "–"}</td></tr>`;
        });
        const t3 = table(num, "channels", `Checked channels in ${esc(d.town_name)}: flagged area in each channel strip (km²)`,
          [{ t: "Channel" }, { t: "Line inside town (km)", n: true }, { t: "Range, all pairs", n: true }, { t: f.isNewest ? "Newest pairs" : "Pairs of this report", n: true }],
          rows, `Each strip is ${d.channel_strip_half_width_m * 2} m wide and counts the whole channel inside the radar check, not only the part inside the town. Channel names follow PHIVOLCS; see References.`);
        channelBlock = `<p>${cap(plural(d.channels.length, "checked channel runs", "checked channels run"))} through ${esc(d.town_name)} (${num.ref("channels")}).</p>${t3}`;
      } else {
        channelBlock = `<p>None of the ${count(f.channelCount)} channels checked so far (${andList(d.site_channel_names.map(esc))}) runs through ${esc(d.town_name)}. PHIVOLCS names other channels around Mayon, but they have not yet been checked for this app, so this section has no channel table.</p>`;
      }

      const newestText = f.littleChecked
        ? `Because almost all of ${esc(d.town_name)} lies outside the radar check, the flagged areas in ${num.ref("map")} and ${num.ref("passes")} are near zero by design, not because nothing changed.`
        : `${f.passesPhrase} flagged ${latestSentence(d, f)} inside the town (${num.ref("map")}). ${f.anyLikely ? "" : "These pairs are brightness only, because no coherence product was available for them, so every flagged cell is “possible”."}`;

      return `${num.h2("Results")}
        ${num.h3("Town overview")}
        <p>${num.ref("facts")} summarises where ${esc(d.town_name)} lies relative to the volcano and how much of it the radar check covers.</p>${t1}
        ${num.h3(f.isNewest ? "Newest passes" : "Passes of this report")}<p>${newestText}</p>${fig2}
        ${num.h3("Change over time")}
        <p>${num.ref("chart")} and ${num.ref("passes")} give the flagged area inside the town for all ${d.pairs.length} published pairs. ${trendSentence(d, f)}</p>${fig3}${t2}
        ${num.h3("Channels")}${channelBlock}`;
    },

    discussion(d, f, num) {
      let reading;
      if (f.littleChecked) reading = `The radar check reaches only ${pct(d.checked_share)} of ${esc(d.town_name)}, so the results cannot describe change across the town.`;
      else if (f.position === "within") reading = `The flagged area for ${f.passPhrase} in ${esc(d.town_name)} falls within the range of quiet passes. On this evidence alone, the radar does not show a clear change in the town${f.afterEruption(f.chosen) ? " after the eruption" : ""}.${f.chosen.coherence_used ? "" : " Coherence for this pass would help to separate real deposits from background change."}`;
      else if (f.position === "above") reading = `The flagged area for ${f.passPhrase} in ${esc(d.town_name)} is above the range of quiet passes. This is consistent with new material, but it is not proof of it, and it should be compared with field observations.`;
      else if (f.position === "below") reading = `The flagged area for ${f.passPhrase} in ${esc(d.town_name)} is below the range of quiet passes.`;
      else reading = `There are no earlier quiet passes on track ${f.chosen.track} to compare the flagged area for ${f.passPhrase} with.`;
      return `${num.h2("Discussion")}
        ${num.h3("Interpretation")}
        <p>${reading} A flagged cell shows that radar brightness changed; it does not show why. Rain, farming, quarrying and plant growth also change brightness, which is why quiet passes are never at zero.</p>
        ${num.h3("Limitations")}
        <ul>
          <li>The NISAR products are PROVISIONAL, and a flagged cell is never a confirmed deposit.</li>
          ${passNotes(f).map((note) => `<li>${note}</li>`).join("")}
          <li>Areas are counted on a grid of about 20 m, so they differ a little from the 10 m areas shown in the app.</li>
          <li>Only land within ${d.detection_reach_km} km of the summit is checked, and town borders are cut at the edge of the app's map area.</li>
          <li>Only ${count(f.channelCount)} ${f.channelCount === 1 ? "channel has" : "channels have"} been checked by eye so far.</li>
        </ul>`;
    },

    conclusion(d, f, num) {
      const summary = f.littleChecked
        ? `${esc(d.town_name)} lies almost entirely beyond the radar check, so this report cannot describe change there.`
        : `Between ${span(f.newest)}, NISAR flagged ${area(f.newest.flagged_km2)} of possible new material inside ${esc(d.town_name)}. ${f.position === "within" ? "That is within the range of earlier quiet passes." : ""}`;
      return `${num.h2("Conclusion and Public Notice")}
        <p>${summary}${f.chosen.coherence_used ? "" : " Coherence for this pass, where it becomes available, would make the method more informative."}</p>
        <div class="notice"><div class="head">Public Notice</div><ul>
          <li>This report is not an official warning or advisory. PHIVOLCS and your local government issue those.</li>
          <li>It shows where the ground changed between two satellite passes. It does not say where or when a lahar happens.</li>
          <li>Follow PHIVOLCS bulletins and lahar advisories, and the instructions of your MDRRMO, barangay and LGU.</li>
          <li>Never enter the ${d.danger_zone_radius_km} km Permanent Danger Zone. Keep away from river channels during heavy rain.</li>
        </ul></div>`;
    },

    acknowledgement(d, f, num) {
      return `${num.plain("Acknowledgement")}
        <p>The radar data are from the NASA–ISRO NISAR mission, distributed by the Alaska Satellite Facility DAAC. Event dates and channel names are from PHIVOLCS, as cited. Town borders are from NAMRIA and PSA via OCHA; channel lines are from OpenStreetMap contributors; the relief is from the Copernicus programme of the European Union and ESA. This report was prepared for the NASA Space Apps Challenge 2026.</p>`;
    },

    dataAvailability(d, f, num) {
      return `${num.plain("Data Availability")}
        <p>The data behind this report are in <b>${esc(d.bundle)}</b>, which opens in QGIS: the town border, the checked channels near the town and the flagged cells (GeoJSON, EPSG:4326), and every pair (CSV). The radar results are released under CC BY 4.0 (credit: Mayon Radar Watch and NASA–ISRO NISAR data via ASF). Borders are CC BY-IGO and channel lines are ODbL 1.0.</p>`;
    },

    references(d, f, num) {
      const refs = [
        "Alaska Satellite Facility. (n.d.). <i>NISAR data at ASF</i>. https://nisar-docs.asf.alaska.edu/nisar-intro/",
        "European Space Agency. (n.d.). <i>Copernicus DEM GLO-30</i> [Data set]. https://registry.opendata.aws/copernicus-dem/",
        "NASA Jet Propulsion Laboratory. (n.d.). <i>NISAR mission science users' handbook</i>. https://doi.org/10.48577/jpl.UD4HV3",
        "OCHA. (n.d.). <i>Philippines subnational administrative boundaries (COD-AB)</i> [Data set], from NAMRIA and PSA. https://github.com/faeldon/philippines-json-maps",
        "OpenStreetMap contributors. (2026). <i>OpenStreetMap</i> [Data set]. https://www.openstreetmap.org/copyright",
        "Philippine Daily Inquirer. (2024, December 1). <i>Phivolcs warns Albay of possible lahar due to heavy rainfall</i>. https://newsinfo.inquirer.net/2011361/phivolcs-warns-albay-of-possible-lahar-due-to-heavy-rainfall",
        "PHIVOLCS. (2000, March 24). <i>Mayon Volcano bulletin</i>. https://wovodat.phivolcs.dost.gov.ph/cm_image/bulletin/MVBU_20000324070000.pdf",
      ];
      const seen = new Set(refs.map((r) => r.split("https://")[1]));
      const add = (text, url) => { const key = url.split("https://")[1]; if (!seen.has(key)) { seen.add(key); refs.push(`${text} ${url}`); } };
      d.events.forEach((e) => add(`${esc(e.source_name)}. (${esc(e.date.slice(0, 4))}). <i>${esc(e.name)}</i> [News report].`, esc(e.source_url)));
      d.channels.forEach((c) => add(`${esc(c.name_source)}. <i>Channel name: ${esc(c.name)}</i>.`, esc(c.name_source_url)));
      refs.sort((a, b) => a.replace(/<[^>]+>/g, "").localeCompare(b.replace(/<[^>]+>/g, "")));
      return `${num.plain("References")}<div class="refs">${refs.map((r) => `<p>${r}</p>`).join("")}</div>`;
    },

    appendix(d, f, num) {
      const pairs = f.latest.map((r) => esc(r.pair_id)).join("<br>");
      return `<section class="appendix">
        ${num.plain("Appendix A. Product Information")}
        <table><tbody>
          <tr><td>Report</td><td>${esc(d.id)}, version ${esc(d.report_version)} (prototype), generated ${esc(d.generated_at)}</td></tr>
          <tr><td>Pairs in this report</td><td>${pairs}</td></tr>
          <tr><td>Granules used for the map</td><td class="mono">${f.chosen.granules.map(esc).join("<br>")}</td></tr>
          <tr><td>Data sheet reviewed</td><td>${esc(f.chosen.reviewed_by)}, ${esc(f.chosen.reviewed_at)}</td></tr>
          <tr><td>Thresholds</td><td>Brightness ${d.thresholds.brightness_db} dB; coherence loss ${d.thresholds.coherence_loss} when coherence is available</td></tr>
          <tr><td>Coordinate system</td><td>WGS 84 (EPSG:4326)</td></tr>
        </tbody></table>
        <p class="flush"><b>Suggested citation.</b> Mayon Radar Watch. (2026). <i>Radar-detected surface change near Mayon Volcano: ${esc(d.town_name)}, Albay</i> (Report ${esc(d.id)}, Version ${esc(d.report_version)}). Contains NASA–ISRO NISAR data via ASF (provisional). CC BY 4.0.</p>
        ${num.plain("Appendix B. Buod sa Filipino")}
        <p>Ipinapakita ng ulat na ito kung saan nakakita ang radar ng NISAR ng posibleng bagong materyal (abo, bato o lava) sa ${esc(d.town_name)}. ${f.isNewest ? "Sa pinakabagong pagdaan ng satellite" : `Sa pagdaan ng satellite na natapos noong ${day(f.chosen.after)}`}, humigit-kumulang ${f.newest.flagged_km2.toFixed(2)} km² ang na-flag sa loob ng bayan. Hindi ito opisyal na babala. Sundin ang PHIVOLCS at ang inyong LGU, at huwag pumasok sa ${d.danger_zone_radius_km} km na Permanent Danger Zone.</p>
      </section>`;
    },
  };

  // ---------- figure: grayscale bar chart, drawn as SVG ----------
  function chart(d, f) {
    const rows = d.pairs;
    const W = 640, H = 190, L = 46, B = 36, T = 12;
    const max = Math.max(0.05, ...rows.map((r) => r.flagged_km2)) * 1.12;
    const bw = (W - L - 6) / rows.length;
    const y = (v) => T + (H - T - B) * (1 - v / max);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart of flagged area inside the town for every pair" font-family="EB Garamond, Garamond, serif">
      <defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#fff"/><line x1="0" y1="0" x2="0" y2="5" stroke="#000" stroke-width="2"/></pattern></defs>`;
    for (let i = 0; i <= 4; i++) {
      const v = (max / 4) * i;
      s += `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#d0d0d0" stroke-width="0.6"/><text x="${L - 5}" y="${y(v) + 3}" font-size="9" text-anchor="end">${v.toFixed(2)}</text>`;
    }
    rows.forEach((r, i) => {
      const x = L + i * bw + 3;
      const w = bw - 6;
      const h = y(0) - y(r.flagged_km2);
      let style = `fill="${r.track === 104 ? "#b5b5b5" : "#4a4a4a"}"`;
      if (f.afterEruption(r)) style = `fill="url(#hatch)" stroke="#000" stroke-width="0.8"`;
      else if (r.days > 12) style = `fill="#fff" stroke="#000" stroke-width="0.8" stroke-dasharray="3 2"`;
      s += `<rect x="${x}" y="${y(r.flagged_km2)}" width="${w}" height="${Math.max(h, 0.5)}" ${style}/>`;
      // The pass of this report gets a small arrow above its bar, so it shows in black and white.
      if (r.pair_id === f.chosen.pair_id) s += `<text class="chosen-mark" x="${x + w / 2}" y="${y(r.flagged_km2) - 3}" font-size="9" text-anchor="middle">▼</text>`;
      s += `<text x="${x + w / 2}" y="${H - B + 13}" font-size="8.5" text-anchor="middle">${esc(day(r.after, { short: true, noYear: true }))}</text>`;
      s += `<text x="${x + w / 2}" y="${H - B + 24}" font-size="7.5" text-anchor="middle" fill="#555">T${r.track}</text>`;
    });
    s += `<line x1="${L}" x2="${W}" y1="${y(0)}" y2="${y(0)}" stroke="#000" stroke-width="0.8"/>`;
    s += `<text x="10" y="${(H - B) / 2}" font-size="9" transform="rotate(-90 10 ${(H - B) / 2})" text-anchor="middle">Flagged area (km²)</text></svg>`;
    return s;
  }

  // ---------- page furniture for print: running head and page numbers ----------
  function pageStyle(d) {
    const head = `Mayon Radar Watch · ${d.town_name} Town Change Report`.replace(/"/g, "'");
    let el = document.getElementById("page-style");
    if (!el) { el = document.createElement("style"); el.id = "page-style"; document.head.appendChild(el); }
    el.textContent = `@page {
      @top-left { content: "${head}"; font: 9pt "EB Garamond", Garamond, serif; color: #555; }
      @top-right { content: "Not an official warning"; font: 9pt "EB Garamond", Garamond, serif; color: #555; }
      @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 9pt "EB Garamond", Garamond, serif; }
      @bottom-left { content: "Report ${d.id} · v${d.report_version} (prototype)"; font: 9pt "EB Garamond", Garamond, serif; color: #555; }
    }
    @page :first { @top-left { content: none; } @top-right { content: none; } }`;
  }

  async function showTown(id, passId) {
    const d = (await getJSON(`${BASE}${id}.json`)).data;
    const f = facts(d, passId);
    const num = numbering();
    const html = TEMPLATE.map((key) => SECTIONS[key](d, f, num)).join("\n");
    root.innerHTML = `<article class="paper">${html}</article>`;
    pageStyle(d);
    bundleLink.href = BASE + d.bundle;
    bundleLink.hidden = false;
    document.title = `MayonRadarWatch_${d.town_name.replace(/\s+/g, "")}_TownReport_${utcDay(f.chosen.after)}`;
  }

  function letterhead() {
    return `<div class="letterhead">${LETTERHEAD.map((t, i) => `<div class="lh-${i + 1}">${esc(t)}</div>`).join("")}</div>`;
  }

  function showList(index, pass) {
    const rows = index.data.map((t) => `<tr><td><a href="?${new URLSearchParams({ site: SITE, town: t.town_id, pass: pass.pair_id })}">${esc(t.town_name)}</a></td><td>${esc(t.town_kind)}</td>
      <td class="n">${t.nearest_km_to_summit.toFixed(1)}</td><td class="n">${pct(t.checked_share)}</td><td class="n">${t.flagged_by_pass[pass.pair_id].toFixed(3)}</td><td>${esc(t.channel_names.join(", ") || "None")}</td></tr>`).join("");
    root.innerHTML = `<article class="paper list">${letterhead()}<p class="doc-title flush">Town Change Reports</p>
      <p class="flush">One report per city or municipality near Mayon Volcano, sorted by distance to the summit, for the pass ${esc(span(pass))} on track ${pass.track}. Not an official warning; follow PHIVOLCS and your LGU.</p>
      <table><thead><tr><th>Town</th><th>Kind</th><th class="n">Km to summit</th><th class="n">Radar check</th><th class="n">This pass (km²)</th><th>Checked channels</th></tr></thead><tbody>${rows}</tbody></table></article>`;
    bundleLink.hidden = true;
  }

  // Until the owner approves a pass's data sheet, there is nothing to report (FR-117).
  function showNoPass() {
    root.innerHTML = `<article class="paper list">${letterhead()}<p class="doc-title flush">Town Change Reports</p>
      <p class="flush">No pass has been reviewed for the town reports yet. Not an official warning; follow PHIVOLCS and your LGU.</p></article>`;
    bundleLink.hidden = true;
  }

  // Go to another town or pass, keeping the other choice.
  function go(town, passId) {
    const q = new URLSearchParams({ site: SITE });
    if (town) q.set("town", town);
    if (passId) q.set("pass", passId);
    location.search = q.toString();
  }

  async function start() {
    try {
      const index = await getJSON(`${BASE}index.json`);
      // FR-118: only approved passes, newest first. The page opens on the newest.
      const passes = index.meta.passes.slice().sort((a, b) => b.after.localeCompare(a.after) || b.track - a.track);
      select.innerHTML = `<option value="">All towns</option>` + index.data.map((t) => `<option value="${esc(t.town_id)}">${esc(t.town_name)}</option>`).join("");
      // T-163: the passes are grouped by the month of the later pass (Manila time), newest month first,
      // so a long list stays easy to scan. The newest pass and any gap longer than 12 days are labelled.
      const monthOf = (p) => new Date(p.after).toLocaleDateString("en-GB", { timeZone: TZ, month: "long", year: "numeric" });
      const months = [];
      passes.forEach((p, i) => {
        const name = monthOf(p);
        if (!months.length || months[months.length - 1].name !== name) months.push({ name, options: [] });
        const notes = [i === 0 ? "newest" : "", p.days > 12 ? `${p.days}-day gap` : ""].filter(Boolean);
        months[months.length - 1].options.push(`<option value="${esc(p.pair_id)}">${esc(shortSpan(p))} · track ${p.track}${notes.length ? ` (${notes.join(", ")})` : ""}</option>`);
      });
      passSelect.innerHTML = months.map((m) => `<optgroup label="${esc(m.name)}">${m.options.join("")}</optgroup>`).join("");
      const id = /^[a-z0-9_]+$/.test(params.get("town") || "") ? params.get("town") : "";
      select.value = id;
      if (!passes.length) {
        passSelect.disabled = true;
        showNoPass();
        return;
      }
      const pass = passes.find((p) => p.pair_id === PASS) || passes[0];
      passSelect.value = pass.pair_id;
      select.addEventListener("change", () => go(select.value, passSelect.value));
      passSelect.addEventListener("change", () => go(select.value, passSelect.value));
      if (id) await showTown(id, pass.pair_id); else showList(index, pass);
    } catch (err) {
      root.innerHTML = `<p class="loading">Couldn't load the town reports. Try again.</p>`;
      console.error(err);
    }
  }

  document.getElementById("print-button").addEventListener("click", () => window.print());
  start();
})();
