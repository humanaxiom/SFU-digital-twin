"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { activateButton, verifyGuidance } = require("./guidance.cjs");
const { createBrowserGate, strand } = require("./room-search.cjs");

const { baseUrl, outputDir, proc, cdp, result, typeQuery, pickNativeOption, screenshot } =
  createBrowserGate("asb-overview");
const quote = JSON.stringify;
const facilityId = "ROOMFINDER_BURNABY_038";
const buildingName = "Applied Sciences Building";
const missingUnit = `${facilityId}_UNMAPPED_TEST_UNIT`;
const shape = `#campus-map path[data-campus-facility-id=${quote(facilityId)}]`;
const listItem = `#campus-buildings [data-campus-facility-id=${quote(facilityId)}]`;
const draftState = `[
  document.querySelector('#route-origin').value,
  document.querySelector('#route-destination').value,
  document.querySelector('#route-profile').value,
  document.querySelector('#route-committed-identity').textContent
]`;

async function api(endpoint, status = 200, options) {
  const response = await fetch(new URL(`/demo/v1/${endpoint}`, baseUrl), options);
  assert.equal(response.status, status, endpoint);
  return response.json();
}

function jsonPost(body) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: quote(body) };
}

async function assertSelected() {
  await cdp.wait(`document.querySelector(${quote(shape)}).classList.contains('selected')`);
  const { details, ...state } = await cdp.evaluate(`({
    open: !document.querySelector('#campus-view').hidden,
    facility: document.querySelector('#facility-select').value,
    disabled: document.querySelector('#level-select').disabled,
    floors: document.querySelector('#level-select').options.length,
    campusFloors: document.querySelectorAll('#campus-details [data-campus-level-id]').length,
    details: document.querySelector('#campus-details').textContent
  })`);
  assert.deepEqual(state, {
    open: true, facility: facilityId, disabled: true, floors: 0, campusFloors: 0,
  });
  assert.ok(details.includes(`ASB · ${buildingName}`));
  assert.match(details, /overview only/i);
}

async function startPilotRoute(rooms, width) {
  await activateButton(cdp, `#building-buttons [data-building-id=${quote(strand.facility)}]`, "Enter");
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId === ${quote(strand.floor1000)}
    && document.querySelector('#floor-map').getAttribute('aria-busy') === 'false'`);
  for (const [room, action] of [[rooms[0], "#room-start-here"], [rooms[1], "#room-directions-here"]]) {
    await activateButton(cdp, `#room-list [data-unit-id=${quote(room.unit_id)}]`);
    await activateButton(cdp, action, "Enter");
  }
  await cdp.wait(`document.querySelector('#route-destination').value === ${quote(rooms[1].unit_id)}`);
  await activateButton(cdp, "#route-submit", "Enter");
  await cdp.wait("window.__routes[0]?.body && document.querySelector('#route-request-status').dataset.state === 'success'");
  const [{ status, body }] = await cdp.evaluate("window.__routes");
  assert.equal(status, 200);
  assert.equal(body.origin.unit_id, rooms[0].unit_id);
  assert.equal(body.destination.unit_id, rooms[1].unit_id);
  assert.equal(body.profile, "default");
  assert.ok(body.edge_ids.length > 0 && body.network_distance_m > 0);
  verifyGuidance(body);
  result.routeCalls.push({ width, status, origin: body.origin.unit_id, destination: body.destination.unit_id });
  return { edgeIds: body.edge_ids, distanceM: body.network_distance_m };
}

function assertPath(actual, geometry, origin) {
  const ring = geometry.coordinates[0];
  assert.equal(geometry.type, "Polygon");
  assert.equal(geometry.coordinates.length, 1);
  const parts = actual.match(/[ML][^MLZ]+|Z/g);
  assert.equal(parts.length, ring.length + 1);
  assert.equal(parts.at(-1), "Z");
  ring.forEach(([x, y], index) => {
    const segment = parts[index];
    assert.equal(segment[0], index === 0 ? "M" : "L");
    assert.deepEqual(segment.slice(1).trim().split(/\s+/).map(Number), [x - origin[0], origin[1] - y]);
  });
}

async function exerciseViewport(width, campus, asb, rooms) {
  await cdp.call("Emulation.setDeviceMetricsOverride", {
    width, height: width > 500 ? 1000 : 844, deviceScaleFactor: 1, mobile: width < 500,
  });
  await cdp.call("Page.navigate", { url: baseUrl });
  await cdp.wait(`document.querySelector(${quote(shape)})`);
  assert.equal(await cdp.evaluate("document.querySelectorAll('#campus-map .campus-shape').length"), 4);
  assert.match(await cdp.evaluate(`document.querySelector(${quote(shape)}).getAttribute('aria-label')`), /overview only/i);
  assertPath(await cdp.evaluate(`document.querySelector(${quote(shape)}).getAttribute('d')`), asb.geometry, campus.bounds);
  assert.ok(await cdp.evaluate(`document.documentElement.scrollWidth <= ${width} &&
    [...document.querySelectorAll('#campus-map .campus-shape')].every(node => {
      const bounds = node.getBoundingClientRect(), map = node.ownerSVGElement.getBoundingClientRect();
      return bounds.width > 0 && bounds.height > 0 && bounds.left >= map.left - 1 && bounds.right <= map.right + 1
        && bounds.top >= map.top - 1 && bounds.bottom <= map.bottom + 1;
    })`), "The four visible footprints fit within the overview map");
  await screenshot(`campus-${width}.png`);

  const route = await startPilotRoute(rooms, width);
  const draft = await cdp.evaluate(draftState);
  assert.match(draft[3], /SH1001C.*SH1003/);
  await activateButton(cdp, "#show-campus", "Enter");
  const scenesBefore = await cdp.evaluate("window.__scenes.length");
  await activateButton(cdp, shape, width === 1440 ? null : " ");
  await assertSelected();
  if (!(await cdp.evaluate("document.querySelector('#building-search').open"))) {
    await activateButton(cdp, "#building-search summary", "Enter");
  }
  const searchByWidth = { 1440: "ASB", 390: buildingName, 320: "Applied Science Building" };
  await typeQuery("#campus-search", searchByWidth[width]);
  assert.equal(await cdp.evaluate("document.querySelectorAll('#campus-buildings button').length"), 1);
  await activateButton(cdp, listItem, "Enter");
  await assertSelected();
  assert.deepEqual(await cdp.evaluate(draftState), draft);
  assert.equal(await cdp.evaluate("window.__routes.length"), 1);
  assert.equal(await cdp.evaluate("window.__scenes.length"), scenesBefore);
  await cdp.evaluate("document.querySelector('#campus-details').scrollIntoView({block:'end'})");
  await screenshot(`asb-${width}.png`);

  if (!(await cdp.evaluate("document.querySelector('#route-origin-finder').open"))) {
    await activateButton(cdp, "#route-origin-finder summary", "Enter");
  }
  await pickNativeOption("#route-origin-search-building", facilityId);
  assert.ok(await cdp.evaluate(`document.querySelector('#route-origin-search-floor').disabled &&
    document.querySelector('#route-origin-search-results').disabled &&
    document.querySelector('#route-origin-search-results').options.length === 0 &&
    document.querySelector('#route-origin-search-choose').disabled`), "ASB has no selectable route rooms");
  await activateButton(cdp, "#return-to-route", "Enter");
  await cdp.wait(`!document.querySelector('#floor-view').hidden &&
    document.querySelector('#viewing-floor').dataset.levelId === ${quote(strand.floor1000)} &&
    document.querySelector('#floor-map').getAttribute('aria-busy') === 'false'`);
  assert.deepEqual(await cdp.evaluate(draftState), draft);
  assert.equal(await cdp.evaluate("window.__routes.length"), 1);
  assert.deepEqual(await cdp.evaluate("window.__errors"), []);
  result.cases.push({ width, input: width === 1440 ? "pointer" : "Space", route });
}

async function main() {
  result.browser = { container: process.env.HOSTNAME, chromium: (await cdp.call("Browser.getVersion")).product };
  const { targetId } = await cdp.call("Target.createTarget", { url: "about:blank" });
  cdp.sessionId = (await cdp.call("Target.attachToTarget", { targetId, flatten: true })).sessionId;
  await cdp.call("Page.enable");
  const campus = await api("campus");
  const health = await api("health");
  result.artifact = health.provenance;
  result.campus = { scope: campus.scope, facilityIds: campus.facilities.map(item => item.facility_id) };
  assert.equal(campus.scope, "burnaby-overview-preview");
  assert.equal(campus.campus_inventory_complete, false);
  assert.equal(campus.facilities.length, 4);
  assert.deepEqual(campus.facilities.map(item => item.code).sort(), ["AQ", "ASB", "ECC", "SH"]);
  assert.equal(campus.provenance.indoor_artifact.artifact_sha256, health.artifact_sha256);
  const evidence = JSON.parse(fs.readFileSync(process.env.WAYFINDING_ASB_FOOTPRINT || "/asb/footprint.json", "utf8"));
  const asb = campus.facilities.find(item => item.facility_id === facilityId);
  assert.ok(asb, "The exact RoomFinder identity is represented");
  assert.equal(asb.name, buildingName);
  assert.equal(asb.coverage, "overview_only");
  assert.equal(asb.geometry_status, "available");
  assert.equal(asb.verified_building_destination, false);
  assert.equal(asb.outdoor_routing, "unavailable");
  assert.deepEqual(asb.known_entrances, []);
  assert.deepEqual(asb.levels, []);
  assert.deepEqual(asb.bounds, evidence.footprint_26910.bounds);
  assert.deepEqual(asb.geometry, evidence.footprint_26910.geometry);
  assert.deepEqual(asb.provenance, {
    source_url: evidence.source_url,
    source_name: evidence.native_response.features[0].attributes.Name,
    directory_url: "https://www.sfu.ca/fs/campus-maps/directory-of-buildings/applied-sciences-building.html",
    screen_sha256: evidence.screen_sha256,
    native_response_sha256: evidence.native_response_sha256,
  });
  assert.deepEqual(campus.provenance.overview_footprints, [asb.provenance]);
  const facilities = await api("facilities");
  assert.deepEqual(facilities.provenance, campus.provenance);
  assert.equal(facilities.count, 4);
  assert.deepEqual(facilities.facilities.find(item => item.facility_id === facilityId), {
    facility_id: facilityId, code: "ASB", name: buildingName, provenance: asb.provenance,
  });
  const assistant = await api("assistant", 200, jsonPost({ message: "List buildings" }));
  const indoorIds = campus.facilities.filter(item => item.facility_id !== facilityId).map(item => item.facility_id);
  assert.deepEqual(assistant.entities.map(item => item.facility_id), indoorIds);
  assert.equal(assistant.artifact_sha256, health.artifact_sha256);
  result.campus.screenSha256 = evidence.screen_sha256;
  result.campus.assistantFacilityIds = indoorIds;

  const levels = await api(`levels?facility_id=${facilityId}`);
  assert.deepEqual(levels.levels, []);
  const { units } = await api("units");
  const rooms = ["SH1001C", "SH1003"].map(id => units.find(room => room.room_id === id));
  assert.ok(rooms.every(room => room?.level_id === strand.floor1000));
  assert.ok(units.every(unit => !unit.unit_id.startsWith(facilityId)));
  await api(`units/${missingUnit}`, 404);
  const negative = await api("route", 404, jsonPost({
    origin: { unit_id: rooms[0].unit_id }, destination: { unit_id: missingUnit }, profile: "default",
  }));
  assert.equal(negative.code, "unknown_endpoint");
  result.unsupported = { unitId: missingUnit, unitHTTP: 404, routeHTTP: 404, routeCode: negative.code, floors: levels.count };

  await cdp.call("Page.addScriptToEvaluateOnNewDocument", { source: `
    window.__routes = []; window.__scenes = []; window.__errors = [];
    addEventListener('error', e => window.__errors.push(e.message));
    addEventListener('unhandledrejection', e => window.__errors.push(String(e.reason)));
    const realFetch = window.fetch.bind(window);
    window.fetch = async (url, init) => {
      if (typeof url === 'string' && url.endsWith('/scene')) window.__scenes.push(url);
      const response = await realFetch(url, init);
      if (url === '/demo/v1/route' && init?.method === 'POST') {
        window.__routes.push({ status: response.status, body: await response.clone().json() });
      }
      return response;
    };
  ` });
  for (const width of [1440, 390, 320]) await exerciseViewport(width, campus, asb, rooms);
  const route = result.cases[0].route;
  assert.ok(result.cases.every(item => JSON.stringify(item.route) === JSON.stringify(route)));
  const fixtures = require("/workspace/docs/reports/DT-015-demo-routes.json");
  if (health.artifact_sha256 === fixtures.artifact_hashes["wayfinding.gpkg"] &&
      health.provenance.graph_sha256 === fixtures.artifact_hashes["graph_contracted.pkl"]) {
    assert.deepEqual(route.edgeIds, fixtures.fixtures.strand_corridor.edge_ids);
    assert.equal(route.distanceM, fixtures.fixtures.strand_corridor.network_distance_m);
  }
  result.checks.push("Verified the exact ASB source outline and 4-building viewport geometry");
  result.checks.push("API distinguishes mixed preview provenance from artifact-only assistant evidence");
  result.checks.push("Selected ASB by pointer, keyboard, code and name without loading floors or submitting routes");
  result.checks.push("Retained the real SH1001C to SH1003 route and draft through ASB inspection");
  result.checks.push("Real API rejected the unmapped ASB unit and route with HTTP 404");
}

main().then(() => {
  result.status = "passed";
}, async error => {
  result.status = "failed";
  result.error = error.stack;
  process.exitCode = 1;
  await screenshot("failure.png").catch(() => {});
}).finally(() => {
  result.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(outputDir, "results.json"), quote(result, null, 2));
  console.log(quote(result, null, 2));
  proc.kill();
});
