// Task T-149: the 3D page's own text (F-25). Text the 2D map also shows comes from ../js/strings.js,
// so both pages say the same thing. The wording test in pipeline/tests/test_wording.py reads this file.

export const STRINGS_3D = {
  pageTitle: "Mayon Radar Watch · 3D view",
  viewName: "3D view",
  backTo2d: "← 2D map",
  mapLabel: "3D map of the volcano",
  passList: "Radar pass",
  previous: "Previous pass",
  next: "Next pass",
  retry: "Try again",
  resetView: "Reset view",
  orbit: "Orbit Mayon",
  orbitMap: "Orbit the map", // a site with no volcano, like the Panama test site
  orbitStop: "Stop orbit",
  orbitStepNote: "Each press turns the view a little, because your device asks for less motion.",
  controlsLabel: "View controls",
  noWebgl: "The 3D view needs WebGL, which this browser doesn't have.",
  siteLoadError: "Couldn't load the 3D view. Try again.",
  open2d: "Open the 2D map",
  dragHelp: "Drag to move. Right-drag or use two fingers to tilt and turn.",
  heightNote: "Heights are drawn 1.5 times taller so the slopes are easier to see.",
};
