// Task T-149: the 3D view (F-25, FR-101 to FR-106, SCR-15, ADR-015).
// A separate page that reads the same published files as the 2D map and changes none of them.
// The ground's shape comes from terrain tiles made from the Copernicus DEM (pipeline/mrw/terrain.py),
// and the relief or satellite picture is draped over it, with the radar result on top.

import { loadPair, loadSiteData, loadSites } from "../js/data.js";
import { STRINGS, textFor } from "../js/strings.js";
import { createTimeline, localDate } from "../js/timeline.js";
import { STRINGS_3D } from "./strings-3d.js";

const SATELLITE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg";
const SATELLITE_MAX_ZOOM = 14;
const TERRAIN_MIN_ZOOM = 8; // the same zooms as pipeline/mrw/terrain.py
const TERRAIN_MAX_ZOOM = 12;
const HEIGHT_EXAGGERATION = 1.5; // FR-102: steeper than life, so the slopes read clearly
const START_PITCH = 60; // degrees from looking straight down
const START_BEARING = -20; // turned a little, so the cone's shape shows from the first look
const PHONE_LAYOUT = "(max-width: 700px)";
const ORBIT_DEGREES_PER_SECOND = 6; // one full circle a minute
const ORBIT_STEP_DEGREES = 45; // with reduced motion, one press turns this far, with no animation
const CIRCLE_POINTS = 128;
const BASEMAP_KEY = "mayon-radar-basemap"; // the same key as the 2D map, so the choice carries over

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const byId = (id) => document.getElementById(id);

// FR-106: without WebGL, MapLibre can't draw anything.
function hasWebgl() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function showProblem(text) {
  byId("loading").hidden = true;
  byId("problem-text").textContent = text;
  byId("problem").hidden = false;
  document.body.dataset.state = "problem";
}

// A circle on the ground as a closed line, `radiusKm` around a point. Close to the equator
// a degree of longitude is shorter than one of latitude by the cosine of the latitude.
function circle(lat, lon, radiusKm) {
  const kmPerDegree = 111.32;
  const coordinates = [];
  for (let i = 0; i <= CIRCLE_POINTS; i += 1) {
    const angle = (i / CIRCLE_POINTS) * 2 * Math.PI;
    coordinates.push([
      lon + (radiusKm * Math.sin(angle)) / (kmPerDegree * Math.cos((lat * Math.PI) / 180)),
      lat + (radiusKm * Math.cos(angle)) / kmPerDegree,
    ]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } };
}

function featureCollection(features) {
  return { type: "FeatureCollection", features };
}

// Each channel's checked and not-checked parts, as two separate sets of lines.
// A site with no channel data, like the Panama test site, has none.
function channelParts(channels) {
  const checked = [];
  const notChecked = [];
  for (const channel of channels ? channels.features : []) {
    const { id, name, checked_geometry: solid, not_checked_geometry: dashed } = channel.properties;
    checked.push({ type: "Feature", properties: { id, name }, geometry: solid });
    if (dashed) notChecked.push({ type: "Feature", properties: { id, name }, geometry: dashed });
  }
  return { checked: featureCollection(checked), notChecked: featureCollection(notChecked) };
}

function savedBasemap() {
  try {
    return localStorage.getItem(BASEMAP_KEY) === "satellite" ? "satellite" : "relief";
  } catch {
    return "relief";
  }
}

function saveBasemap(choice) {
  try {
    localStorage.setItem(BASEMAP_KEY, choice);
  } catch {
    // The choice still applies until the page closes.
  }
}

// The map's style: the backgrounds, the terrain and every line, all from this site's own files
// except the satellite imagery. No font server is needed, because names are HTML markers.
function mapStyle(site, channels) {
  const relief = [site.relief_bounds_west, site.relief_bounds_south, site.relief_bounds_east, site.relief_bounds_north];
  const parts = channelParts(channels);
  // The rings need a summit. The Panama test site has none, so it has no rings.
  const rings = [];
  if (site.summit_lat != null && site.detection_reach_km) rings.push({ ...circle(site.summit_lat, site.summit_lon, site.detection_reach_km), properties: { kind: "reach" } });
  if (site.summit_lat != null && site.danger_zone_radius_km) rings.push({ ...circle(site.summit_lat, site.summit_lon, site.danger_zone_radius_km), properties: { kind: "zone" } });
  return {
    version: 8,
    sources: {
      relief: {
        type: "raster", tiles: [`data/sites/${site.id}/relief/{z}/{x}/{y}.webp`], tileSize: 256,
        minzoom: site.min_zoom, maxzoom: site.relief_max_native_zoom, bounds: relief, attribution: STRINGS.reliefCredit,
      },
      satellite: {
        type: "raster", tiles: [SATELLITE_URL], tileSize: 256, maxzoom: SATELLITE_MAX_ZOOM,
        attribution: STRINGS.satelliteCredit,
      },
      terrain: {
        type: "raster-dem", tiles: [`data/sites/${site.id}/terrain/{z}/{x}/{y}.png`], tileSize: 256,
        encoding: "terrarium", minzoom: TERRAIN_MIN_ZOOM, maxzoom: TERRAIN_MAX_ZOOM, bounds: relief,
      },
      // FR-103: only the channels the owner confirmed, from the published file.
      channels: { type: "geojson", data: parts.checked },
      "channels-not-checked": { type: "geojson", data: parts.notChecked },
      rings: { type: "geojson", data: featureCollection(rings) },
    },
    layers: [
      { id: "ground", type: "background", paint: { "background-color": "#cde2ee" } }, // the relief's sea colour
      { id: "relief", type: "raster", source: "relief" },
      { id: "satellite", type: "raster", source: "satellite", layout: { visibility: "none" } },
      // A dark edge under each line keeps it readable on both backgrounds, as on the 2D map.
      { id: "ring-edge", type: "line", source: "rings", paint: { "line-color": "#0f172a", "line-width": 4, "line-opacity": 0.45 } },
      { id: "reach", type: "line", source: "rings", filter: ["==", ["get", "kind"], "reach"], paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [1, 3] } },
      { id: "zone", type: "line", source: "rings", filter: ["==", ["get", "kind"], "zone"], paint: { "line-color": "#fb923c", "line-width": 2.5, "line-dasharray": [3, 3] } },
      { id: "channel-edge", type: "line", source: "channels", paint: { "line-color": "#0f172a", "line-width": 6, "line-opacity": 0.55 } },
      { id: "channel", type: "line", source: "channels", paint: { "line-color": "#22d3ee", "line-width": 3.5 } },
      { id: "not-checked-edge", type: "line", source: "channels-not-checked", paint: { "line-color": "#0f172a", "line-width": 5, "line-opacity": 0.55 } },
      { id: "not-checked", type: "line", source: "channels-not-checked", paint: { "line-color": "#ffffff", "line-width": 2.5, "line-dasharray": [2, 2] } },
    ],
    terrain: { source: "terrain", exaggeration: HEIGHT_EXAGGERATION },
  };
}

// A name on the ground, drawn as page text so it needs no map fonts and screen readers can read it.
function addLabel(map, lngLat, text, className) {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = text; // text from a data file is never read as HTML
  return new maplibregl.Marker({ element, anchor: "center" }).setLngLat(lngLat).addTo(map);
}

function addLabels(map, site, towns, channels) {
  for (const town of towns.features) {
    addLabel(map, [town.properties.label_lon, town.properties.label_lat], town.properties.name, "label-3d town-label-3d");
  }
  for (const channel of channels ? channels.features : []) {
    addLabel(map, [channel.properties.label_lon, channel.properties.label_lat], channel.properties.name, "label-3d channel-label-3d");
  }
  if (!site.danger_zone_label || site.summit_lat == null) return;
  // The danger zone's name sits just outside the ring's southern edge, as on the 2D map.
  const south = site.summit_lat - site.danger_zone_radius_km / 111.32;
  addLabel(map, [site.summit_lon, south], site.danger_zone_label, "label-3d zone-label-3d").setOffset([0, 12]);
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Image failed to load: ${url}`));
    image.src = url;
  });
}

// The label saying which radar products made this pass, and from which dates (FR-084, FR-105).
function productText(pair, site) {
  const products = pair.coherence_used ? STRINGS.productsWithCoherence : STRINGS.productsWithoutCoherence;
  return STRINGS.productLabel(products, localDate(pair.before_acquired_start, site.time_zone),
    localDate(pair.after_acquired_start, site.time_zone));
}

// Show one pass's new-material image, placed by its bounds, draped on the ground.
function pairShower(map, site) {
  return async function showPair(summary, isCurrent) {
    const pair = await loadPair(site.id, summary.id);
    const layer = pair.layers.find((item) => item.kind === "new_material");
    const url = `${pair.folder}/${layer.image_path}`;
    await loadImage(url);
    if (!isCurrent()) return;
    const coordinates = [
      [layer.bounds_west, layer.bounds_north], [layer.bounds_east, layer.bounds_north],
      [layer.bounds_east, layer.bounds_south], [layer.bounds_west, layer.bounds_south],
    ];
    const source = map.getSource("new-material");
    if (source) {
      source.updateImage({ url, coordinates });
    } else {
      map.addSource("new-material", { type: "image", url, coordinates });
      // Under the lines, so the channels and rings stay readable over the marks.
      map.addLayer({ id: "new-material", type: "raster", source: "new-material", paint: { "raster-fade-duration": 0 } }, "ring-edge");
    }
    byId("product-label").textContent = productText(pair, site);
    byId("pair-image-alt").textContent = layer.title;
  };
}

// The middle of the view: the summit where there is one, otherwise the site's own center.
function middle(site) {
  return site.summit_lat != null ? [site.summit_lon, site.summit_lat] : [site.center_lon, site.center_lat];
}

function startCamera(site) {
  const phone = window.matchMedia(PHONE_LAYOUT).matches;
  return {
    center: middle(site),
    zoom: site.default_zoom - (phone ? 1.6 : 0.6),
    pitch: START_PITCH,
    bearing: START_BEARING,
  };
}

// FR-102: Relief or Satellite. The satellite's credit shows whenever its layer is on, in full.
function setUpBasemap(map) {
  const buttons = { relief: byId("basemap-relief"), satellite: byId("basemap-satellite") };
  function show(choice) {
    map.setLayoutProperty("satellite", "visibility", choice === "satellite" ? "visible" : "none");
    document.body.classList.toggle("satellite-on", choice === "satellite");
    for (const [name, button] of Object.entries(buttons)) button.setAttribute("aria-pressed", String(name === choice));
  }
  for (const [choice, button] of Object.entries(buttons)) {
    button.onclick = () => {
      saveBasemap(choice);
      show(choice);
    };
  }
  show(savedBasemap());
}

// FR-104: Reset view and Orbit Mayon. With reduced motion, nothing moves on its own.
function setUpCamera(map, site) {
  const orbitButton = byId("orbit");
  const orbitText = site.summit_lat != null ? STRINGS_3D.orbit : STRINGS_3D.orbitMap;
  orbitButton.textContent = orbitText;
  let frame = null;
  let lastTime = null;

  function stopOrbit() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    lastTime = null;
    orbitButton.setAttribute("aria-pressed", "false");
    orbitButton.textContent = orbitText;
  }

  function turn(time) {
    if (lastTime !== null) {
      const degrees = ((time - lastTime) / 1000) * ORBIT_DEGREES_PER_SECOND;
      map.setBearing(map.getBearing() + degrees);
    }
    lastTime = time;
    frame = requestAnimationFrame(turn);
  }

  orbitButton.onclick = () => {
    const around = { center: middle(site), pitch: Math.max(map.getPitch(), 50) };
    if (reducedMotion.matches) {
      map.jumpTo({ ...around, bearing: map.getBearing() + ORBIT_STEP_DEGREES });
      byId("orbit-note").hidden = false;
      return;
    }
    if (frame !== null) {
      stopOrbit();
      return;
    }
    map.jumpTo(around);
    orbitButton.setAttribute("aria-pressed", "true");
    orbitButton.textContent = STRINGS_3D.orbitStop;
    frame = requestAnimationFrame(turn);
  };

  byId("reset-view").onclick = () => {
    stopOrbit();
    if (reducedMotion.matches) map.jumpTo(startCamera(site));
    else map.easeTo({ ...startCamera(site), duration: 1200 });
  };

  // The visitor taking hold of the map stops the orbit, so it never fights their hand.
  const canvas = map.getCanvasContainer();
  for (const name of ["mousedown", "touchstart", "wheel", "keydown"]) canvas.addEventListener(name, stopOrbit, { passive: true });
  reducedMotion.addEventListener("change", stopOrbit);
}

function fillText() {
  document.title = STRINGS_3D.pageTitle;
  for (const element of document.querySelectorAll("[data-text]")) {
    const key = element.dataset.text;
    element.textContent = STRINGS_3D[key] ?? STRINGS[key];
  }
  for (const element of document.querySelectorAll("[data-label]")) {
    element.setAttribute("aria-label", STRINGS_3D[element.dataset.label] ?? STRINGS[element.dataset.label]);
  }
}

// The site the address names, like the 2D map: Mayon, or the Panama test site at ?site=panama.
function siteFromAddress(sites) {
  const id = new URLSearchParams(location.search).get("site");
  return sites.find((site) => site.id === id) || sites[0];
}

// The site's own disclaimer, test banner and ways back to the 2D map (FR-107, FR-108).
function showSite(site, sites) {
  const isTest = site !== sites[0];
  byId("site-name").textContent = site.name;
  byId("disclaimer-tag").textContent = textFor(site).disclaimerShort;
  byId("test-banner").hidden = !isTest;
  for (const link of document.querySelectorAll(".to-2d")) link.href = isTest ? `./?site=${site.id}` : "./";
}

// A site's boundary credit, as a link when the source asks for one. The text is escaped first.
function boundaryCredit(site) {
  const holder = document.createElement("span");
  holder.textContent = site.boundary_credit;
  return site.boundary_credit_url ? `<a href="${site.boundary_credit_url}">${holder.innerHTML}</a>` : holder.innerHTML;
}

async function start() {
  fillText();
  let sites;
  let site;
  try {
    sites = await loadSites();
    site = siteFromAddress(sites);
    showSite(site, sites);
  } catch (problem) {
    console.error(problem.message);
    showProblem(STRINGS_3D.siteLoadError);
    return;
  }
  if (!hasWebgl()) {
    showProblem(STRINGS_3D.noWebgl);
    return;
  }
  let siteData;
  try {
    siteData = await loadSiteData(site);
  } catch (problem) {
    console.error(problem.message);
    showProblem(STRINGS_3D.siteLoadError);
    return;
  }

  let map;
  try {
    map = new maplibregl.Map({
      container: "map",
      style: mapStyle(site, siteData.channels),
      ...startCamera(site),
      minZoom: site.min_zoom - 1,
      maxZoom: site.max_zoom,
      maxPitch: 75,
      maxBounds: [[site.relief_bounds_west, site.relief_bounds_south], [site.relief_bounds_east, site.relief_bounds_north]],
      attributionControl: false,
    });
  } catch (problem) {
    console.error(problem.message);
    showProblem(STRINGS_3D.noWebgl);
    return;
  }
  window.map3d = map; // lets the browser tests read the map's layers
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  // Every credit in full, never folded, so EOX's stays clearly visible on Satellite (FR-091).
  map.addControl(new maplibregl.AttributionControl({
    compact: false,
    customAttribution: [siteData.channels ? STRINGS.channelCredit : null, boundaryCredit(site)].filter(Boolean),
  }), "bottom-right");
  // The NISAR label, added after the credits so that MapLibre stacks it just above them.
  const productLabel = byId("product-label");
  map.addControl({ onAdd: () => productLabel, onRemove: () => productLabel.remove() }, "bottom-right");
  // A screen reader should hear the map's name, not "canvas".
  map.getCanvas().setAttribute("aria-label", STRINGS_3D.mapLabel);

  await new Promise((resolve) => map.once("load", resolve));
  addLabels(map, site, siteData.towns, siteData.channels);
  setUpBasemap(map);
  setUpCamera(map, site);

  const timeline = {
    list: byId("pair-list"), label: byId("pair-label"), sub: byId("pair-sub"), detail: byId("pair-detail"),
    events: byId("pair-events"), gap: byId("pair-gap"), previous: byId("previous"), next: byId("next"),
    message: byId("pair-message"), retry: byId("retry"),
  };
  await createTimeline(timeline, site, siteData.pairs, siteData.events, () => true, pairShower(map, site));
  byId("loading").hidden = true;
  document.body.dataset.state = "ready";
}

start();
