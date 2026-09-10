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
let facilitiesById = new Map();
let levelsByOrder = new Map();
let allLevels = [];
let activeRoute = null;
let activeStep = 0;

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
  const drawLine = (line, close) => line.map((point, index) => `${index ? "L" : "M"}${point[0]} ${-point[1]}`).join(" ") + (close ? " Z" : "");
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
  floorMap.querySelectorAll("g").forEach((node) => node.remove());
  const points = coordinates(scene.level.geometry);
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const padding = 4;
  const minX = Math.min(...xs) - padding;
  const maxX = Math.max(...xs) + padding;
  const minY = Math.min(...ys) - padding;
  const maxY = Math.max(...ys) + padding;
  floorMap.setAttribute("viewBox", `${minX} ${-maxY} ${maxX - minX} ${maxY - minY}`);

  const layers = ["level", "details", "units", "landmarks"].map(() => element("g"));
  layers[0].append(svgPath(scene.level, "level-shape"));
  scene.details.forEach((item) => layers[1].append(svgPath(item, "detail-shape")));
  scene.units.forEach((item) => {
    const shape = svgPath(item, "unit-shape");
    shape.dataset.unitId = item.unit_id;
    shape.setAttribute("tabindex", "0");
    shape.setAttribute("role", "button");
    shape.setAttribute("aria-label", `Room ${item.room_id || item.unit_id}, ${item.use_type || "use not recorded"}`);
    shape.addEventListener("click", () => selectUnit(item.unit_id));
    shape.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectUnit(item.unit_id);
      }
    });
    layers[2].append(shape);
  });
  scene.landmarks.forEach((item) => {
    const point = coordinates(item.geometry)[0];
    if (!point) return;
    const marker = element("circle", { cx: point[0], cy: -point[1], r: 1.3, class: "landmark-shape", tabindex: 0, "aria-label": item.category || "Landmark" });
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
    button.addEventListener("click", () => selectUnit(item.unit_id, true));
    return button;
  });
  roomList.replaceChildren(...buttons);
  setStatus(`${scene.level.short_name}: ${scene.units.length} searchable rooms, ${scene.landmarks.length} landmarks.`);
}

async function loadScene() {
  const level = activeLevel();
  if (!level) return;
  setStatus("Loading artifact geometry…");
  try {
    renderScene(await request(`/demo/v1/levels/${encodeURIComponent(level.level_id)}/scene`));
  } catch (error) {
    setStatus(error.message);
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
    return option(String(verticalOrder), `Order ${verticalOrder} · ${labels.join(" · ")}`);
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
  await loadScene();
}

function renderRouteOverlay(levelId) {
  const overlay = document.querySelector("#route-overlay");
  if (!overlay) return;
  overlay.replaceChildren();
  if (!activeRoute?.geometries) return;
  activeRoute.geometries
    .filter((item) => item.level_id === levelId)
    .forEach((item) => overlay.append(svgPath(item, "route-segment")));
}

function renderRoute(body) {
  activeRoute = body.status === 200 ? body : null;
  activeStep = 0;
  routeAccessibility.hidden = body.profile !== "elevator_only";
  routeSteps.replaceChildren();
  if (body.status !== 200) {
    routeStatus.textContent = `${body.code}: no measured graph route is available for these anchors.`;
    renderRouteOverlay(activeLevel()?.level_id);
    return;
  }
  routeStatus.textContent = `${body.network_distance_m.toFixed(1)} m graph-only route over ${body.edge_ids.length} measured edges. Origin attachment ${body.origin.attachment_distance_m.toFixed(1)} m; destination attachment ${body.destination.attachment_distance_m.toFixed(1)} m.`;
  const items = body.steps.map((step, index) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = step.instruction;
    button.classList.toggle("active", index === activeStep);
    button.addEventListener("click", async () => {
      activeStep = index;
      routeSteps.querySelectorAll("button").forEach((node, position) => node.classList.toggle("active", position === activeStep));
      await selectLevel(step.level_id);
    });
    item.append(button);
    return item;
  });
  routeSteps.replaceChildren(...items);
  selectLevel(body.steps[0].level_id);
}

routeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  routeStatus.textContent = "Computing the deterministic graph route...";
  try {
    const body = await request("/demo/v1/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: { unit_id: routeOrigin.value },
        destination: { unit_id: routeDestination.value },
        profile: routeProfile.value,
      }),
    });
    renderRoute(body);
  } catch (error) {
    renderRoute(error.payload || { status: 500, code: error.message });
  }
});

routeProfile.addEventListener("change", () => {
  routeAccessibility.hidden = true;
});

assistantForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  assistantResponse.textContent = "Checking normalized artifact records…";
  assistantEvidence.textContent = "";
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

facilitySelect.addEventListener("change", loadScene);
levelSelect.addEventListener("change", async () => {
  updateFacilities();
  await loadScene();
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
    const routeOptions = units.units.map((unit) => option(
      unit.unit_id,
      `${unit.room_id || unit.unit_id} · ${unit.level_id}`,
    ));
    routeOrigin.replaceChildren(...routeOptions.map((item) => item.cloneNode(true)));
    routeDestination.replaceChildren(...routeOptions);
    if (routeDestination.options.length > 1) routeDestination.selectedIndex = 1;
    await loadScene();
  } catch (error) {
    setStatus(error.message);
  }
}

initialize();