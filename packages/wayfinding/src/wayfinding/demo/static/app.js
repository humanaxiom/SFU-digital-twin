"use strict";

const facilitySelect = document.querySelector("#facility-select");
const levelSelect = document.querySelector("#level-select");
const floorMap = document.querySelector("#floor-map");
const svgNamespace = floorMap.namespaceURI;
const mapStatus = document.querySelector("#map-status");
const roomList = document.querySelector("#room-list");
const unitDetails = document.querySelector("#unit-details");
const assistantForm = document.querySelector("#assistant-form");
const assistantInput = document.querySelector("#assistant-input");
const assistantResponse = document.querySelector("#assistant-response");
const assistantEvidence = document.querySelector("#assistant-evidence");
const artifactHash = document.querySelector("#artifact-hash");
const graphHash = document.querySelector("#graph-hash");
const routeForm = document.querySelector("#route-form");
const routeOrigin = document.querySelector("#route-origin");
const routeDestination = document.querySelector("#route-destination");
const routeProfile = document.querySelector("#route-profile");
const routeStatus = document.querySelector("#route-status");
const routeSteps = document.querySelector("#route-steps");
const routeAccessibility = document.querySelector("#route-accessibility");
const routeClear = document.querySelector("#route-clear");
const routeSwap = document.querySelector("#route-swap");
const floorJourney = document.querySelector("#floor-journey");
const viewingFloor = document.querySelector("#viewing-floor");
const currentInstruction = document.querySelector("#current-instruction");
const stepPosition = document.querySelector("#step-position");
const stepPrevious = document.querySelector("#step-previous");
const stepNext = document.querySelector("#step-next");
const floorPreview = document.querySelector("#floor-preview");
const previewMessage = document.querySelector("#preview-message");
const transitionViews = document.querySelector("#transition-views");
const transitionDeparture = document.querySelector("#transition-departure");
const transitionArrival = document.querySelector("#transition-arrival");
const routeDiagnostics = document.querySelector("#route-diagnostics");
const routeOptionsStatus = document.querySelector("#route-options-status");
const reachableDestinations = document.querySelector("#reachable-destinations");
const unavailableGuidanceMessage = "A directions preview is unavailable for this route. See route details for the data checks.";
let facilitiesById = new Map();
let levelsByOrder = new Map();
let allLevels = [];
let routeUnits = [];
let activeRoute = null;
let activeStep = 0;
let routeSelection = "empty";
let requestGeneration = 0;
let sceneGeneration = 0;
let currentScene = null;
let manualPreview = false;
let previewVisitId = null;
let mapFit = "floor";
let mapOrigin = [0, 0];
let availabilityGeneration = 0;
let routeUiState = "empty";

function element(name, attributes = {}) {
  const node = document.createElementNS(svgNamespace, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || body.code || "The artifact request failed.");
    error.payload = body;
    throw error;
  }
  return body;
}

function coordinates(geometry) {
  const points = [];
  function visit(value) {
    if (Array.isArray(value) && value.length >= 2 && typeof value[0] === "number") {
      points.push(value);
    } else if (Array.isArray(value)) {
      value.forEach(visit);
    }
  }
  if (geometry) visit(geometry.coordinates);
  return points;
}

function pathData(geometry) {
  if (!geometry) return "";
  const drawLine = (line, close) => line.map((point, index) => `${index ? "L" : "M"}${point[0] - mapOrigin[0]} ${-(point[1] - mapOrigin[1])}`).join(" ") + (close ? " Z" : "");
  if (geometry.type === "Polygon") return geometry.coordinates.map((ring) => drawLine(ring, true)).join(" ");
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => drawLine(ring, true))).join(" ");
  if (geometry.type === "LineString") return drawLine(geometry.coordinates, false);
  if (geometry.type === "MultiLineString") return geometry.coordinates.map((line) => drawLine(line, false)).join(" ");
  return "";
}

function svgPath(record, className) {
  const node = element("path", { d: pathData(record.geometry), class: className });
  return node;
}

function setStatus(message) {
  mapStatus.textContent = message;
}

async function selectUnit(unitId, focusMap = false) {
  const body = await request(`/demo/v1/units/${encodeURIComponent(unitId)}`);
  document.querySelectorAll(".unit-shape").forEach((node) => node.classList.toggle("selected", node.dataset.unitId === unitId));
  const rows = [
    ["Room", body.room_id || "Not assigned"],
    ["Category", body.category || "Not recorded"],
    ["Use type", body.use_type || "Not recorded"],
    ["Destination tag", body.accessible === null ? "Unknown" : String(body.accessible)],
    ["Verified by", body.verified_by || "Not recorded"],
    ["Verified date", body.verified_date || "Not recorded"],
  ];
  unitDetails.replaceChildren(...rows.map(([term, value]) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    const detail = document.createElement("dd");
    label.textContent = term;
    detail.textContent = value;
    row.append(label, detail);
    return row;
  }));
  setStatus(`Selected room ${body.room_id || body.unit_id}. Destination metadata does not describe path accessibility.`);
  if (focusMap) document.querySelector(`[data-unit-id="${CSS.escape(unitId)}"]`)?.focus();
}

function updateEndpointStates() {
  document.querySelectorAll("[data-unit-id]").forEach((node) => {
    const isOrigin = node.dataset.unitId === routeOrigin.value;
    const isDestination = node.dataset.unitId === routeDestination.value;
    node.classList.toggle("route-origin", isOrigin);
    node.classList.toggle("route-destination", isDestination);
    if (isOrigin) node.setAttribute("aria-current", "Origin A selected");
    else if (isDestination) node.setAttribute("aria-current", "Destination B selected");
    else node.removeAttribute("aria-current");
  });
}

function clearRoute(clearEndpoints = true) {
  requestGeneration += 1;
  sceneGeneration += 1;
  activeRoute = null;
  activeStep = 0;
  manualPreview = false;
  previewVisitId = null;
  routeAccessibility.hidden = true;
  routeSteps.replaceChildren();
  floorJourney.replaceChildren();
  routeDiagnostics.textContent = "No route requested.";
  setRouteState("empty");
  routeStatus.textContent = "Choose two rooms, or select them on the map.";
  updateGuidanceControls();
  restoreRenderedFloor();
  renderRouteOverlay(activeLevel()?.level_id);
  if (clearEndpoints) {
    routeOrigin.value = "";
    routeDestination.value = "";
    routeSelection = "empty";
    availabilityGeneration += 1;
    renderDestinationOptions();
    setAvailabilityState("empty");
    routeOptionsStatus.textContent = "Choose a starting room to see mapped connections.";
  }
  updateEndpointStates();
}

async function activateRouteEndpoint(unitId, focusMap = false) {
  if (routeSelection === "complete" || routeSelection === "failed") {
    clearRoute();
  }
  if (routeSelection === "empty" || !routeOrigin.value) {
    routeOrigin.value = unitId;
    routeDestination.value = "";
    routeSelection = "origin_selected";
    updateEndpointStates();
    refreshRouteOptions();
    setStatus("Origin A set. Select a distinct room for destination B.");
    await selectUnit(unitId, focusMap);
    return;
  }
  if (unitId === routeOrigin.value) {
    setStatus("That room is already origin A; select a distinct destination B.");
    return;
  }
  if (unitId !== routeOrigin.value) {
    routeDestination.value = unitId;
    routeSelection = "request_pending";
    updateEndpointStates();
    const generation = ++requestGeneration;
    const origin = routeOrigin.value;
    const profile = routeProfile.value;
    await selectUnit(unitId, focusMap);
    if (generation !== requestGeneration) return;
    await requestRoute(origin, unitId, profile, generation);
  }
}

function selectLandmark(item, marker) {
  document.querySelectorAll(".unit-shape, .landmark-shape").forEach((node) => {
    node.classList.toggle("selected", node === marker);
  });
  const rows = [
    ["Landmark", item.category || "Uncategorized"],
    ["Record", item.landmark_id],
    ["Level", item.level_id],
  ];
  unitDetails.replaceChildren(...rows.map(([term, value]) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    const detail = document.createElement("dd");
    label.textContent = term;
    detail.textContent = value;
    row.append(label, detail);
    return row;
  }));
  setStatus(`Selected landmark ${item.category || item.landmark_id}.`);
}

function renderScene(scene) {
  const retainedCamera = mapFit === "manual" && currentScene?.level.level_id === scene.level.level_id
    ? (floorMap.getAttribute("viewBox") || "").split(" ").map(Number) : null;
  const previousOrigin = mapOrigin;
  if (mapFit === "manual" && !retainedCamera) mapFit = activeRoute?.guidance ? "route" : "floor";
  currentScene = scene;
  floorMap.querySelectorAll("g").forEach((node) => node.remove());
  const points = coordinates(scene.level.geometry);
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  // Keep SVG arithmetic near zero: large projected ordinates lose precision in
  // Chromium's stroke renderer. Native response coordinates are never rounded.
  mapOrigin = [Math.min(...xs), Math.min(...ys)];
  floorMap.dataset.originX = String(mapOrigin[0]);
  floorMap.dataset.originY = String(mapOrigin[1]);
  const padding = 4;
  const minX = Math.min(...xs) - padding;
  const maxX = Math.max(...xs) + padding;
  const minY = Math.min(...ys) - padding;
  const maxY = Math.max(...ys) + padding;
  floorMap.setAttribute("viewBox", `${minX - mapOrigin[0]} ${mapOrigin[1] - maxY} ${maxX - minX} ${maxY - minY}`);
  if (retainedCamera?.length === 4 && retainedCamera.every(Number.isFinite)) {
    retainedCamera[0] += previousOrigin[0] - mapOrigin[0];
    retainedCamera[1] += mapOrigin[1] - previousOrigin[1];
    floorMap.setAttribute("viewBox", retainedCamera.join(" "));
  }

  const layers = ["level", "details", "units", "landmarks"].map(() => element("g"));
  layers[0].append(svgPath(scene.level, "level-shape"));
  scene.details.forEach((item) => layers[1].append(svgPath(item, "detail-shape")));
  scene.units.forEach((item) => {
    const shape = svgPath(item, "unit-shape");
    shape.dataset.unitId = item.unit_id;
    shape.setAttribute("tabindex", "0");
    shape.setAttribute("role", "button");
    shape.setAttribute("aria-label", `Room ${item.room_id || item.unit_id}, ${item.use_type || "use not recorded"}`);
    shape.addEventListener("click", () => activateRouteEndpoint(item.unit_id));
    shape.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activateRouteEndpoint(item.unit_id);
      }
    });
    layers[2].append(shape);
  });
  scene.landmarks.forEach((item) => {
    const point = coordinates(item.geometry)[0];
    if (!point) return;
    const marker = element("circle", { cx: point[0] - mapOrigin[0], cy: -(point[1] - mapOrigin[1]), r: 1.3, class: "landmark-shape", tabindex: 0, "aria-label": item.category || "Landmark" });
    marker.setAttribute("role", "button");
    marker.addEventListener("click", () => selectLandmark(item, marker));
    marker.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectLandmark(item, marker);
      }
    });
    layers[3].append(marker);
  });
  floorMap.append(...layers);
  const routeOverlay = element("g", { id: "route-overlay" });
  floorMap.append(routeOverlay);
  renderRouteOverlay(scene.level.level_id);

  const buttons = scene.units.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.room_id || item.use_type || "Unnamed room";
    button.dataset.unitId = item.unit_id;
    button.addEventListener("click", () => activateRouteEndpoint(item.unit_id, true));
    return button;
  });
  roomList.replaceChildren(...buttons);
  updateEndpointStates();
  viewingFloor.textContent = `Viewing ${floorLabel(scene.level.level_id)}`;
  viewingFloor.dataset.levelId = scene.level.level_id;
  setStatus(`${floorLabel(scene.level.level_id)} · ${scene.units.length} rooms`);
  updateGuidanceControls();
  fitMap(mapFit);
}

async function loadScene() {
  const generation = ++sceneGeneration;
  const level = activeLevel();
  if (!level) return;
  setStatus(`Loading ${floorLabel(level.level_id)}…`);
  try {
    const scene = await request(`/demo/v1/levels/${encodeURIComponent(level.level_id)}/scene`);
    if (generation !== sceneGeneration) return;
    renderScene(scene);
  } catch (error) {
    if (generation !== sceneGeneration) return;
    restoreRenderedFloor();
    manualPreview = Boolean(guidanceStep());
    previewVisitId = null;
    updateGuidanceControls();
    renderRouteOverlay(currentScene?.level.level_id);
    const retained = currentScene ? ` Showing ${floorLabel(currentScene.level.level_id)}.` : "";
    setStatus(`Could not load ${floorLabel(level.level_id)}: ${error.message}.${retained}`);
  }
}

function activeLevel() {
  const alignedLevels = levelsByOrder.get(Number(levelSelect.value)) || [];
  return alignedLevels.find((item) => item.facility_id === facilitySelect.value);
}

function updateFacilities() {
  const previousFacility = facilitySelect.value;
  const alignedLevels = levelsByOrder.get(Number(levelSelect.value)) || [];
  const availableFacilities = alignedLevels.map((level) => facilitiesById.get(level.facility_id));
  facilitySelect.replaceChildren(
    ...availableFacilities.map((facility) => option(
      facility.facility_id,
      `${facility.code} · ${facility.name}`,
    )),
  );
  if (availableFacilities.some((facility) => facility.facility_id === previousFacility)) {
    facilitySelect.value = previousFacility;
  }
}

function initializeFloorControls(levels) {
  allLevels = levels;
  levelsByOrder = levels.reduce((groups, level) => {
    const values = groups.get(level.vertical_order) || [];
    values.push(level);
    groups.set(level.vertical_order, values);
    return groups;
  }, new Map());
  const floorOptions = [...levelsByOrder.entries()].map(([verticalOrder, alignedLevels]) => {
    const labels = alignedLevels.map((level) => {
      const facility = facilitiesById.get(level.facility_id);
      return `${facility.code} ${level.short_name}`;
    });
    return option(String(verticalOrder), labels.join(" · "));
  });
  levelSelect.replaceChildren(...floorOptions);
  if (levelsByOrder.has(0)) levelSelect.value = "0";
  updateFacilities();
}

async function selectLevel(levelId) {
  const level = allLevels.find((item) => item.level_id === levelId);
  if (!level) return;
  const aligned = levelsByOrder.get(level.vertical_order) || [];
  levelSelect.value = String(level.vertical_order);
  updateFacilities();
  if (aligned.some((item) => item.facility_id === level.facility_id)) {
    facilitySelect.value = level.facility_id;
  }
  if (currentScene?.level.level_id === levelId) {
    sceneGeneration += 1;
    renderRouteOverlay(levelId);
    updateGuidanceControls();
    fitMap(mapFit);
    setStatus(`${floorLabel(levelId)} · ${currentScene.units?.length || 0} rooms`);
    return;
  }
  await loadScene();
}

function floorLabel(levelId) {
  const level = allLevels.find((item) => item.level_id === levelId);
  if (!level) return "Floor not recorded";
  const facility = facilitiesById.get(level.facility_id);
  return [facility?.code, level.short_name].filter(Boolean).join(" ") || "Unnamed floor";
}

function restoreRenderedFloor() {
  mapFit = "floor";
  if (!currentScene) {
    viewingFloor.textContent = "Floor plan not loaded";
    if (viewingFloor.dataset) delete viewingFloor.dataset.levelId;
    setStatus("Choose a floor to load its map.");
    return;
  }
  const level = allLevels.find((item) => item.level_id === currentScene.level.level_id);
  if (level) {
    levelSelect.value = String(level.vertical_order);
    updateFacilities();
    facilitySelect.value = level.facility_id;
  }
  viewingFloor.textContent = `Viewing ${floorLabel(currentScene.level.level_id)}`;
  viewingFloor.dataset.levelId = currentScene.level.level_id;
  setStatus(`${floorLabel(currentScene.level.level_id)} · ${currentScene.units?.length || 0} rooms`);
  fitMap("floor");
}

function roomLabel(unitId) {
  return routeUnits.find((unit) => unit.unit_id === unitId)?.room_id || "Unnamed room";
}

function setRouteState(state) {
  routeUiState = state;
  // Attribute API also works in the small network-state regression harness.
  if (routeStatus.setAttribute) routeStatus.setAttribute("data-state", state);
}

function guidanceStep() {
  return activeRoute?.guidance?.steps[activeStep];
}

function stepIsVisible(step = guidanceStep()) {
  return Boolean(step && currentScene?.level.level_id === step.level_id
    && (!previewVisitId || previewVisitId === step.visit_id));
}

function updateGuidanceControls() {
  const guidance = activeRoute?.guidance;
  const step = guidanceStep();
  stepPrevious.disabled = !step || activeStep === 0;
  stepNext.disabled = !step || activeStep === guidance.steps.length - 1;
  stepPosition.textContent = step ? `Step ${activeStep + 1} of ${guidance.steps.length} · ${floorLabel(step.level_id)}` : "Choose a route";
  currentInstruction.textContent = step?.instruction || (activeRoute?.guidance && !activeRoute.guidance.steps.length
    ? unavailableGuidanceMessage : ["error", "pending"].includes(routeUiState)
      ? routeStatus.textContent : "Select a starting room and destination to see directions.");
  floorPreview.hidden = !step || !manualPreview;
  transitionViews.hidden = !step?.transition_id;
  if (!step) return;
  previewMessage.textContent = `You are previewing ${floorLabel(activeLevel()?.level_id)}. Selected step: ${floorLabel(step.level_id)}.`;
  routeSteps.querySelectorAll("button").forEach((node) => {
    const selected = node.dataset.stepId === step.step_id;
    node.classList.toggle("active", selected);
    if (selected) node.setAttribute("aria-current", "step");
    else node.removeAttribute("aria-current");
  });
  floorJourney.querySelectorAll("button").forEach((node) => {
    const visit = guidance.visits.find((item) => item.visit_id === node.dataset.visitId);
    const selected = visit?.visit_id === (previewVisitId || step.visit_id)
      && visit?.level_id === activeLevel()?.level_id;
    if (selected) node.setAttribute("aria-current", "location");
    else node.removeAttribute("aria-current");
  });
  if (step.transition_id) {
    const transition = guidance.transitions.find((item) => item.transition_id === step.transition_id);
    transitionDeparture.textContent = `Departure: ${transition.from_label}`;
    transitionArrival.textContent = `Arrival: ${transition.to_label}`;
    transitionDeparture.setAttribute("aria-pressed", String(step.phase === "departure" && !manualPreview));
    transitionArrival.setAttribute("aria-pressed", String(step.phase === "arrival" && !manualPreview));
  }
}

async function selectGuidanceStep(stepId, cameraMode = "step") {
  const index = activeRoute?.guidance?.steps.findIndex((step) => step.step_id === stepId);
  if (index === undefined || index < 0) return;
  activeStep = index;
  manualPreview = false;
  previewVisitId = null;
  const step = guidanceStep();
  // A marker alone gives no useful walking context. Initial directions also
  // retain the full floor route while selecting the first instruction.
  mapFit = cameraMode === "step" && step.geometry_ids.length ? "step" : "route";
  updateGuidanceControls();
  renderRouteOverlay(currentScene?.level.level_id);
  if (step.level_id) await selectLevel(step.level_id);
  else {
    sceneGeneration += 1;
    restoreRenderedFloor();
    updateGuidanceControls();
    renderRouteOverlay(currentScene?.level.level_id);
  }
}

async function previewFloor(levelId, visitId = null) {
  manualPreview = Boolean(guidanceStep());
  previewVisitId = visitId;
  mapFit = "route";
  updateGuidanceControls();
  await selectLevel(levelId);
}

function selectTransitionPhase(phase) {
  const step = guidanceStep();
  const other = activeRoute?.guidance?.steps.find((item) => item.transition_id
    && item.transition_id === step?.transition_id && item.phase === phase);
  if (other) return selectGuidanceStep(other.step_id);
}

function markerNode(marker, number, selected = false) {
  const node = element("g", { class: `route-marker${selected ? " selected" : ""}`,
    transform: `translate(${marker.coordinates[0] - mapOrigin[0]} ${-(marker.coordinates[1] - mapOrigin[1])})`,
    "data-marker-id": marker.marker_id,
    "aria-label": `${number}. ${marker.label}`,
    role: "img",
    "pointer-events": "none",
  });
  node.dataset.markerId = marker.marker_id;
  node.dataset.x = String(marker.coordinates[0]);
  node.dataset.y = String(marker.coordinates[1]);
  const shape = element("circle", { r: 2.1 });
  const label = element("text", { "font-size": 2.4 });
  label.textContent = String(number);
  const title = element("title");
  title.textContent = `${number}. ${marker.label}`;
  node.append(title, shape, label);
  return node;
}

function renderRouteOverlay(levelId) {
  const overlay = document.querySelector("#route-overlay");
  if (!overlay) return;
  overlay.replaceChildren();
  const guidance = activeRoute?.guidance;
  if (!guidance) return;
  const step = guidanceStep();
  const visible = step?.level_id === levelId && (!previewVisitId || previewVisitId === step.visit_id);
  const pieces = guidance.geometries
    .filter((item) => item.level_id === levelId);
  let walkingMarker = null;
  pieces.forEach((item) => {
    const path = svgPath(item, "route-segment");
    path.dataset.geometryId = item.geometry_id;
    overlay.append(path);
  });
  if (visible) {
    const selectedPieces = pieces.filter((item) => step.geometry_ids.includes(item.geometry_id));
    selectedPieces.forEach((item) => overlay.append(svgPath(item, "route-halo")));
    selectedPieces.forEach((item) => {
      const selected = svgPath(item, "route-selected");
      selected.dataset.geometryId = item.geometry_id;
      selected.dataset.stepId = step.step_id;
      overlay.append(selected);
    });
    const firstPiece = pieces.find((item) => step.geometry_ids.includes(item.geometry_id));
    if (firstPiece) {
      const point = firstPiece.geometry.coordinates[0];
      walkingMarker = markerNode({marker_id: `step-${step.step_id}`, coordinates: point,
        label: step.instruction}, activeStep + 1, true);
      // An arrow at the actual end of the selected span indicates directed travel.
      const lastPiece = pieces.filter((item) => step.geometry_ids.includes(item.geometry_id)).at(-1);
      const points = lastPiece.geometry.coordinates;
      let before = points.length - 2;
      const end = points.at(-1);
      while (before >= 0 && points[before][0] === end[0] && points[before][1] === end[1]) before -= 1;
      if (before >= 0) {
        const angle = -Math.atan2(end[1] - points[before][1], end[0] - points[before][0]) * 180 / Math.PI;
        overlay.append(element("path", {class: "route-direction", d: "M-2 -1.3 L0 0 L-2 1.3", fill: "none",
          "pointer-events": "none",
          stroke: "#005fcc", "stroke-width": 3, "vector-effect": "non-scaling-stroke",
          transform: `translate(${end[0] - mapOrigin[0]} ${-(end[1] - mapOrigin[1])}) rotate(${angle})`, "aria-hidden": "true"}));
      }
    }
  }
  guidance.markers.filter((marker) => marker.level_id === levelId)
    .sort((left, right) => Number(visible && step.marker_ids.includes(left.marker_id))
      - Number(visible && step.marker_ids.includes(right.marker_id))).forEach((marker) => {
    const transition = guidance.transitions.find((item) => item.departure_marker_id === marker.marker_id
      || item.arrival_marker_id === marker.marker_id);
    const number = guidance.steps.findIndex((item) => transition
      ? item.transition_id === transition.transition_id && item.phase === "departure"
      : item.marker_ids.includes(marker.marker_id)) + 1;
    overlay.append(markerNode(marker, number, visible && step.marker_ids.includes(marker.marker_id)));
  });
  if (walkingMarker) overlay.append(walkingMarker);
  resizeMarkers();
}

function resizeMarkers() {
  // Keep marker text legible at both floor and selected-span scales.
  const box = (floorMap.getAttribute("viewBox") || "0 0 100 100").split(" ").map(Number);
  const width = floorMap.clientWidth || 600;
  const height = floorMap.clientHeight || 400;
  const scale = Math.max(box[2] / width, box[3] / height);
  floorMap.querySelectorAll(".route-marker").forEach((node) => {
    node.querySelector("circle")?.setAttribute("r", 11 * scale);
    node.querySelector("text")?.setAttribute("font-size", 12 * scale);
  });
  floorMap.querySelectorAll(".route-direction").forEach((node) => {
    node.setAttribute("d", `M${-10 * scale} ${-6 * scale} L0 0 L${-10 * scale} ${6 * scale}`);
  });
}

function fitMap(mode) {
  mapFit = mode;
  floorMap.dataset.cameraMode = mode;
  if (!currentScene) return;
  if (mode === "manual") {
    resizeMarkers();
    return;
  }
  const guidance = activeRoute?.guidance;
  const levelId = currentScene.level.level_id;
  const step = guidanceStep();
  let points = [];
  if (mode !== "floor" && guidance) {
    const selectedOnly = mode === "step" && stepIsVisible();
    guidance.geometries.filter((item) => item.level_id === levelId
      && (!selectedOnly || step.geometry_ids.includes(item.geometry_id)))
      .forEach((item) => points.push(...coordinates(item.geometry)));
    guidance.markers.filter((item) => item.level_id === levelId
      && (!selectedOnly || step.marker_ids.includes(item.marker_id)))
      .forEach((item) => points.push(item.coordinates));
  }
  // Express intermediate floors and same-anchor routes can contain only
  // coincident markers. Keep their floor context instead of fitting one point.
  if (!points.length || points.every((point) => point[0] === points[0][0] && point[1] === points[0][1])) {
    points = coordinates(currentScene.level.geometry);
  }
  if (!points.length) return;
  const xs = points.map((point) => point[0]), ys = points.map((point) => point[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  // Reserve screen space for the 11px route circles and their stroke even on
  // long routes in narrow viewports; SVG meet scaling may add more letterboxing.
  const pixelMargin = 16;
  const width = Math.max(1, (floorMap.clientWidth || 600) - pixelMargin * 2);
  const height = Math.max(1, (floorMap.clientHeight || 400) - pixelMargin * 2);
  const padding = Math.max(mode === "step" ? 8 : 4,
    pixelMargin * (maxX - minX) / width, pixelMargin * (maxY - minY) / height);
  floorMap.setAttribute("viewBox", `${minX - mapOrigin[0] - padding} ${mapOrigin[1] - maxY - padding} ${maxX - minX + padding * 2} ${maxY - minY + padding * 2}`);
  resizeMarkers();
}

function zoomMap(factor) {
  if (!currentScene || !Number.isFinite(factor) || factor <= 0) return;
  const box = (floorMap.getAttribute("viewBox") || "").split(" ").map(Number);
  if (box.length !== 4 || !box.every(Number.isFinite) || box[2] <= 0 || box[3] <= 0) return;
  // Bound the largest dimension to 2 m–10 km, preserving center and aspect.
  const span = Math.max(box[2], box[3]);
  const scale = Math.max(2, Math.min(10000, span * factor)) / span;
  const width = box[2] * scale, height = box[3] * scale;
  floorMap.setAttribute("viewBox", `${box[0] + (box[2] - width) / 2} ${box[1] + (box[3] - height) / 2} ${width} ${height}`);
  mapFit = "manual";
  floorMap.dataset.cameraMode = "manual";
  resizeMarkers();
}

function renderRoute(body) {
  activeRoute = body.status === 200 ? body : null;
  activeStep = 0;
  routeAccessibility.hidden = body.profile !== "elevator_only";
  routeSteps.replaceChildren();
  floorJourney.replaceChildren();
  manualPreview = false;
  previewVisitId = null;
  routeDiagnostics.textContent = JSON.stringify(body, null, 2);
  if (body.status !== 200) {
    const errors = {
      disconnected: "The map does not contain a connected route between these rooms.",
      no_elevator_only_route: "No route without stairs is available between these rooms in the map.",
      endpoint_unavailable: "A mapped route point is unavailable for one of these rooms.",
      unknown_endpoint: "One of these rooms was not found. Choose a room from the list.",
      ambiguous_endpoint: "That room name matches more than one room. Choose its building and floor from the list.",
    };
    routeStatus.textContent = errors[body.code] || "Directions are unavailable for this request. Please try again.";
    setRouteState("error");
    updateGuidanceControls();
    currentInstruction.textContent = routeStatus.textContent;
    renderRouteOverlay(activeLevel()?.level_id);
    return;
  }
  if (!body.guidance || body.guidance.version !== "dt018-guidance-v1") {
    activeRoute = null;
    updateGuidanceControls();
    routeStatus.textContent = "This demo needs an update before directions can be displayed.";
    currentInstruction.textContent = routeStatus.textContent;
    setRouteState("error");
    renderRouteOverlay(currentScene?.level.level_id);
    return;
  }
  setRouteState("success");
  const guidance = body.guidance;
  const summary = guidance?.status === "available" && guidance.distance_m !== null
    ? `About ${Math.round(guidance.distance_m)} m mapped route`
    : "Mapped route · geometry needs review";
  routeStatus.textContent = `${roomLabel(body.origin.unit_id)} → ${roomLabel(body.destination.unit_id)}. ${summary}.`;
  if (guidance?.status !== "available") {
    routeStatus.textContent += ` ${guidance?.warnings?.join(" ") || "Directions preview is unavailable."}`;
  }
  if (!guidance?.steps.length) {
    updateGuidanceControls();
    currentInstruction.textContent = unavailableGuidanceMessage;
    renderRouteOverlay(currentScene?.level.level_id);
    return;
  }
  const items = guidance.steps.map((step, index) => {
    const item = document.createElement("li");
    const visit = guidance.visits.find((candidate) => candidate.visit_id === step.visit_id);
    if (index === 0 || step.visit_id !== guidance.steps[index - 1].visit_id) {
      const heading = document.createElement("span");
      heading.className = "visit-heading";
      heading.textContent = visit?.label || floorLabel(step.level_id);
      item.append(heading);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.stepId = step.step_id;
    const number = document.createElement("span");
    number.className = "step-number";
    number.textContent = String(index + 1);
    number.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.textContent = step.instruction;
    button.setAttribute("aria-label", `Step ${index + 1}. ${step.instruction}`);
    button.append(number, text);
    button.addEventListener("click", () => selectGuidanceStep(step.step_id));
    item.append(button);
    return item;
  });
  routeSteps.replaceChildren(...items);
  guidance.visits.forEach((visit, index) => {
    if (index) {
      const connector = document.createElement("span");
      connector.className = "journey-connector";
      const transition = guidance.transitions.find((item) => item.to_visit_id === visit.visit_id);
      connector.textContent = transition ? `${transition.mode === "stairs" ? "Stairs" : "Elevator"} →` : "→";
      floorJourney.append(connector);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.visitId = visit.visit_id;
    button.textContent = `${index + 1}. ${visit.label}`;
    button.disabled = !visit.level_id;
    button.addEventListener("click", () => previewFloor(visit.level_id, visit.visit_id));
    floorJourney.append(button);
  });
  selectGuidanceStep(guidance.steps[0].step_id, "route");
}

async function requestRoute(origin, destination, profile, generation) {
  activeRoute = null;
  sceneGeneration += 1;
  manualPreview = false;
  previewVisitId = null;
  routeSteps.replaceChildren();
  floorJourney.replaceChildren();
  routeDiagnostics.textContent = "Route request in progress.";
  updateGuidanceControls();
  restoreRenderedFloor();
  renderRouteOverlay(activeLevel()?.level_id);
  routeAccessibility.hidden = profile !== "elevator_only";
  refreshRouteOptions(origin, profile);
  if (!origin || !destination || origin === destination) {
    routeSelection = origin ? "origin_selected" : "empty";
    setRouteState("empty");
    routeStatus.textContent = "Choose two distinct endpoints. Select origin A and destination B.";
    currentInstruction.textContent = routeStatus.textContent;
    return;
  }
  routeSelection = "request_pending";
  setRouteState("pending");
  routeStatus.textContent = "Finding a mapped route…";
  currentInstruction.textContent = routeStatus.textContent;
  try {
    const body = await request("/demo/v1/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: { unit_id: origin },
        destination: { unit_id: destination },
        profile: profile,
      }),
    });
    if (generation !== requestGeneration) return;
    renderRoute(body);
    routeSelection = "complete";
  } catch (error) {
    if (generation !== requestGeneration) return;
    const body = error.payload || { status: 500, code: error.message, profile: profile };
    if (!body.profile) body.profile = profile;
    renderRoute(body);
    routeSelection = "failed";
  }
}

function setAvailabilityState(state, origin = "", profile = "") {
  if (state !== "ready") {
    reachableDestinations.replaceChildren();
    reachableDestinations.hidden = true;
  }
  routeOptionsStatus.setAttribute?.("data-state", state);
  routeOptionsStatus.setAttribute?.("data-origin-unit-id", origin);
  routeOptionsStatus.setAttribute?.("data-profile", profile);
}

function renderReachableDestinations(availability, origin, profile, generation) {
  const units = routeUnits.filter((unit) => availability.get(unit.unit_id) === "connected");
  reachableDestinations.replaceChildren();
  reachableDestinations.hidden = !units.length || units.length > 5;
  if (reachableDestinations.hidden) return;
  units.forEach((unit) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Directions to ${unit.room_id || "Unnamed room"} · ${floorLabel(unit.level_id)}`;
    button.dataset.destinationUnitId = unit.unit_id;
    button.dataset.originUnitId = origin;
    button.dataset.profile = profile;
    button.addEventListener("click", () => {
      if (generation !== availabilityGeneration || routeOrigin.value !== origin || routeProfile.value !== profile) return;
      routeDestination.value = unit.unit_id;
      return submitSelectedRoute();
    });
    reachableDestinations.append(button);
  });
}

function renderDestinationOptions(availability = null, origin = "") {
  if (!routeUnits.length) return;
  const selected = routeDestination.value;
  const makeOption = (unit, state) => {
    const node = option(unit.unit_id, `${unit.room_id || "Unnamed room"} · ${floorLabel(unit.level_id)}`);
    if (state) node.dataset.availability = state;
    return node;
  };
  const children = [option("", "Select destination B")];
  if (!availability) {
    children.push(...routeUnits.map((unit) => makeOption(unit)));
  } else {
    const labels = {
      connected: "Mapped routes",
      same_anchor: "Same route point — no walking path",
      disconnected: "No mapped connection",
      endpoint_unavailable: "No mapped route point",
    };
    Object.entries(labels).forEach(([state, label]) => {
      const units = routeUnits.filter((unit) => availability.get(unit.unit_id) === state);
      if (!units.length) return;
      const group = document.createElement("optgroup");
      group.label = `${label} (${units.length})`;
      group.dataset.availability = state;
      group.append(...units.map((unit) => makeOption(unit, state)));
      children.push(group);
    });
    // Retain the complete catalog: Swap and assistant entry may next select the
    // previous origin. Native selects discard values absent from their options.
    const startingRoom = routeUnits.find((item) => item.unit_id === origin);
    if (startingRoom) {
      const node = makeOption(startingRoom);
      node.textContent += " · starting room";
      children.push(node);
    }
  }
  routeDestination.replaceChildren(...children);
  routeDestination.value = selected;
}

async function refreshRouteOptions(origin = routeOrigin.value, profile = routeProfile.value) {
  const generation = ++availabilityGeneration;
  renderDestinationOptions();
  if (!origin || !routeUnits.some((unit) => unit.unit_id === origin)) {
    setAvailabilityState("empty");
    routeOptionsStatus.textContent = "Choose a starting room to see mapped connections.";
    return;
  }
  setAvailabilityState("pending", origin, profile);
  routeOptionsStatus.textContent = "Checking mapped connections… You can still choose any room.";
  try {
    const body = await request(`/demo/v1/route-options?origin_unit_id=${encodeURIComponent(origin)}&profile=${encodeURIComponent(profile)}`);
    if (generation !== availabilityGeneration || routeOrigin.value !== origin || routeProfile.value !== profile) return;
    const allowed = ["connected", "same_anchor", "disconnected", "endpoint_unavailable"];
    if (body.version !== "route-options-v1" || body.origin_unit_id !== origin
      || body.profile !== profile || !Array.isArray(body.destinations)
      || body.destinations.some((item) => !allowed.includes(item.availability))) {
      throw new Error("Invalid route choices");
    }
    const availability = new Map(body.destinations.map((item) => [item.unit_id, item.availability]));
    const expected = routeUnits.filter((unit) => unit.unit_id !== origin);
    if (availability.size !== expected.length || body.destinations.length !== expected.length
      || expected.some((unit) => !availability.has(unit.unit_id))) throw new Error("Incomplete route choices");
    renderDestinationOptions(availability, origin);
    const connected = body.destinations.filter((item) => item.availability === "connected").length;
    const sameAnchor = body.destinations.filter((item) => item.availability === "same_anchor").length;
    let help = `${connected} mapped ${connected === 1 ? "route" : "routes"} from ${roomLabel(origin)} with this route option. Choose from “Mapped routes”.`;
    if (connected > 0 && connected <= 5) help = `${connected} mapped ${connected === 1 ? "route" : "routes"} from ${roomLabel(origin)} with this route option. Choose a named destination below.`;
    if (!connected) help = `0 mapped routes from ${roomLabel(origin)} with this route option. The map has no connected destination with a walking path.`;
    if (sameAnchor) help += ` ${sameAnchor} ${sameAnchor === 1 ? "room shares" : "rooms share"} the starting route point, with no walking path drawn.`;
    const chosen = availability.get(routeDestination.value);
    if (chosen === "disconnected") help += " Your selected destination has no mapped connection.";
    if (chosen === "endpoint_unavailable") help += " Your selected destination has no mapped route point.";
    help += " Other rooms remain selectable. Door connections and accessibility are not verified.";
    routeOptionsStatus.textContent = help;
    setAvailabilityState("ready", origin, profile);
    renderReachableDestinations(availability, origin, profile, generation);
  } catch (error) {
    if (generation !== availabilityGeneration || routeOrigin.value !== origin || routeProfile.value !== profile) return;
    renderDestinationOptions();
    const reason = error.payload?.code === "endpoint_unavailable"
      ? "This starting room has no mapped route point."
      : "Connection choices are unavailable right now.";
    routeOptionsStatus.textContent = `${reason} You can still choose any room and request directions.`;
    setAvailabilityState("error", origin, profile);
  }
}

function submitSelectedRoute() {
  clearRoute(false);
  const origin = routeOrigin.value;
  const destination = routeDestination.value;
  updateEndpointStates();
  return requestRoute(origin, destination, routeProfile.value, ++requestGeneration);
}

function parseExactDirections(message) {
  const match = message.trim().match(/^(?:(wheelchair|mobility|accessible|step-free)\s+)?directions\s+from\s+(\S+)\s+to\s+(\S+)$/i);
  if (!match) return null;
  return {
    origin: match[2],
    destination: match[3],
    profile: match[1] ? "elevator_only" : "default",
  };
}

function resolveRouteUnitId(identifier) {
  const normalized = identifier.trim().toUpperCase();
  const matches = routeUnits.filter((unit) => (
    unit.unit_id.toUpperCase() === normalized
    || (unit.room_id && unit.room_id.toUpperCase() === normalized)
  ));
  return matches.length === 1 ? matches[0].unit_id : identifier;
}

routeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitSelectedRoute();
});

routeOrigin.addEventListener("change", submitSelectedRoute);
routeDestination.addEventListener("change", submitSelectedRoute);
routeClear.addEventListener("click", () => {
  clearRoute();
  routeStatus.textContent = "Route endpoints cleared. Select origin A.";
});
routeSwap.addEventListener("click", async () => {
  const origin = routeOrigin.value;
  const destination = routeDestination.value;
  if (!origin || !destination || origin === destination) return;
  routeOrigin.value = destination;
  routeDestination.value = origin;
  await submitSelectedRoute();
});

routeProfile.addEventListener("change", () => {
  routeAccessibility.hidden = true;
  return submitSelectedRoute();
});

assistantForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  assistantResponse.textContent = "Checking normalized artifact records…";
  assistantEvidence.textContent = "";
  const directionRequest = parseExactDirections(assistantInput.value);
  if (directionRequest) {
    const origin = resolveRouteUnitId(directionRequest.origin);
    const destination = resolveRouteUnitId(directionRequest.destination);
    routeOrigin.value = origin;
    routeDestination.value = destination;
    routeProfile.value = directionRequest.profile;
    updateEndpointStates();
    assistantResponse.textContent = "Rendering the deterministic route result below.";
    await requestRoute(origin, destination, directionRequest.profile, ++requestGeneration);
    return;
  }
  try {
    const body = await request("/demo/v1/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: assistantInput.value,
        facility_id: facilitySelect.value,
        level_id: activeLevel()?.level_id,
      }),
    });
    assistantResponse.textContent = body.text;
    assistantEvidence.textContent = body.evidence?.length ? `Evidence: ${body.evidence.map((item) => `${item.layer} · ${item.feature_id}`).join("; ")}` : "No artifact record cited.";
    const unit = body.entities?.find((item) => item.type === "unit");
    if (unit && unit.level_id === activeLevel()?.level_id) await selectUnit(unit.unit_id, true);
  } catch (error) {
    assistantResponse.textContent = error.message;
  }
});

stepPrevious.addEventListener("click", () => {
  const step = activeRoute?.guidance?.steps[activeStep - 1];
  if (step) return selectGuidanceStep(step.step_id);
});
stepNext.addEventListener("click", () => {
  const step = activeRoute?.guidance?.steps[activeStep + 1];
  if (step) return selectGuidanceStep(step.step_id);
});
transitionDeparture.addEventListener("click", () => selectTransitionPhase("departure"));
transitionArrival.addEventListener("click", () => selectTransitionPhase("arrival"));
document.querySelector("#show-selected-step").addEventListener("click", () => {
  const step = guidanceStep();
  if (step) return selectGuidanceStep(step.step_id);
});
document.querySelector("#fit-route").addEventListener("click", () => fitMap("route"));
document.querySelector("#fit-floor").addEventListener("click", () => fitMap("floor"));
document.querySelector("#zoom-in").addEventListener("click", () => zoomMap(1 / 1.5));
document.querySelector("#zoom-out").addEventListener("click", () => zoomMap(1.5));

facilitySelect.addEventListener("change", () => previewFloor(activeLevel()?.level_id));
levelSelect.addEventListener("change", async () => {
  updateFacilities();
  await previewFloor(activeLevel()?.level_id);
});

async function initialize() {
  try {
    const [health, facilities, levels] = await Promise.all([
      request("/demo/v1/health"),
      request("/demo/v1/facilities"),
      request("/demo/v1/levels"),
    ]);
    artifactHash.textContent = health.artifact_sha256;
    graphHash.textContent = health.provenance?.graph_sha256 || "Unavailable";
    facilitiesById = new Map(
      facilities.facilities.map((facility) => [facility.facility_id, facility]),
    );
    initializeFloorControls(levels.levels);
    const units = await request("/demo/v1/units");
    routeUnits = units.units;
    const routeOptions = units.units.map((unit) => option(
      unit.unit_id,
      `${unit.room_id || "Unnamed room"} · ${floorLabel(unit.level_id)}`,
    ));
    routeOrigin.replaceChildren(option("", "Select origin A"), ...routeOptions.map((item) => item.cloneNode(true)));
    routeDestination.replaceChildren(option("", "Select destination B"), ...routeOptions);
    await loadScene();
  } catch (error) {
    setStatus(error.message);
  }
}

initialize();
