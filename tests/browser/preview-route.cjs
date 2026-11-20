"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createBrowserGate, strand, origin, destination, defaultRoute } = require("./room-search.cjs");

const {
  baseUrl, outputDir, proc, cdp, result, pointerClick, key, field, typeQuery,
  pickNativeOption, assertIdle, resultClick, activateChoice, prepareViewport, screenshot,
} = createBrowserGate("preview-route");

const quote = JSON.stringify;
const forward = defaultRoute;
const reverse = {origin: forward.destination, destination: forward.origin, profile: "default"};
const elevator = {...forward, profile: "elevator_only"};
const levels = [strand.floor1000, "SFU_BURNABY_STRAND_2000", strand.floor3000];
const [forwardOrigin, forwardDestination] = ["SH1036", "SH3050.1"];
const escapedDestination = "SH3050\\.1";
const forwardIdentity = new RegExp(forwardOrigin + ".*" + escapedDestination);
const reverseIdentity = new RegExp(escapedDestination + ".*" + forwardOrigin);
const routeCount = "window.__routeCalls.length";

const check = description => result.checks.push(description);

async function activate(selector, keyboard = false) {
  if (!keyboard) return pointerClick(selector);
  assert.ok(await cdp.evaluate(`(() => {
    const control = document.querySelector(${quote(selector)});
    control?.focus();
    return !!control && document.activeElement === control;
  })()`), `Keyboard focus reaches ${selector}`);
  await key("Enter");
}

async function selectSearchRoom(selector, query, id) {
  await typeQuery(selector, query);
  await resultClick(`${selector}-results`, id);
  await activateChoice(selector, false);
}

async function switchFloor(level) {
  await pointerClick(`#floor-buttons [data-level-id=${quote(level)}]`);
  await cdp.wait(`document.querySelector('#viewing-floor')?.dataset.levelId === ${quote(level)}
    && document.querySelector('#floor-map')?.getAttribute('aria-busy') === 'false'`);
}

async function inspectRoom(unitId, roomId, keyboard = false) {
  const selector = `.unit-shape[data-unit-id=${quote(unitId)}]`;
  if (keyboard) {
    await activate(selector, true);
  } else {
    const point = await cdp.evaluate(`(() => {
      const node = document.querySelector(${quote(selector)});
      node.scrollIntoView({block: 'center', inline: 'center'});
      const rect = node.getBoundingClientRect();
      for (let i = 1; i < 20; i++) for (let j = 1; j < 20; j++) {
        const x = rect.left + rect.width * i / 20;
        const y = rect.top + rect.height * j / 20;
        if (document.elementFromPoint(x, y) === node) return {x, y};
      }
      throw new Error('No visible pointer hit point inside the room');
    })()`);
    for (const type of ["mousePressed", "mouseReleased"]) {
      await cdp.call("Input.dispatchMouseEvent", {type, ...point, button: "left", clickCount: 1});
    }
  }
  await cdp.wait(`document.querySelector('#unit-details dd')?.textContent === ${quote(roomId)}
    && Array.from(document.querySelectorAll('#unit-details dt')).some(item => item.textContent === "Recorded category")`);
}

function waitOptions(originId, profile = "default", state = "ready") {
  return cdp.wait(`document.querySelector('#route-options-status')?.dataset.state === ${quote(state)}
    && document.querySelector('#route-options-status').dataset.originUnitId === ${quote(originId)}
    && document.querySelector('#route-options-status').dataset.profile === ${quote(profile)}`);
}

async function assertCommitted(payload, identity) {
  for (const selector of ["#route-committed-identity", "#map-route-identity"]) {
    assert.equal(await field(selector, "checkVisibility()"), true, `${selector} labels the displayed route`);
    const label = await field(selector, "textContent");
    assert.match(label, identity, `${selector} shows the committed From and To in order`);
    assert.match(label, /stairs or elevators/i, `${selector} shows the committed profile`);
    assert.equal(await field(selector, "dataset.originUnitId"), payload.origin.unit_id);
    assert.equal(await field(selector, "dataset.destinationUnitId"), payload.destination.unit_id);
    assert.equal(await field(selector, "dataset.profile"), payload.profile);
  }
}

async function assertUnapplied() {
  assert.equal(await field("#route-draft-status", "checkVisibility()"), true);
  assert.match(await field("#route-draft-status", "textContent"), /route changes not applied/i);
}

function routeVisual() {
  return cdp.evaluate(`({
    floor: document.querySelector('#viewing-floor').dataset.levelId,
    instruction: document.querySelector('#current-instruction').textContent,
    step: document.querySelector('#step-position').textContent,
    summaryText: document.querySelector('#route-status').textContent,
    summaryBackground: getComputedStyle(document.querySelector('#route-status')).backgroundColor,
    endpoints: Array.from(document.querySelectorAll('.unit-shape.route-origin, .unit-shape.route-destination'),
      item => [item.dataset.unitId, item.getAttribute('aria-current')]),
    geometry: Array.from(document.querySelectorAll('#route-overlay .route-segment'),
      item => [item.dataset.geometryId, item.getAttribute('d')])
  })`);
}

function expectedSvgPath({type, coordinates}, [originX, originY]) {
  assert.ok(["LineString", "MultiLineString"].includes(type), "Guidance pieces contain line geometry");
  const lines = type === "LineString" ? [coordinates] : coordinates;
  return lines.map(line => line.map(([x, y], index) =>
    `${index ? "L" : "M"}${x - originX} ${-(y - originY)}`).join(" ")).join(" ");
}

async function assertSuccess(index, payload, visitLevels, identity) {
  await cdp.wait(`window.__routeCalls[${index}]?.delivered && document.querySelector('#route-status').dataset.state === 'success'
    && document.querySelector('#viewing-floor').dataset.levelId === ${quote(visitLevels[0])}
    && document.querySelector('#floor-map').getAttribute('aria-busy') === 'false'`);
  const call = await cdp.evaluate(`window.__routeCalls[${index}]`);
  assert.equal(call.status, 200);
  assert.deepEqual(call.payload, payload);
  assert.deepEqual(call.visitLevels, visitLevels);
  assert.ok(call.geometryPointCount > 0, "Route contains recorded guidance coordinates");
  assert.ok(call.edgeIds.length > 0, "Route has recorded graph edges");
  assert.equal(await cdp.evaluate(routeCount), index + 1, "Each preview sends one route request");
  await assertCommitted(payload, identity);
  const visual = await routeVisual();
  const mapOrigin = await cdp.evaluate(`["originX", "originY"].map(key => Number(document.querySelector("#floor-map").dataset[key]))`);
  const geometries = await cdp.evaluate(`window.__routeGeometries[${index}].filter(item => item.level_id === ${quote(visual.floor)})`);
  assert.deepEqual(visual.geometry, geometries.map(item => [item.geometry_id, expectedSvgPath(item.geometry, mapOrigin)]),
    "Displayed SVG paths exactly match the returned guidance coordinates");
  assert.notEqual(visual.geometry.length, 0);
  return visual;
}

async function holdPreview(index, keyboard = false) {
  await cdp.evaluate("window.__holdNextRoute = true");
  await activate("#route-submit", keyboard);
  await cdp.wait(`window.__routeCalls[${index}]?.held && typeof window.__releaseRoute === 'function'`);
}

async function releasePreview(index) {
  await cdp.evaluate("window.__releaseRoute()");
  await cdp.wait(`window.__routeCalls[${index}]?.consumed`);
  await cdp.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
}

function snapshotInspection() {
  return cdp.evaluate(`({
    building: document.querySelector('#facility-select').value,
    floor: document.querySelector('#viewing-floor').dataset.levelId,
    selectedRoom: document.querySelector('#unit-details').textContent,
    camera: document.querySelector('#floor-map').getAttribute('viewBox')
  })`);
}

async function desktopDraftAndRaces() {
  await prepareViewport(1440);
  await selectSearchRoom(origin, forwardOrigin, strand.origin);
  await waitOptions(strand.origin);
  await pointerClick("#route-destination-finder > summary");
  await selectSearchRoom(destination, forwardDestination, strand.destination);
  assert.deepEqual(await cdp.evaluate("window.__routeCalls"), [], "Choosing a To room must wait for Preview route");
  await assertIdle(strand.origin, strand.destination, 0);
  assert.equal(await field("#route-submit", "textContent.trim()"), "Preview route");
  check("1440px pointer search chooses exact From and To without sending a route request");

  await pointerClick("#route-submit");
  const originalMap = await assertSuccess(0, forward, levels, forwardIdentity);
  check("The first explicit preview shows the real three-floor Strand route with committed labels and matching map paths");

  // A failed availability check makes the route outcome unknown. Preview then reaches the real route API.
  await cdp.evaluate('window.__failOptionsProfile = "elevator_only"');
  await pickNativeOption("#route-profile", "elevator_only");
  await waitOptions(strand.origin, "elevator_only", "error");
  await assertIdle(strand.origin, strand.destination, 1);
  await assertUnapplied();
  await assertCommitted(forward, forwardIdentity);
  assert.equal(await field("#route-accessibility", "checkVisibility()"), false);
  assert.deepEqual(await routeVisual(), originalMap);

  await holdPreview(1);
  assert.equal(await field("#route-request-status", "dataset.state"), "pending");
  assert.equal(await field("#route-status", "dataset.state"), "success", "Pending replacement preserves the committed summary's success styling");
  const pending = await field("#route-request-status", "textContent");
  assert.match(pending, forwardIdentity);
  assert.match(pending, /elevator only/i);
  assert.deepEqual(await routeVisual(), originalMap);
  await releasePreview(1);
  await cdp.wait("document.querySelector('#route-request-status').dataset.state === 'error'");
  assert.equal(await field("#route-status", "dataset.state"), "success", "Failed replacement preserves the committed summary's success styling");
  const failure = await field("#route-request-status", "textContent");
  assert.match(failure, forwardIdentity);
  assert.match(failure, /elevator only/i);
  assert.match(failure, /no mapped route without stairs/i);
  assert.match(failure, /previous route remains displayed/i);
  const failed = await cdp.evaluate("window.__routeCalls[1]");
  assert.deepEqual(failed.payload, elevator);
  assert.equal(failed.status, 409);
  assert.equal(failed.code, "no_elevator_only_route");
  await assertUnapplied();
  await assertCommitted(forward, forwardIdentity);
  assert.deepEqual(await routeVisual(), originalMap);
  await screenshot("desktop-failed-replacement.png");
  check("Pending and failed Elevator only replacement identifies its own rooms and profile while the original default map and instructions stay unchanged");

  await pickNativeOption("#route-profile", "default");
  await waitOptions(strand.origin);
  await pointerClick("#route-swap");
  await waitOptions(strand.destination);
  await assertIdle(strand.destination, strand.origin, 2);
  await holdPreview(2);
  await pointerClick("#route-swap");
  await waitOptions(strand.origin);
  await assertIdle(strand.origin, strand.destination, 3);
  await assertCommitted(forward, forwardIdentity);
  await releasePreview(2);
  await assertSuccess(2, reverse, [...levels].reverse(), reverseIdentity);
  await assertUnapplied();
  await assertIdle(strand.origin, strand.destination, 3);
  check("Swap edits both rooms locally, and a pending preview commits its submitted rooms while preserving the later Swap edit");

  await switchFloor(strand.floor1000);
  await inspectRoom(strand.origin, forwardOrigin);
  await pointerClick("#zoom-in");
  const roomAndCamera = await snapshotInspection();
  await holdPreview(3);
  await pointerClick("#route-clear");
  await releasePreview(3);
  await assertIdle("", "", 4);
  assert.equal(await field("#route-profile", "value"), "default");
  assert.equal(await field("#route-status", "dataset.state"), "empty");
  assert.equal(await field("#route-options-status", "dataset.state"), "empty");
  assert.doesNotMatch(await field("#route-draft-status", "textContent"), /route changes not applied/i);
  assert.equal(await field("#map-route-identity", "textContent"), "No committed route.");
  assert.equal(await field("#route-request-status", "dataset.state"), "empty");
  const cleared = await routeVisual();
  assert.deepEqual(cleared.geometry, []);
  assert.deepEqual(cleared.endpoints, []);
  assert.equal(await field("#route-steps", "children.length"), 0);
  assert.equal(await field("#floor-journey", "children.length"), 0);
  assert.deepEqual(await snapshotInspection(), roomAndCamera);
  check("Clear during preview prevents a late success from restoring the route and keeps the inspected room, floor, and zoom");
  await saveBrowserCase(1440, "pointer");
}

async function inspectRoomWithPendingDetails() {
  const alternate = "SFU_BURNABY_STRAND_1000_110";
  await cdp.evaluate(`window.__holdRoomDetailsFor = ${quote(alternate)}`);
  await pointerClick(`#room-list [data-unit-id=${quote(alternate)}]`);
  await cdp.wait("typeof window.__releaseRoomDetails === 'function'");
  const inspector = ".facts";
  assert.equal(await field(inspector, "open"), true);
  assert.equal(await field("#unit-details dd", "textContent"), "SH110");
  assert.equal(await field("#unit-details > div:nth-child(2) dd", "textContent"), "SH 1000");
  const detailsStatus = `document.querySelector('.facts').textContent + document.querySelector('#map-status').textContent`;
  assert.match(await cdp.evaluate(detailsStatus), /loading.*details|details.*loading/i);
  assert.doesNotMatch(await field("#unit-details", "textContent"), /recorded category|source use type/i);
  assert.equal(await field(`.unit-shape[data-unit-id=${quote(strand.origin)}]`, "classList.contains('selected')"), false);
  assert.equal(await field(`.unit-shape[data-unit-id=${quote(alternate)}]`, "matches(':focus')"), true,
    "The room-list action moves focus to the newly inspected map room immediately");
  await assertIdle("", "", 0);

  assert.equal(await field("#room-start-here", "dataset.unitId"), alternate);
  await activate("#room-start-here", true);
  await waitOptions(alternate);
  await assertIdle(alternate, "", 0);

  await cdp.evaluate("window.__releaseRoomDetails()");
  await cdp.wait(`/details (?:are )?unavailable|could not load room details/i.test(${detailsStatus})`);
  assert.equal(await field("#room-start-here", "matches(':focus')"), true,
    "Room details complete without taking focus from the latest action");
  assert.equal(await field("#unit-details dd", "textContent"), "SH110");
  assert.equal(await field("#room-start-here", "dataset.unitId"), alternate);

  await inspectRoom(strand.origin, forwardOrigin, true);
  await assertIdle(alternate, "", 0);
  check("390px inspection shows the new exact room while its details load or fail, and its explicit Start here action uses that room");
}

async function mobileEndpointActions() {
  await prepareViewport(390);
  await pointerClick(`#building-buttons [data-building-id=${quote(strand.facility)}]`);
  await switchFloor(strand.floor1000);
  await inspectRoom(strand.origin, forwardOrigin, true);
  await assertIdle("", "", 0);
  await inspectRoomWithPendingDetails();
  await activate("#room-start-here", true);
  await waitOptions(strand.origin);
  await assertIdle(strand.origin, "", 0);

  await switchFloor(strand.floor100);
  await inspectRoom(strand.disconnected, "SH110", true);
  assert.equal(await field("#room-directions-here", "disabled"), true, "An unsupported destination still opens room details");
  await assertIdle(strand.origin, "", 0);

  await switchFloor(strand.floor3000);
  await inspectRoom(strand.destination, forwardDestination, true);
  await assertIdle(strand.origin, "", 0);
  await activate("#room-directions-here", true);
  await assertIdle(strand.origin, strand.destination, 0);
  await activate("#route-submit", true);
  const originalMap = await assertSuccess(0, forward, levels, forwardIdentity);
  check("390px keyboard SVG inspection and explicit Start here / Directions here choose only draft rooms, including unsupported room inspection");

  await pickNativeOption("#route-profile", "elevator_only");
  await waitOptions(strand.origin, "elevator_only");
  assert.match(await field("#route-options-status", "textContent"), /selected destination has no mapped connection/i);
  await activate("#route-submit", true);
  await cdp.wait("document.querySelector('#route-request-status').dataset.state === 'error'");
  const blocked = await field("#route-request-status", "textContent");
  assert.match(blocked, forwardIdentity);
  assert.match(blocked, /elevator only.*no mapped connection/i);
  await assertIdle(strand.origin, strand.destination, 1);
  await assertCommitted(forward, forwardIdentity);
  await assertUnapplied();
  assert.deepEqual(await routeVisual(), originalMap);
  check("A genuinely disconnected Elevator only draft stays visible, cannot send a route request, and leaves the default route intact");

  await pointerClick(".assistant > summary");
  await typeQuery("#assistant-input", `directions from ${forwardDestination} to ${forwardOrigin}`);
  await key("Enter");
  await waitOptions(strand.destination);
  await cdp.wait("/preview route/i.test(document.querySelector('#assistant-response').textContent)");
  await assertIdle(strand.destination, strand.origin, 1);
  assert.equal(await field("#route-profile", "value"), "default");
  await assertCommitted(forward, forwardIdentity);
  await assertUnapplied();
  await activate("#route-submit", true);
  await assertSuccess(1, reverse, [...levels].reverse(), reverseIdentity);
  check("Assistant directions resolve exact reverse rooms into the draft and use the same explicit keyboard Preview route action");
  await screenshot("mobile-directions.png");
  await cdp.evaluate(`(async () => {
    document.querySelector("#floor-map").scrollIntoView({block: "center"});
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  })()`);
  await screenshot("mobile-map.png");
  await saveBrowserCase(390, "keyboard");
}

async function narrowViewport() {
  await prepareViewport(320);
  assert.ok(await cdp.evaluate(`document.documentElement.scrollWidth <= 321 &&
    ['#route-submit', '#route-swap', '#route-clear', '#route-profile'].every(selector => {
      const rect = document.querySelector(selector).getBoundingClientRect();
      return rect.left >= 0 && rect.right <= 321 && rect.width > 0;
    })`), "Preview, Swap, Clear and profile fit the 320px layout");
  await screenshot("narrow-directions.png");
  check("Preview, Swap, Clear and profile fit the 320px layout");
}

async function saveBrowserCase(width, input) {
  assert.deepEqual(await cdp.evaluate("window.__errors"), [], "Browser interaction emits no uncaught errors");
  result.cases.push({width, input, routeCalls: await cdp.evaluate("window.__routeCalls")});
}

async function verifyApi() {
  const request = async (endpoint, init) => {
    const response = await fetch(new URL(`/demo/v1/${endpoint}`, baseUrl), init);
    return {status: response.status, body: await response.json()};
  };
  const health = await request("health");
  assert.equal(health.status, 200);
  assert.equal(health.body.capabilities.routing, true);
  result.api = {provenance: health.body.provenance, fixtures: []};
  for (const [payload, status, expectedLevels] of [
    [forward, 200, levels], [reverse, 200, [...levels].reverse()], [elevator, 409, null],
  ]) {
    const response = await request("route", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    assert.equal(response.status, status);
    if (expectedLevels) {
      assert.deepEqual(response.body.guidance.visits.map(visit => visit.level_id), expectedLevels);
      for (const testCase of result.cases) for (const call of testCase.routeCalls) {
        if (call.status === 200 && quote(call.payload) === quote(payload)) {
          assert.deepEqual(call.edgeIds, response.body.edge_ids, "Browser and direct API use identical graph edges");
        }
      }
    } else {
      assert.equal(response.body.code, "no_elevator_only_route");
    }
    result.api.fixtures.push({payload, status, visitLevels: expectedLevels, code: response.body.code, distanceM: response.body.network_distance_m});
  }
  check("Direct API verifies both route directions with exact graph-edge parity and the Elevator only HTTP 409");
}

async function initialize() {
  result.browser = {container: process.env.HOSTNAME, chromium: (await cdp.call("Browser.getVersion")).product};
  const {targetId} = await cdp.call("Target.createTarget", {url: "about:blank"});
  const {sessionId} = await cdp.call("Target.attachToTarget", {targetId, flatten: true});
  cdp.sessionId = sessionId;
  await cdp.call("Page.enable");
  await cdp.call("Page.addScriptToEvaluateOnNewDocument", {source: `
    window.__routeCalls = [];
    window.__routeGeometries = [];
    window.__errors = [];
    addEventListener("error", event => window.__errors.push(String(event.message)));
    addEventListener("unhandledrejection", event => window.__errors.push(String(event.reason)));
    const realFetch = window.fetch.bind(window);
    window.fetch = async (url, init) => {
      if (window.__holdRoomDetailsFor && url === "/demo/v1/units/" + encodeURIComponent(window.__holdRoomDetailsFor)) {
        window.__holdRoomDetailsFor = null;
        await new Promise(resolve => { window.__releaseRoomDetails = resolve; });
        return new Response(JSON.stringify({message: "Browser gate simulates unavailable room details"}), {
          status: 503, headers: {"Content-Type": "application/json"}
        });
      }
      if (url.startsWith("/demo/v1/route-options?") && window.__failOptionsProfile &&
          new URL(url, window.location.origin).searchParams.get("profile") === window.__failOptionsProfile) {
        return new Response(JSON.stringify({message: "Browser gate simulates an unavailable connection check"}), {
          status: 503, headers: {"Content-Type": "application/json"}
        });
      }
      if (url !== "/demo/v1/route" || init?.method !== "POST") return realFetch(url, init);
      const held = !!window.__holdNextRoute;
      window.__holdNextRoute = false;
      const call = {payload: JSON.parse(init.body)};
      const index = window.__routeCalls.push(call) - 1;
      // Hold the real response and deliver it even if the UI attempts network cancellation.
      const response = await realFetch(url, held ? {...init, signal: undefined} : init);
      const body = await response.clone().json();
      call.status = response.status;
      call.code = body.code;
      call.edgeIds = body.edge_ids;
      call.visitLevels = body.guidance?.visits?.map(visit => visit.level_id);
      call.geometryPointCount = body.guidance?.geometries?.reduce((sum, item) => sum + item.geometry.coordinates.length, 0);
      window.__routeGeometries[index] = body.guidance?.geometries || [];
      if (held) {
        const readBody = response.json.bind(response);
        response.json = async () => {
          const body = await readBody();
          call.consumed = true;
          return body;
        };
        call.held = true;
        await new Promise(resolve => { window.__releaseRoute = resolve; });
      }
      call.delivered = true;
      return response;
    };
  `});
}

async function main() {
  try {
    await initialize();
    await desktopDraftAndRaces();
    await mobileEndpointActions();
    await narrowViewport();
    await verifyApi();
    result.status = "passed";
  } catch (error) {
    result.status = "failed";
    result.error = error.stack;
    result.routeCalls = await cdp.evaluate("window.__routeCalls").catch(() => []);
    if (result.routeCalls.length > 0) result.lastRouteStatus = await field("#route-request-status", "textContent").catch(() => "");
    process.exitCode = 1;
    await screenshot("failure.png").catch(() => {});
  } finally {
    result.finishedAt = new Date().toISOString();
    fs.writeFileSync(path.join(outputDir, "results.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify({status: result.status, checks: result.checks, error: result.error, lastRouteStatus: result.lastRouteStatus}, null, 2));
    proc.kill();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
  proc.kill();
});
