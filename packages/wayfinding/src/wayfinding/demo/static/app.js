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
const unavailableGuidanceMessage = "A directions preview is unavailable for this route. See route details for the data checks.";
let facilitiesById = new Map();
// Navigation identity is state-owned; select values are event inputs only.
const navigationState = {
  context: "campus", facilityId: null, requestedLevelId: null,
  displayedLevelId: null, intentRevision: 0, roomRevision: 0, assistantRevision: 0,
  selectedUnitId: null, sceneStatus: "idle", sceneError: null,
  rememberedLevels: new Map(), pendingStep: null,
};
const openFloor = document.querySelector("#open-floor");
const retryScene = document.querySelector("#retry-scene");
const returnToRoute = document.querySelector("#return-to-route");
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
let routeAvailability = null;
let routeAvailabilityOrigin = "";
let routeAvailabilityProfile = "";
let routeAvailabilityPendingOrigin = "";
let routeAvailabilityPendingProfile = "";
let routeAvailabilitySettled = Promise.resolve();
let settleRouteAvailability = () => {};
let routeUiState = "empty";
const campusView = document.querySelector("#campus-view");
const floorView = document.querySelector("#floor-view");
const campusMap = document.querySelector("#campus-map");
const campusSearch = document.querySelector("#campus-search");
let campusData = null;
let campusFacilityId = null;
let campusCamera = null;
let campusOrigin = [0, 0];

function beginNavigation(context) {
  navigationState.context = context;
  navigationState.intentRevision += 1;
  navigationState.roomRevision += 1;
  navigationState.pendingStep = null;
  navigationState.sceneStatus = "idle";
  navigationState.sceneError = null;
  sceneGeneration += 1;
  retryScene.hidden = true;
  floorMap.setAttribute("aria-busy", "false");
}

function showFloorContext() {
  campusView.hidden = true;
  floorView.hidden = false;
  document.querySelector("#map-context").textContent = "Floor";
}

function showCampus() {
  beginNavigation(campusFacilityId ? "building" : "campus");
  campusView.hidden = false;
  floorView.hidden = true;
  document.querySelector("#map-context").textContent = campusFacilityId ? "Building" : "Campus";
  manualPreview = Boolean(guidanceStep());
  updateGuidanceControls();
}

function validCampusBounds(bounds) {
  return Array.isArray(bounds) && bounds.length === 4 && bounds.every(Number.isFinite)
    && bounds[2] >= bounds[0] && bounds[3] >= bounds[1];
}

function frameCampus(bounds) {
  if (!validCampusBounds(bounds)) return;
  const width = Math.max(bounds[2] - bounds[0], 1);
  const height = Math.max(bounds[3] - bounds[1], 1);
  const padding = Math.max(width, height) * 0.12 + 2;
  campusCamera = [bounds[0] - campusOrigin[0] - padding,
    campusOrigin[1] - bounds[3] - padding, width + padding * 2, height + padding * 2];
  campusMap.setAttribute("viewBox", campusCamera.join(" "));
}

function resetCampusCamera() {
  const selected = campusData?.facilities.find(item => item.facility_id === campusFacilityId);
  frameCampus(selected?.bounds || campusData?.bounds);
}

function zoomCampus(factor) {
  if (!campusCamera) return;
  const [x, y, width, height] = campusCamera;
  const nextWidth = Math.max(1, Math.min(width * factor, 100000));
  const nextHeight = nextWidth * height / width;
  campusCamera = [x + (width - nextWidth) / 2, y + (height - nextHeight) / 2, nextWidth, nextHeight];
  campusMap.setAttribute("viewBox", campusCamera.join(" "));
}

function renderCampusBuildings() {
  const query = campusSearch.value.trim().toLocaleLowerCase();
  const matches = (campusData?.facilities || []).filter(item =>
    [item.name, item.code, item.facility_id].some(value => String(value || "").toLocaleLowerCase().includes(query)));
  document.querySelector("#campus-buildings").replaceChildren(...matches.map(item => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.campusFacilityId = item.facility_id;
    button.textContent = `${item.code || "Building"} · ${item.name || item.facility_id}`;
    button.setAttribute("aria-pressed", String(item.facility_id === campusFacilityId));
    button.addEventListener("click", () => openBuilding(item.facility_id));
    return button;
  }));
  document.querySelector("#campus-status").textContent = matches.length
    ? `${matches.length} pilot building${matches.length === 1 ? "" : "s"} found. Visibility does not imply a route connection.`
    : "No matching building in this three-building pilot. The campus inventory is incomplete.";
}

function selectCampusBuilding(facilityId) {
  const item = campusData?.facilities.find(facility => facility.facility_id === facilityId);
  if (!item) return;
  const changed = campusFacilityId !== facilityId;
  campusFacilityId = facilityId;
  showCampus();
  selectBuildingControls(facilityId);
  const heading = document.createElement("h3");
  heading.textContent = `${item.code || "Building"} · ${item.name || item.facility_id}`;
  const note = document.createElement("p");
  note.textContent = item.levels.length ? "Recorded indoor floors · partial indoor coverage. Select a floor to inspect rooms."
    : "No indoor floors are recorded for this building. Overview only.";
  const buttons = item.levels.map(level => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.campusLevelId = level.level_id;
    button.textContent = `Floor ${level.short_name || "not named"}`;
    button.addEventListener("click", () => previewFloor(level.level_id));
    return button;
  });
  const missing = document.createElement("p");
  missing.textContent = item.geometry_status === "available" ? "" : "Footprint geometry is unavailable. No location has been inferred.";
  document.querySelector("#campus-details").replaceChildren(heading, note, ...buttons, missing);
  document.querySelector("#campus-reset").textContent = "Show whole building";
  document.querySelectorAll(".campus-shape").forEach(shape =>
    shape.classList.toggle("selected", shape.dataset.campusFacilityId === facilityId));
  renderCampusBuildings();
  if (changed) resetCampusCamera();
}

function openBuilding(facilityId) {
  selectCampusBuilding(facilityId);
  const level = activeLevel();
  if (level) return previewFloor(level.level_id);
}

function renderQuickNavigation() {
  const buildingButtons = document.querySelector("#building-buttons");
  if (buildingButtons.children.length !== facilitiesById.size) {
    buildingButtons.replaceChildren(...Array.from(facilitiesById.values(), facility => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.buildingId = facility.facility_id;
      button.textContent = facility.code || facility.name;
      button.setAttribute("aria-label", `${facility.code} · ${facility.name}. Show rooms.`);
      button.addEventListener("click", () => openBuilding(facility.facility_id));
      return button;
    }));
  }
  for (const button of buildingButtons.children) {
    button.setAttribute("aria-pressed", String(button.dataset.buildingId === navigationState.facilityId));
  }
  const floors = allLevels.filter(level => level.facility_id === navigationState.facilityId);
  const floorButtons = document.querySelector("#floor-buttons");
  if (Array.from(floorButtons.children, button => button.dataset.levelId).join("|") !== floors.map(level => level.level_id).join("|")) {
    floorButtons.replaceChildren(...floors.map(level => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.levelId = level.level_id;
      button.textContent = level.short_name;
      button.setAttribute("aria-label", `Open ${floorLabel(level.level_id)}`);
      button.addEventListener("click", () => previewFloor(level.level_id));
      return button;
    }));
  }
  for (const button of floorButtons.children) {
    button.setAttribute("aria-pressed", String(button.dataset.levelId === navigationState.requestedLevelId));
  }
}

function renderCampus() {
  if (!campusData) return;
  if (validCampusBounds(campusData.bounds)) campusOrigin = campusData.bounds.slice(0, 2);
  campusMap.querySelectorAll("g").forEach(node => node.remove());
  const layer = element("g");
  for (const item of campusData.facilities) {
    if (item.geometry_status !== "available" || !item.geometry) continue;
    const polygons = item.geometry.type === "Polygon" ? [item.geometry.coordinates] : item.geometry.coordinates;
    const d = polygons.flatMap(polygon => polygon.map(ring => ring.map((point, index) =>
      `${index ? "L" : "M"}${point[0] - campusOrigin[0]} ${campusOrigin[1] - point[1]}`).join(" ") + " Z")).join(" ");
    const shape = element("path", {d, class: "campus-shape", tabindex: 0, role: "button",
      "aria-label": `${item.code} · ${item.name}. Show rooms.`, "fill-rule": "evenodd"});
    shape.dataset.campusFacilityId = item.facility_id;
    shape.addEventListener("click", () => openBuilding(item.facility_id));
    shape.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();openBuilding(item.facility_id);
      }
    });
    layer.append(shape);
    if (validCampusBounds(item.bounds)) {
      const label = element("text", {x: (item.bounds[0] + item.bounds[2]) / 2 - campusOrigin[0],
        y: campusOrigin[1] - (item.bounds[1] + item.bounds[3]) / 2, class: "campus-label"});
      label.textContent = item.code || item.name;
      layer.append(label);
    }
  }
  campusMap.append(layer);
  if (!campusCamera) resetCampusCamera();
  renderCampusBuildings();
}

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

function setStatus(message, sceneMessage = false) {
  if (!sceneMessage && ["loading", "error"].includes(navigationState.sceneStatus)) return;
  mapStatus.textContent = message;
}

async function selectUnit(unitId, focusMap = false) {
  const revision = ++navigationState.roomRevision;
  const intent = navigationState.intentRevision;
  const levelId = currentScene?.level.level_id;
  navigationState.selectedUnitId = unitId;
  const isCurrent = () => revision === navigationState.roomRevision
    && intent === navigationState.intentRevision
    && navigationState.selectedUnitId === unitId
    && currentScene?.level.level_id === levelId;
  try {
    const body = await request(`/demo/v1/units/${encodeURIComponent(unitId)}`);
    if (!isCurrent()) return false;
    document.querySelectorAll(".unit-shape").forEach((node) => node.classList.toggle("selected", node.dataset.unitId === unitId));
    const rows = [
      ["Room", body.room_id || "Not assigned"], ["Category", body.category || "Not recorded"],
      ["Use type", body.use_type || "Not recorded"],
      ["Destination tag", body.accessible === null ? "Unknown" : String(body.accessible)],
      ["Verified by", body.verified_by || "Not recorded"], ["Verified date", body.verified_date || "Not recorded"],
    ];
    unitDetails.replaceChildren(...rows.map(([term, value]) => {
      const row = document.createElement("div"), label = document.createElement("dt"), detail = document.createElement("dd");
      label.textContent = term; detail.textContent = value;
      row.append(label, detail); return row;
    }));
    document.querySelector(".facts").open = true;
    setStatus(`Selected room ${body.room_id || body.unit_id}. Destination metadata does not describe path accessibility.`);
    if (focusMap) document.querySelector(`[data-unit-id="${CSS.escape(unitId)}"]`)?.focus();
    return true;
  } catch (error) {
    if (isCurrent()) setStatus(`Could not load room details: ${error.message}`);
    return false;
  }
}

function updateEndpointStates() {
  const hasCurrentAvailability = routeAvailability instanceof Map
    && routeAvailabilityOrigin === routeOrigin.value
    && routeAvailabilityProfile === routeProfile.value;
  document.querySelectorAll("[data-unit-id]").forEach((node) => {
    const isOrigin = node.dataset.unitId === routeOrigin.value;
    const isDestination = node.dataset.unitId === routeDestination.value;
    const availability = hasCurrentAvailability ? routeAvailability.get(node.dataset.unitId) : null;
    const isConnected = !isOrigin && availability === "connected";
    const isUnavailable = !isOrigin && Boolean(availability) && availability !== "connected";
    node.classList.toggle("route-origin", isOrigin);
    node.classList.toggle("route-destination", isDestination);
    node.classList.toggle("route-connected", isConnected);
    node.classList.toggle("route-unavailable", isUnavailable);
    if (node.tagName?.toLowerCase() === "button") node.disabled = isUnavailable;
    if (isUnavailable) node.setAttribute("aria-disabled", "true");
    else node.removeAttribute("aria-disabled");
    if (isOrigin) node.setAttribute("aria-current", "Origin A selected");
    else if (isDestination) node.setAttribute("aria-current", "Destination B selected");
    else node.removeAttribute("aria-current");
  });
}

function cancelPendingRouteScene() {
  if (navigationState.pendingStep) {
    beginNavigation("floor");
    const displayed = allLevels.find(level => level.level_id === currentScene?.level.level_id);
    if (displayed) selectFloorControls(displayed);
  }
}

function clearRoute(clearEndpoints = true) {
  requestGeneration += 1;
  navigationState.roomRevision += 1;
  cancelPendingRouteScene();
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
  if (navigationState.sceneStatus !== "loading") restoreRenderedFloor();
  renderRouteOverlay(currentScene?.level.level_id);
  if (clearEndpoints) {
    routeOrigin.value = "";
    routeDestination.value = "";
    routeSelection = "empty";
    availabilityGeneration += 1;
    routeAvailability = null;
    routeAvailabilityOrigin = "";
    routeAvailabilityProfile = "";
    settleRouteAvailability();
    settleRouteAvailability = () => {};
    routeAvailabilitySettled = Promise.resolve();
    routeAvailabilityPendingOrigin = "";
    routeAvailabilityPendingProfile = "";
    renderDestinationOptions();
    setAvailabilityState("empty");
    routeOptionsStatus.textContent = "Choose a starting room to see mapped connections.";
  }
  updateEndpointStates();
}

async function activateRouteEndpoint(unitId, focusMap = false) {
  document.querySelector("#directions-panel").open = true;
  if (routeSelection === "complete" || routeSelection === "failed") {
    const retainedOrigin = routeOrigin.value;
    clearRoute(false);
    routeDestination.value = "";
    routeSelection = retainedOrigin ? "origin_selected" : "empty";
    updateEndpointStates();
  }
  if (routeSelection === "empty" || !routeOrigin.value) {
    retainEndpointOption(routeOrigin, unitId);
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
    const pendingOrigin = routeOrigin.value;
    const pendingProfile = routeProfile.value;
    while (routeAvailabilityPendingOrigin === pendingOrigin
      && routeAvailabilityPendingProfile === pendingProfile) {
      const pendingAvailability = routeAvailabilitySettled;
      await pendingAvailability;
      if (routeOrigin.value !== pendingOrigin || routeProfile.value !== pendingProfile) return;
      if (routeAvailabilitySettled === pendingAvailability) break;
    }
    const hasCurrentAvailability = routeAvailability instanceof Map
      && routeAvailabilityOrigin === routeOrigin.value
      && routeAvailabilityProfile === routeProfile.value;
    if (hasCurrentAvailability && routeAvailability.get(unitId) !== "connected") {
      setStatus(`${roomLabel(unitId)} has no mapped connection from ${roomLabel(routeOrigin.value)}. Choose a highlighted room, or Clear to choose another start.`);
      routeSelection = "origin_selected";
      updateEndpointStates();
      return;
    }
    retainEndpointOption(routeDestination, unitId);
    routeDestination.value = unitId;
    routeSelection = "request_pending";
    updateEndpointStates();
    const generation = ++requestGeneration;
    const origin = routeOrigin.value;
    const profile = routeProfile.value;
    void selectUnit(unitId, focusMap);
    await requestRoute(origin, unitId, profile, generation);
  }
}

function selectLandmark(item, marker) {
  navigationState.roomRevision += 1;
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
  navigationState.displayedLevelId = scene.level.level_id;
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

  document.querySelector("#room-filter").value = "";
  renderRoomList();
  updateEndpointStates();
  viewingFloor.textContent = `Viewing ${floorLabel(scene.level.level_id)}`;
  viewingFloor.dataset.levelId = scene.level.level_id;
  setStatus(`${floorLabel(scene.level.level_id)} · ${scene.units.length} rooms`);
  updateGuidanceControls();
  fitMap(mapFit);
}

function renderRoomList() {
  if (!currentScene) return;
  const query = document.querySelector("#room-filter").value.trim().toLocaleLowerCase();
  const rooms = currentScene.units.filter(item =>
    `${item.room_id || ""} ${item.use_type || ""}`.toLocaleLowerCase().includes(query));
  const buttons = rooms.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.room_id || item.use_type || "Unnamed room";
    button.dataset.unitId = item.unit_id;
    button.addEventListener("click", () => activateRouteEndpoint(item.unit_id, true));
    return button;
  });
  roomList.replaceChildren(...buttons);
  if (!buttons.length) {
    const empty = document.createElement("p");
    empty.textContent = currentScene.units.length ? "No rooms match this search." : "No rooms are recorded on this floor. Try another floor.";
    roomList.append(empty);
  }
  document.querySelector("#room-count").textContent = `${rooms.length} of ${currentScene.units.length}`;
  updateEndpointStates();
}

async function loadScene() {
  const level = activeLevel();
  if (!level) return false;
  showFloorContext();
  const generation = ++sceneGeneration;
  navigationState.sceneStatus = "loading";
  navigationState.sceneError = null;
  retryScene.hidden = true;
  floorMap.setAttribute("aria-busy", "true");
  const retained = currentScene ? ` Showing ${floorLabel(currentScene.level.level_id)} until ready.` : "";
  setStatus(`Loading ${floorLabel(level.level_id)}…${retained}`, true);
  updateGuidanceControls();
  try {
    const scene = await request(`/demo/v1/levels/${encodeURIComponent(level.level_id)}/scene`);
    if (generation !== sceneGeneration) return false;
    if (scene.level?.level_id !== level.level_id) throw new Error("The returned floor does not match the requested floor");
    navigationState.sceneStatus = "ready";
    navigationState.displayedLevelId = level.level_id;
    floorMap.setAttribute("aria-busy", "false");
    renderScene(scene);
    return true;
  } catch (error) {
    if (generation !== sceneGeneration) return false;
    navigationState.sceneStatus = "error";
    navigationState.sceneError = error.message;
    navigationState.pendingStep = null;
    floorMap.setAttribute("aria-busy", "false");
    retryScene.hidden = false;
    retryScene.textContent = `Retry ${floorLabel(level.level_id)}`;
    manualPreview = Boolean(guidanceStep());
    previewVisitId = null;
    updateGuidanceControls();
    renderRouteOverlay(currentScene?.level.level_id);
    const showing = currentScene ? ` Still showing ${floorLabel(currentScene.level.level_id)}.` : " No floor is displayed.";
    setStatus(`Could not load ${floorLabel(level.level_id)}: ${error.message}.${showing}`, true);
    return false;
  }
}

function activeLevel() {
  return allLevels.find(level => level.level_id === navigationState.requestedLevelId
    && level.facility_id === navigationState.facilityId);
}

function updateFacilities() {
  facilitySelect.replaceChildren(...[...facilitiesById.values()].map(facility => option(
    facility.facility_id, `${facility.code || "Building"} · ${facility.name || facility.facility_id}`,
  )));
  facilitySelect.value = navigationState.facilityId || "";
}

function populateFloorOptions() {
  const levels = allLevels.filter(level => level.facility_id === navigationState.facilityId);
  levelSelect.replaceChildren(...levels.map(level => option(level.level_id, `Floor ${level.short_name || "not named"}`)));
  levelSelect.value = navigationState.requestedLevelId || "";
  levelSelect.disabled = levels.length === 0;
  openFloor.disabled = levels.length === 0;
  renderQuickNavigation();
}

function selectBuildingControls(facilityId) {
  if (!facilitiesById.has(facilityId)) return;
  const levels = allLevels.filter(level => level.facility_id === facilityId);
  const remembered = navigationState.rememberedLevels.get(facilityId);
  const level = levels.find(item => item.level_id === remembered)
    || levels.find(item => item.vertical_order === 0) || levels[0];
  navigationState.facilityId = facilityId;
  navigationState.requestedLevelId = level?.level_id || null;
  if (level) navigationState.rememberedLevels.set(facilityId, level.level_id);
  updateFacilities();
  populateFloorOptions();
  renderRouteCatalog();
}

function initializeFloorControls(levels) {
  allLevels = levels;
  const first = levels.find(level => level.vertical_order === 0) || levels[0];
  selectBuildingControls(first?.facility_id || facilitiesById.keys().next().value);
}

function selectFloorControls(level) {
  navigationState.facilityId = level.facility_id;
  navigationState.requestedLevelId = level.level_id;
  navigationState.rememberedLevels.set(level.facility_id, level.level_id);
  updateFacilities();
  populateFloorOptions();
  if (navigationState.context !== "route") renderRouteCatalog();
  if (routeOrigin.value && routeSelection === "origin_selected") {
    refreshRouteOptions(routeOrigin.value, routeProfile.value);
  }
}

async function selectLevel(levelId) {
  const level = allLevels.find(item => item.level_id === levelId);
  if (!level) return false;
  showFloorContext();
  selectFloorControls(level);
  if (currentScene?.level.level_id === levelId) {
    sceneGeneration += 1;
    navigationState.displayedLevelId = levelId;
    navigationState.sceneStatus = "ready";
    navigationState.sceneError = null;
    retryScene.hidden = true;
    floorMap.setAttribute("aria-busy", "false");
    renderRouteOverlay(levelId);
    updateGuidanceControls();
    fitMap(mapFit);
    setStatus(`${floorLabel(levelId)} · ${currentScene.units?.length || 0} rooms`);
    return true;
  }
  return loadScene();
}

function floorLabel(levelId) {
  const level = allLevels.find((item) => item.level_id === levelId);
  if (!level) return "Floor not recorded";
  const facility = facilitiesById.get(level.facility_id);
  return [facility?.code, level.short_name].filter(Boolean).join(" ") || "Unnamed floor";
}

function restoreRenderedFloor() {
  if (!currentScene) {
    viewingFloor.textContent = "Floor plan not loaded";
    if (viewingFloor.dataset) delete viewingFloor.dataset.levelId;
    setStatus("Choose a floor to load its map.");
    return;
  }
  navigationState.displayedLevelId = currentScene.level.level_id;
  viewingFloor.textContent = `Viewing ${floorLabel(currentScene.level.level_id)}`;
  viewingFloor.dataset.levelId = currentScene.level.level_id;
  setStatus(`${floorLabel(currentScene.level.level_id)} · ${currentScene.units?.length || 0} rooms`);
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
  const hasRouteMessage = ["pending", "error"].includes(routeUiState)
    || Boolean(activeRoute?.guidance && !step);
  document.querySelector(".current-step").hidden = !step && !hasRouteMessage;
  const pending = Boolean(navigationState.pendingStep) || navigationState.sceneStatus === "loading";
  stepPrevious.disabled = pending || !step || activeStep === 0;
  stepNext.disabled = pending || !step || activeStep === guidance.steps.length - 1;
  returnToRoute.hidden = !step || (!manualPreview && !floorView.hidden);
  stepPosition.textContent = step ? `Step ${activeStep + 1} of ${guidance.steps.length} · ${floorLabel(step.level_id)}` : "Choose a route";
  currentInstruction.textContent = step?.instruction || (activeRoute?.guidance && !activeRoute.guidance.steps.length
    ? unavailableGuidanceMessage : ["error", "pending"].includes(routeUiState)
      ? routeStatus.textContent : "Select a starting room and destination to see directions.");
  if (step?.level_id && step.level_id !== navigationState.displayedLevelId) {
    if (navigationState.pendingStep?.index === activeStep) {
      currentInstruction.textContent = `Loading ${floorLabel(step.level_id)} for the selected instruction…`;
      stepPosition.textContent = `Loading route floor · ${floorLabel(step.level_id)}`;
    } else if (navigationState.sceneStatus === "error") {
      currentInstruction.textContent = `Route floor not loaded. Preview only: ${step.instruction}`;
    }
  }
  floorPreview.hidden = !step || !manualPreview;
  transitionViews.hidden = !step?.transition_id;
  if (!step) return;
  previewMessage.textContent = `You are previewing ${floorLabel(currentScene?.level.level_id)}. Selected step: ${floorLabel(step.level_id)}.`;
  routeSteps.querySelectorAll("button").forEach((node) => {
    const selected = node.dataset.stepId === step.step_id;
    node.classList.toggle("active", selected);
    if (selected) node.setAttribute("aria-current", "step");
    else node.removeAttribute("aria-current");
  });
  floorJourney.querySelectorAll("button").forEach((node) => {
    const visit = guidance.visits.find((item) => item.visit_id === node.dataset.visitId);
    const selected = visit?.visit_id === (previewVisitId || step.visit_id)
      && visit?.level_id === currentScene?.level.level_id;
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
  const route = activeRoute;
  const index = route?.guidance?.steps.findIndex((step) => step.step_id === stepId);
  if (index === undefined || index < 0) return;
  beginNavigation("route");
  const intent = navigationState.intentRevision;
  const step = route.guidance.steps[index];
  navigationState.pendingStep = { route, index, intent };
  // A marker alone gives no useful walking context. Initial directions also
  // retain the full floor route while selecting the first instruction.
  mapFit = cameraMode === "step" && step.geometry_ids.length ? "step" : "route";
  updateGuidanceControls();
  if (!step.level_id) {
    const displayed = allLevels.find(level => level.level_id === currentScene?.level.level_id);
    if (displayed) selectFloorControls(displayed);
    restoreRenderedFloor();
  }
  const loaded = step.level_id ? await selectLevel(step.level_id) : true;
  if (!loaded || activeRoute !== route || intent !== navigationState.intentRevision) return;
  navigationState.pendingStep = null;
  activeStep = index;
  manualPreview = false;
  previewVisitId = null;
  updateGuidanceControls();
  renderRouteOverlay(currentScene?.level.level_id);
  fitMap(mapFit);
}

async function previewFloor(levelId, visitId = null) {
  if (!allLevels.some(level => level.level_id === levelId)) return;
  beginNavigation("floor");
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

function renderRoute(body, { follow = true } = {}) {
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
    routeStatus.textContent = "This demo needs an update before directions can be displayed.";
    setRouteState("error");
    updateGuidanceControls();
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
    const firstStep = guidance.steps.find(step => step.visit_id === visit.visit_id);
    button.disabled = !visit.level_id || !firstStep;
    button.addEventListener("click", () => {
      if (firstStep) return selectGuidanceStep(firstStep.step_id, "route");
    });
    floorJourney.append(button);
  });
  if (follow) selectGuidanceStep(guidance.steps[0].step_id, "route");
  else {
    manualPreview = true;
    updateGuidanceControls();
    renderRouteOverlay(currentScene?.level.level_id);
  }
}

async function requestRoute(origin, destination, profile, generation) {
  document.querySelector("#directions-panel").open = true;
  cancelPendingRouteScene();
  const navigationIntent = navigationState.intentRevision;
  activeRoute = null;
  manualPreview = false;
  previewVisitId = null;
  routeSteps.replaceChildren();
  floorJourney.replaceChildren();
  routeDiagnostics.textContent = "Route request in progress.";
  updateGuidanceControls();
  if (navigationState.sceneStatus !== "loading") restoreRenderedFloor();
  renderRouteOverlay(currentScene?.level.level_id);
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
  updateGuidanceControls();
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
    routeSelection = "complete";
    renderRoute(body, { follow: navigationIntent === navigationState.intentRevision });
  } catch (error) {
    if (generation !== requestGeneration) return;
    const body = error.payload || { status: 500, code: error.message, profile: profile };
    if (!body.profile) body.profile = profile;
    routeSelection = "failed";
    renderRoute(body, { follow: navigationIntent === navigationState.intentRevision });
  }
}

function setAvailabilityState(state, origin = "", profile = "") {
  routeOptionsStatus.setAttribute?.("data-state", state);
  routeOptionsStatus.setAttribute?.("data-origin-unit-id", origin);
  routeOptionsStatus.setAttribute?.("data-profile", profile);
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
    children.push(...routeUnits.filter((unit) => unit.level_id === navigationState.requestedLevelId).map((unit) => makeOption(unit)));
  } else {
    const connected = routeUnits.filter((unit) => availability.get(unit.unit_id) === "connected");
    if (connected.length) {
      const group = document.createElement("optgroup");
      group.label = `Mapped destinations (${connected.length})`;
      group.dataset.availability = "connected";
      group.append(...connected.map((unit) => makeOption(unit, "connected")));
      children.push(group);
    }
    // Retain only explicit endpoint values needed by Swap or an assistant result.
    const startingRoom = routeUnits.find((item) => item.unit_id === origin);
    if (startingRoom) {
      const node = makeOption(startingRoom);
      node.textContent += " · starting room";
      children.push(node);
    }
  }
  routeDestination.replaceChildren(...children);
  if (selected && routeUnits.some(unit => unit.unit_id === selected)
    && !Array.from(routeDestination.querySelectorAll("option")).some(node => node.value === selected)) {
    const selectedRoom = routeUnits.find(unit => unit.unit_id === selected);
    const node = makeOption(selectedRoom);
    node.textContent += " · selected";
    routeDestination.append(node);
  }
  routeDestination.value = selected;
}

function renderRouteCatalog() {
  if (!routeUnits.length) return;
  const selected = routeOrigin.value;
  const units = routeUnits.filter(unit => unit.level_id === navigationState.requestedLevelId);
  const children = [option("", "Select start A")];
  const floors = allLevels.filter(level => level.level_id === navigationState.requestedLevelId);
  floors.forEach(level => {
    const onFloor = units.filter(unit => unit.level_id === level.level_id);
    if (!onFloor.length) return;
    const group = document.createElement("optgroup");
    group.label = floorLabel(level.level_id);
    group.append(...onFloor.map(unit => option(unit.unit_id, unit.room_id || "Unnamed room")));
    children.push(group);
  });
  if (selected && !units.some(unit => unit.unit_id === selected)) {
    const unit = routeUnits.find(item => item.unit_id === selected);
    if (unit) children.push(option(unit.unit_id, `${unit.room_id} · current start`));
  }
  routeOrigin.replaceChildren(...children);
  routeOrigin.value = selected;
  const availability = routeAvailability instanceof Map
    && routeAvailabilityOrigin === selected
    && routeAvailabilityProfile === routeProfile.value
    ? routeAvailability : null;
  renderDestinationOptions(availability, selected);
}

function retainEndpointOption(select, unitId) {
  if (!unitId || Array.from(select.querySelectorAll("option")).some(node => node.value === unitId)) return;
  const unit = routeUnits.find(item => item.unit_id === unitId);
  if (unit) select.append(option(unit.unit_id, `${unit.room_id || "Unnamed room"} · ${floorLabel(unit.level_id)}`));
}

async function refreshRouteOptions(origin = routeOrigin.value, profile = routeProfile.value) {
  const generation = ++availabilityGeneration;
  settleRouteAvailability();
  settleRouteAvailability = () => {};
  routeAvailabilitySettled = Promise.resolve();
  routeAvailabilityPendingOrigin = "";
  routeAvailabilityPendingProfile = "";
  routeAvailability = null;
  routeAvailabilityOrigin = "";
  routeAvailabilityProfile = "";
  renderDestinationOptions();
  updateEndpointStates();
  if (!origin || !routeUnits.some((unit) => unit.unit_id === origin)) {
    setAvailabilityState("empty");
    routeOptionsStatus.textContent = "Choose a starting room to see mapped connections.";
    return;
  }
  setAvailabilityState("pending", origin, profile);
  routeAvailabilityPendingOrigin = origin;
  routeAvailabilityPendingProfile = profile;
  let finishAvailability;
  const settled = new Promise((resolve) => { finishAvailability = resolve; });
  routeAvailabilitySettled = settled;
  settleRouteAvailability = finishAvailability;
  routeOptionsStatus.textContent = "Checking mapped connections...";
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
    routeAvailability = availability;
    routeAvailabilityOrigin = origin;
    routeAvailabilityProfile = profile;
    renderDestinationOptions(availability, origin);
    updateEndpointStates();
    const connected = body.destinations.filter((item) => item.availability === "connected").length;
    const sameAnchor = body.destinations.filter((item) => item.availability === "same_anchor").length;
    let help = `${connected} mapped ${connected === 1 ? "destination" : "destinations"} from ${roomLabel(origin)}. Choose destination B.`;
    if (!connected) help = `0 mapped routes from ${roomLabel(origin)} with this route option. The map has no connected destination with a walking path.`;
    if (sameAnchor) help += ` ${sameAnchor} ${sameAnchor === 1 ? "room shares" : "rooms share"} the starting route point, with no walking path drawn.`;
    const chosen = availability.get(routeDestination.value);
    if (chosen === "disconnected") help += " Your selected destination has no mapped connection.";
    if (chosen === "endpoint_unavailable") help += " Your selected destination has no mapped route point.";
    help += " Only mapped destinations are offered. Door connections and accessibility are not verified.";
    routeOptionsStatus.textContent = help;
    setAvailabilityState("ready", origin, profile);
  } catch (error) {
    if (generation !== availabilityGeneration || routeOrigin.value !== origin || routeProfile.value !== profile) return;
    renderDestinationOptions();
    routeAvailability = null;
    routeAvailabilityOrigin = "";
    routeAvailabilityProfile = "";
    updateEndpointStates();
    const reason = error.payload?.code === "endpoint_unavailable"
      ? "This starting room has no mapped route point."
      : "Connection choices are unavailable right now.";
    routeOptionsStatus.textContent = `${reason} You can still choose any room and request directions.`;
    setAvailabilityState("error", origin, profile);
  } finally {
    finishAvailability();
    if (routeAvailabilitySettled === settled) {
      routeAvailabilityPendingOrigin = "";
      routeAvailabilityPendingProfile = "";
      settleRouteAvailability = () => {};
    }
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
  retainEndpointOption(routeOrigin, destination);
  retainEndpointOption(routeDestination, origin);
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
  const assistantRevision = ++navigationState.assistantRevision;
  assistantResponse.textContent = "Checking normalized artifact records…";
  assistantEvidence.textContent = "";
  const directionRequest = parseExactDirections(assistantInput.value);
  if (directionRequest) {
    const origin = resolveRouteUnitId(directionRequest.origin);
    const destination = resolveRouteUnitId(directionRequest.destination);
    retainEndpointOption(routeOrigin, origin);
    retainEndpointOption(routeDestination, destination);
    routeOrigin.value = origin;
    routeDestination.value = destination;
    routeProfile.value = directionRequest.profile;
    updateEndpointStates();
    assistantResponse.textContent = "Rendering the deterministic route result below.";
    await requestRoute(origin, destination, directionRequest.profile, ++requestGeneration);
    return;
  }
  const assistantIntent = navigationState.intentRevision;
  const assistantRoomRevision = navigationState.roomRevision;
  try {
    const body = await request("/demo/v1/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: assistantInput.value,
        facility_id: navigationState.facilityId,
        level_id: activeLevel()?.level_id,
      }),
    });
    if (assistantRevision !== navigationState.assistantRevision || assistantIntent !== navigationState.intentRevision || assistantRoomRevision !== navigationState.roomRevision) return;
    assistantResponse.textContent = body.text;
    assistantEvidence.textContent = body.evidence?.length ? `Evidence: ${body.evidence.map((item) => `${item.layer} · ${item.feature_id}`).join("; ")}` : "No artifact record cited.";
    const unit = body.entities?.find((item) => item.type === "unit");
    if (unit && unit.level_id === currentScene?.level.level_id) await selectUnit(unit.unit_id, true);
  } catch (error) {
    if (assistantRevision === navigationState.assistantRevision && assistantIntent === navigationState.intentRevision && assistantRoomRevision === navigationState.roomRevision) assistantResponse.textContent = error.message;
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

facilitySelect.addEventListener("change", () => {
  const facilityId = facilitySelect.value;
  if (!facilitiesById.has(facilityId)) return;
  if (floorView.hidden) selectCampusBuilding(facilityId);
  else {
    selectBuildingControls(facilityId);
    if (activeLevel()) return previewFloor(activeLevel().level_id);
    selectCampusBuilding(facilityId);
  }
});
levelSelect.addEventListener("change", () => {
  const levelId = levelSelect.value;
  if (allLevels.some(level => level.level_id === levelId && level.facility_id === navigationState.facilityId)) return previewFloor(levelId);
});
openFloor.addEventListener("click", () => previewFloor(navigationState.requestedLevelId));
retryScene.addEventListener("click", () => previewFloor(navigationState.requestedLevelId));
returnToRoute.addEventListener("click", () => {
  const step = guidanceStep();
  if (step) return selectGuidanceStep(step.step_id, "route");
});

document.querySelector("#show-campus").addEventListener("click", () => {
  const wasBuilding = campusFacilityId !== null;
  campusFacilityId = null;
  document.querySelector("#campus-details").replaceChildren();
  document.querySelector("#campus-reset").textContent = "Show all buildings";
  showCampus();
  renderCampusBuildings();
  document.querySelectorAll(".campus-shape").forEach(shape => shape.classList.toggle("selected", false));
  if (wasBuilding) resetCampusCamera();
});
campusSearch.addEventListener("input", renderCampusBuildings);
document.querySelector("#room-filter").addEventListener("input", renderRoomList);
document.querySelector("#campus-zoom-in").addEventListener("click", () => zoomCampus(1 / 1.5));
document.querySelector("#campus-zoom-out").addEventListener("click", () => zoomCampus(1.5));
document.querySelector("#campus-reset").addEventListener("click", resetCampusCamera);

async function initialize() {
  try {
    const [health, facilities, levels, campus] = await Promise.all([
      request("/demo/v1/health"),
      request("/demo/v1/facilities"),
      request("/demo/v1/levels"),
      request("/demo/v1/campus"),
    ]);
    artifactHash.textContent = health.artifact_sha256;
    graphHash.textContent = health.provenance?.graph_sha256 || "Unavailable";
    facilitiesById = new Map(
      facilities.facilities.map((facility) => [facility.facility_id, facility]),
    );
    initializeFloorControls(levels.levels);
    campusData = campus;
    renderCampus();
    const units = await request("/demo/v1/units");
    routeUnits = units.units;
    renderRouteCatalog();
  } catch (error) {
    setStatus(error.message);
    document.querySelector("#campus-status").textContent = `Campus pilot unavailable: ${error.message}`;
  }
}

initialize();
