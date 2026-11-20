"use strict";

// Regression coverage for choosing room A, changing floors immediately, and
// choosing room B with visible building/floor/room controls. Run only in the
// pinned Playwright container; this intentionally exercises the deployed UI.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chooseRoomInspection } = require("./guidance.cjs");

assert.ok(fs.existsSync("/.dockerenv"), "Run this browser gate through Docker.");

const baseUrl = process.env.WAYFINDING_BROWSER_BASE_URL || "http://127.0.0.1:8080";
const runLabel = process.env.WAYFINDING_BROWSER_RUN_LABEL || "crossfloor-room-picking";
const outputDir = path.join("/workspace/build/navigation-review", runLabel);
fs.mkdirSync(outputDir, { recursive: true });

class Cdp {
  constructor(proc) {
    this.proc = proc;
    this.nextId = 1;
    this.pending = new Map();
    let buffer = "";
    const fail = error => {
      for (const pending of this.pending.values()) pending.reject(error);
      this.pending.clear();
    };
    proc.on("error", fail);
    proc.on("exit", code => fail(new Error(`Chromium exited: ${code}`)));
    proc.stdio[3].on("error", fail);
    proc.stdio[4].setEncoding("utf8");
    proc.stdio[4].on("data", chunk => {
      buffer += chunk;
      const messages = buffer.split("\0");
      buffer = messages.pop();
      for (const raw of messages) {
        if (!raw) continue;
        const message = JSON.parse(raw);
        const pending = this.pending.get(message.id);
        if (!pending) continue;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(JSON.stringify(message.error)));
        else pending.resolve(message.result);
      }
    });
  }

  call(method, params = {}, sessionId = this.sessionId) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 15000);
      this.pending.set(id, {
        resolve: value => { clearTimeout(timer); resolve(value); },
        reject: error => { clearTimeout(timer); reject(error); },
      });
      this.proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0");
    });
  }

  async evaluate(expression) {
    const response = await this.call("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    }
    return response.result?.value;
  }

  async wait(expression, timeout = 30000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (await this.evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Timed out: ${expression}`);
  }
}

const quote = JSON.stringify;
const proc = spawn(
  "/ms-playwright/chromium-1140/chrome-linux/chrome",
  ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--remote-debugging-pipe", "about:blank"],
  { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] },
);
const cdp = new Cdp(proc);
const result = {
  startedAt: new Date().toISOString(),
  baseUrl,
  status: "running",
  checks: [],
  cases: [],
  routeCalls: [],
};

async function pointerClick(selector) {
  const point = await cdp.evaluate(`(() => {
    const node = document.querySelector(${quote(selector)});
    if (!node) throw new Error('Missing control ' + ${quote(selector)});
    node.scrollIntoView({block: 'center', inline: 'center'});
    const rect = node.getBoundingClientRect();
    if (!rect.width || !rect.height || !node.checkVisibility?.()) throw new Error('Hidden control ' + ${quote(selector)});
    return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
  })()`);
  await cdp.call("Input.dispatchMouseEvent", { type: "mousePressed", ...point, button: "left", clickCount: 1 });
  await cdp.call("Input.dispatchMouseEvent", { type: "mouseReleased", ...point, button: "left", clickCount: 1 });
}

async function sceneReady(levelId) {
  await cdp.wait(`document.querySelector('#viewing-floor')?.dataset.levelId===${quote(levelId)}
    && document.querySelector('#floor-map')?.getAttribute('aria-busy')==='false'
    && !document.querySelector('#map-status')?.textContent.includes('Loading')`);
}

async function clearRoute() {
  if (await cdp.evaluate("!document.querySelector('#route-origin')?.value && document.querySelector('#route-status')?.dataset.state==='empty'")) return;
  await pointerClick("#route-clear");
  await cdp.wait("document.querySelector('#route-status')?.dataset.state==='empty' && !document.querySelector('#route-origin')?.value");
}

async function openBuilding(facilityId) {
  await pointerClick(`#building-buttons [data-building-id=${quote(facilityId)}]`);
  await cdp.wait(`document.querySelector('#facility-select')?.value===${quote(facilityId)}`);
}

async function clickRoom(levelId, unitId) {
  await pointerClick(`#floor-buttons [data-level-id=${quote(levelId)}]`);
  await sceneReady(levelId);
  await pointerClick(`#room-list [data-unit-id=${quote(unitId)}]`);
}

async function routeCallFor(destinationId) {
  await cdp.wait(`window.__routeCalls?.some(call => call.done && call.payload?.destination?.unit_id===${quote(destinationId)})`);
  return cdp.evaluate(`window.__routeCalls.filter(call => call.payload?.destination?.unit_id===${quote(destinationId)})`);
}

async function routeState() {
  return cdp.evaluate(`({
    origin: document.querySelector('#route-origin')?.value || '',
    destination: document.querySelector('#route-destination')?.value || '',
    routeState: document.querySelector('#route-status')?.dataset.state || '',
    routeText: document.querySelector('#route-status')?.textContent || '',
    viewedFloor: document.querySelector('#viewing-floor')?.dataset.levelId || '',
    optionsState: document.querySelector('#route-options-status')?.dataset.state || '',
  })`);
}

async function routeCatalog(originId, profile = "default") {
  return cdp.evaluate(`(async () => {
    const options = await fetch('/demo/v1/route-options?origin_unit_id=${encodeURIComponent(originId)}&profile=${encodeURIComponent(profile)}').then(response => response.json());
    const units = routeUnits;
    const byUnit = Object.fromEntries(units.map(unit => [unit.unit_id, unit]));
    return {
      options,
      units: byUnit,
      origin: byUnit[${quote(originId)}],
    };
  })()`);
}

async function roomAction(unitId, button, activate = pointerClick) {
  await cdp.wait(`document.querySelector(${quote(button)})?.dataset.unitId===${quote(unitId)}`);
  await activate(button);
}

async function chooseStart(fixture) {
  await clickRoom(fixture.originLevelId, fixture.originId);
  await roomAction(fixture.originId, "#room-start-here");
}

async function previewDestination(unitId, activate = pointerClick) {
  await roomAction(unitId, "#room-directions-here", activate);
  await cdp.wait(`document.querySelector('#route-destination').value===${quote(unitId)}`);
  await activate("#route-submit");
}

async function exerciseSupersededAvailability(fixture) {
  await clearRoute();
  await openBuilding(fixture.facilityId);
  await chooseRoomInspection(cdp);
  await cdp.evaluate("window.__holdRouteOptions=true");
  const before = await cdp.evaluate("window.__routeCalls.length");
  await chooseStart(fixture);
  await cdp.wait("window.__heldRouteOptions.length>0");
  await clickRoom(fixture.destinationLevelId, fixture.destinationId);
  await roomAction(fixture.destinationId, "#room-start-here");
  await cdp.wait(`document.querySelector('#route-origin').value===${quote(fixture.destinationId)} && window.__heldRouteOptions.length>=2`);
  await cdp.evaluate("window.__holdRouteOptions=false; window.__heldRouteOptions.pop()()");
  await cdp.wait(`document.querySelector('#route-options-status').dataset.state==='ready' && document.querySelector('#route-options-status').dataset.originUnitId===${quote(fixture.destinationId)}`);
  await cdp.evaluate("window.__heldRouteOptions.splice(0).forEach(release=>release())");
  await cdp.wait("window.__optionsInFlight===0");
  assert.equal((await routeState()).origin,fixture.destinationId);
  assert.equal(await cdp.evaluate("document.querySelector('#route-options-status').dataset.originUnitId"),fixture.destinationId);
  assert.equal(await cdp.evaluate("window.__routeCalls.length"),before);
  result.checks.push(`${fixture.name}: superseded availability keeps the newer draft origin without routing`);
}

async function keyboardActivate(selector) {
  await cdp.evaluate(`(() => {
    const node = document.querySelector(${quote(selector)});
    if (!node?.checkVisibility?.() || node.disabled) throw new Error('Unavailable keyboard control');
    node.scrollIntoView({block: 'center'});
    node.focus();
  })()`);
  await cdp.call("Input.dispatchKeyEvent", { type: "keyDown", text: "\r", unmodifiedText: "\r", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  await cdp.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
}

async function exerciseClickIntent(fixture, width, keyboard) {
  await cdp.call("Emulation.setDeviceMetricsOverride", { width, height: width === 1440 ? 1000 : 844, deviceScaleFactor: 1, mobile: width < 500 });
  await clearRoute();
  await openBuilding(fixture.facilityId);
  await chooseRoomInspection(cdp);
  await cdp.evaluate("window.__holdRouteResponses=true");
  await chooseStart(fixture);
  await cdp.wait("document.querySelector('#route-options-status').dataset.state==='ready'");
  await pointerClick(`#floor-buttons [data-level-id=${quote(fixture.destinationLevelId)}]`);
  await sceneReady(fixture.destinationLevelId);
  const before = await cdp.evaluate("({posts: window.__routeCalls.length})");
  const activate = keyboard ? keyboardActivate : pointerClick;
  await activate(`#room-list [data-unit-id=${quote(fixture.destinationId)}]`);
  await previewDestination(fixture.destinationId, activate);
  await cdp.wait("window.__heldRouteResponses.length===1");
  before.details = await cdp.evaluate("window.__unitCalls.length");
  await activate(`#floor-buttons [data-level-id=${quote(fixture.explorationLevelId)}]`);
  await sceneReady(fixture.explorationLevelId);
  await cdp.evaluate("window.__holdRouteResponses=false; window.__heldRouteResponses.shift()()");
  await cdp.wait(`window.__routeCalls.length>${before.posts} && window.__routeCalls.at(-1).done
    && document.querySelector('#route-status')?.dataset.state==='success'`);
  const state = await routeState();
  assert.equal(state.viewedFloor, fixture.explorationLevelId, "Delayed B must not steal newer floor navigation");
  assert.equal(state.origin, fixture.originId);
  assert.equal(state.destination, fixture.destinationId);
  assert.equal(await cdp.evaluate(`window.__unitCalls.slice(${before.details}).some(url=>url.endsWith(${quote('/' + encodeURIComponent(fixture.destinationId))}))`), false,
    "Superseded B must not start obsolete room-detail inspection");
  assert.equal(await cdp.evaluate("document.querySelector('#return-to-route').checkVisibility()"), true,
    "Retained route must offer Return to route");
  const screenshot = await cdp.call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(path.join(outputDir, `click-intent-${fixture.name}-${width}.png`), Buffer.from(screenshot.data, "base64"));
  await activate("#return-to-route");
  await sceneReady(fixture.originLevelId);
  assert.equal((await routeState()).routeState, "success", "Return retains the accepted route");
  result.checks.push(`${fixture.name} ${width}px ${keyboard ? 'keyboard' : 'pointer'}: delayed B retains newer floor, suppresses obsolete details, and Return restores route`);
}
async function exerciseBuilding(fixture) {
  await clearRoute();
  await openBuilding(fixture.facilityId);
  await chooseRoomInspection(cdp);
  await chooseStart(fixture);

  // This is deliberately immediate: no route-options readiness wait is allowed
  // between selecting A and changing to the destination floor.
  await pointerClick(`#floor-buttons [data-level-id=${quote(fixture.destinationLevelId)}]`);
  await sceneReady(fixture.destinationLevelId);
  await pointerClick(`#room-list [data-unit-id=${quote(fixture.destinationId)}]`);
  await previewDestination(fixture.destinationId);
  await cdp.wait(`document.querySelector('#route-status')?.dataset.state==='success'
    && document.querySelector('#route-destination')?.value===${quote(fixture.destinationId)}`);
  const successCalls = await routeCallFor(fixture.destinationId);
  assert.ok(successCalls.some(call => call.status === 200 && call.body?.status === 200), `${fixture.name}: fixed cross-floor pair must return HTTP/body 200`);
  const successState = await routeState();
  assert.equal(successState.origin, fixture.originId, `${fixture.name}: fixed pair origin must be retained`);
  assert.equal(successState.destination, fixture.destinationId, `${fixture.name}: fixed pair destination must be retained`);
  result.checks.push(`${fixture.name}: immediate floor switch plus visible room click creates known connected cross-floor route`);

  const replacementCatalog = await routeCatalog(fixture.originId);
  const replacement = replacementCatalog.options.destinations.find(item => (
    item.availability === "connected"
    && item.unit_id !== fixture.destinationId
    && replacementCatalog.units[item.unit_id]?.level_id.startsWith(fixture.facilityId + "_")
    && replacementCatalog.units[item.unit_id]?.level_id !== fixture.originLevelId
  ));
  assert.ok(replacement, `${fixture.name}: fixture needs a second connected destination`);
  const replacementUnit = replacementCatalog.units[replacement.unit_id];

  const beforeCompletedReplacement = await cdp.evaluate("window.__routeCalls.length");
  await clickRoom(replacementUnit.level_id, replacement.unit_id);
  await previewDestination(replacement.unit_id);
  await cdp.wait(`window.__routeCalls.length>${beforeCompletedReplacement}
    && window.__routeCalls.at(-1).done && window.__routeCalls.at(-1).status===200
    && document.querySelector('#route-status')?.dataset.state==='success'
    && document.querySelector('#route-destination')?.value===${quote(replacement.unit_id)}`);
  const completedReplacementState = await routeState();
  assert.equal(completedReplacementState.origin, fixture.originId, `${fixture.name}: completed-route replacement must retain A`);

  await cdp.evaluate("window.__failNextRoute=true");
  const beforeSyntheticFailure = await cdp.evaluate("window.__routeCalls.length");
  await clickRoom(fixture.destinationLevelId, fixture.destinationId);
  await previewDestination(fixture.destinationId);
  await cdp.wait(`window.__routeCalls.length>${beforeSyntheticFailure}
    && window.__routeCalls.at(-1).done && window.__routeCalls.at(-1).status===409
    && document.querySelector('#route-request-status')?.dataset.state==='error'`);
  const failedReplacementState = await routeState();
  assert.equal(failedReplacementState.origin, fixture.originId, `${fixture.name}: failed replacement must retain A`);
  assert.equal(failedReplacementState.destination, fixture.destinationId, `${fixture.name}: failed replacement must retain B`);

  const beforeFailedRetry = await cdp.evaluate("window.__routeCalls.length");
  await clickRoom(replacementUnit.level_id, replacement.unit_id);
  await previewDestination(replacement.unit_id);
  await cdp.wait(`window.__routeCalls.length>${beforeFailedRetry}
    && window.__routeCalls.at(-1).done && window.__routeCalls.at(-1).status===200
    && document.querySelector('#route-status')?.dataset.state==='success'
    && document.querySelector('#route-destination')?.value===${quote(replacement.unit_id)}`);
  const failedRetryState = await routeState();
  assert.equal(failedRetryState.origin, fixture.originId, `${fixture.name}: failed-route retry must retain A`);
  result.checks.push(`${fixture.name}: completed and failed routes replace B while retaining A`);

  // Reset to the same origin, then inspect an actual disconnected destination.
  // It must be visibly disabled and must never submit a doomed route request.
  await clearRoute();
  await chooseStart(fixture);
  await cdp.wait(`document.querySelector('#route-options-status')?.dataset.state==='ready'
    && document.querySelector('#route-origin')?.value===${quote(fixture.originId)}`);
  const catalog = await routeCatalog(fixture.originId);
  const disconnectedChoices = catalog.options.destinations.filter(item => (
    item.availability === "disconnected"
    && catalog.units[item.unit_id]?.level_id
    && catalog.units[item.unit_id].level_id !== fixture.originLevelId
  ));
  const sameBuilding = disconnectedChoices.find(item => (
    catalog.units[item.unit_id].level_id.startsWith(fixture.facilityId + "_")
  ));
  const disconnected = sameBuilding || disconnectedChoices[0];
  assert.ok(disconnected, `${fixture.name}: catalog must include a disconnected destination`);
  const disconnectedUnit = catalog.units[disconnected.unit_id];
  if (!sameBuilding) {
    const disconnectedFacility = await cdp.evaluate(`(async () => {
      const response = await fetch('/demo/v1/levels').then(result => result.json());
      return response.levels.find(level => level.level_id === ${quote(disconnectedUnit.level_id)})?.facility_id;
    })()`);
    assert.ok(disconnectedFacility, `${fixture.name}: disconnected room must have a known building`);
    await openBuilding(disconnectedFacility);
  }

  await pointerClick(`#floor-buttons [data-level-id=${quote(disconnectedUnit.level_id)}]`);
  await sceneReady(disconnectedUnit.level_id);
  const disconnectedSelector = `#room-list [data-unit-id=${quote(disconnected.unit_id)}]`;
  assert.equal(await cdp.evaluate(`document.querySelector(${quote(disconnectedSelector)})?.disabled`), false,
    `${fixture.name}: disconnected rooms remain inspectable`);
  const beforeBlockedClick = await cdp.evaluate("window.__routeCalls.length");
  await pointerClick(disconnectedSelector);
  await cdp.wait(`document.querySelector('#room-directions-here').dataset.unitId===${quote(disconnected.unit_id)} && document.querySelector('#room-directions-here').disabled`);
  await new Promise(resolve => setTimeout(resolve, 150));
  const blockedState = await routeState();
  assert.equal(await cdp.evaluate("window.__routeCalls.length"), beforeBlockedClick,
    `${fixture.name}: disabled destination must not submit a route`);
  assert.equal(blockedState.origin, fixture.originId, `${fixture.name}: blocked destination must retain original A`);
  assert.equal(blockedState.destination, "", `${fixture.name}: blocked destination must not become B`);

  if (!sameBuilding) await openBuilding(fixture.facilityId);
  await clickRoom(fixture.destinationLevelId, fixture.destinationId);
  await previewDestination(fixture.destinationId);
  await cdp.wait(`document.querySelector('#route-status')?.dataset.state==='success'
    && document.querySelector('#route-destination')?.value===${quote(fixture.destinationId)}`);
  const retryCalls = await routeCallFor(fixture.destinationId);
  assert.ok(retryCalls.some(call => call.status === 200 && call.body?.status === 200), `${fixture.name}: connected retry must return HTTP/body 200`);
  const retryState = await routeState();
  assert.equal(retryState.origin, fixture.originId, `${fixture.name}: connected choice must retain original A after a blocked room`);
  assert.equal(retryState.destination, fixture.destinationId, `${fixture.name}: connected choice must become B`);
  result.cases.push({
    name: fixture.name,
    origin: fixture.originId,
    disconnected: disconnected.unit_id,
    connected: fixture.destinationId,
    replacement: replacement.unit_id,
    disconnectedLevel: disconnectedUnit.level_id,
    disconnectedInSameBuilding: Boolean(sameBuilding),
    routeCalls: await cdp.evaluate("window.__routeCalls.slice()"),
  });
  result.checks.push(`${fixture.name}: disconnected rooms can be inspected, and only a mapped destination can be previewed`);
}

async function main() {
  const { targetId } = await cdp.call("Target.createTarget", { url: "about:blank" });
  cdp.sessionId = (await cdp.call("Target.attachToTarget", { targetId, flatten: true })).sessionId;
  await cdp.call("Page.enable");
  await cdp.call("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await cdp.call("Page.addScriptToEvaluateOnNewDocument", { source: `
    window.__errors=[]; window.__routeCalls=[]; window.__failNextRoute=false;
    window.__optionsInFlight=0; window.__holdRouteOptions=false; window.__heldRouteOptions=[]; window.__unitCalls=[]; window.__holdRouteResponses=false; window.__heldRouteResponses=[];
    addEventListener('error', event => __errors.push(String(event.message || event.error)));
    addEventListener('unhandledrejection', event => __errors.push(String(event.reason)));
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const input = args[0], init = args[1] || {};
      const url = String(typeof input === 'string' ? input : input.url);
      const method = String(init.method || input.method || 'GET').toUpperCase();
      if (method === 'GET' && url.includes('/demo/v1/route-options') && window.__holdRouteOptions) {
        window.__optionsInFlight++;
        await new Promise(resolve => window.__heldRouteOptions.push(resolve));
        try { return await originalFetch(...args); } finally { window.__optionsInFlight--; }
      }
      if (method === 'GET' && url.includes('/demo/v1/units/')) window.__unitCalls.push(url);
      let payload = null;
      if (method === 'POST' && url.includes('/demo/v1/route')) {
        try { payload = JSON.parse(init.body || 'null'); } catch (error) { payload = {parseError: String(error)}; }
      }
      let call = null;
      if (method === 'POST' && url.includes('/demo/v1/route')) {
        call = {url, method, payload, status: null, done: false, body: null};
        window.__routeCalls.push(call);
      }
      const failThisRoute = Boolean(call && window.__failNextRoute);
      if (failThisRoute) window.__failNextRoute = false;
      const response = failThisRoute
        ? new Response(JSON.stringify({status:409,code:'disconnected',profile:payload?.profile||'default'}), {status:409,headers:{'Content-Type':'application/json'}})
        : await originalFetch(...args);
      if (call && window.__holdRouteResponses) await new Promise(resolve => window.__heldRouteResponses.push(resolve));
      if (call) {
        call.status = response.status;
        const body = await response.clone().json().catch(() => null);
        call.body = body ? {
          status: body.status,
          code: body.code || null,
          visitLevelIds: body.guidance?.visits?.map(visit => visit.level_id) || [],
        } : null;
        call.done = true;
      }
      return response;
    };
  ` });
  await cdp.call("Page.navigate", { url: baseUrl });
  await cdp.wait("document.querySelectorAll('#building-buttons button').length===3 && document.querySelector('#route-origin')?.options.length>1");

  const fixtures = [
    {
      name: "AQ",
      explorationLevelId: "SFU_BURNABY_QUAD_3000",
      facilityId: "SFU_BURNABY_QUAD",
      originLevelId: "SFU_BURNABY_QUAD_2000",
      originId: "SFU_BURNABY_QUAD_2000_2035.2",
      destinationLevelId: "SFU_BURNABY_QUAD_5000",
      destinationId: "SFU_BURNABY_QUAD_5000_5046",
    },
    {
      name: "SH",
      explorationLevelId: "SFU_BURNABY_STRAND_2000",
      facilityId: "SFU_BURNABY_STRAND",
      originLevelId: "SFU_BURNABY_STRAND_1000",
      originId: "SFU_BURNABY_STRAND_1000_1036",
      destinationLevelId: "SFU_BURNABY_STRAND_3000",
      destinationId: "SFU_BURNABY_STRAND_3000_3050.1",
    },
  ];
  const room = fixtures[0];
  await openBuilding(room.facilityId);
  await chooseRoomInspection(cdp);
  await clickRoom(room.originLevelId, room.originId);
  await cdp.wait("document.querySelector('#unit-details').innerText.includes('2035.2') && document.querySelector('#unit-details').innerText.includes('Physical accessibility')");
  const detailText = await cdp.evaluate("document.querySelector('#unit-details').innerText");
  assert.match(detailText, /physical accessibility/i);
  assert.match(detailText, /unverified/i);
  assert.doesNotMatch(detailText, /destination tag|verified by|verified date/i);
  result.checks.push("AQ2035.2 room details distinguish recorded use from unverified physical accessibility");
  await exerciseClickIntent(fixtures[0], 1440, false);
  await exerciseClickIntent(fixtures[1], 390, true);
  await exerciseClickIntent(fixtures[0], 320, true);
  await clearRoute();
  await openBuilding(room.facilityId);
  await keyboardActivate(`#floor-buttons [data-level-id=${quote(room.originLevelId)}]`);
  await sceneReady(room.originLevelId);
  await keyboardActivate(`#room-list [data-unit-id=${quote(room.originId)}]`);
  await cdp.wait("document.querySelector('.facts').open && document.querySelector('#unit-details').innerText.includes('2035.2') && document.querySelector('#unit-details').innerText.includes('Physical accessibility')");
  const mobileDetails = await cdp.evaluate("document.querySelector('#unit-details').innerText");
  assert.match(mobileDetails, /physical accessibility/i);
  assert.match(mobileDetails, /unverified/i);
  assert.ok(await cdp.evaluate("document.querySelector('#unit-details').scrollWidth <= document.querySelector('#unit-details').clientWidth + 1"));
  result.checks.push("AQ2035.2 room details readable after keyboard selection at 320px");
  await cdp.call("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await exerciseSupersededAvailability(fixtures[0]);
  for (const fixture of fixtures) await exerciseBuilding(fixture);
  result.routeCalls = await cdp.evaluate("window.__routeCalls.slice()");
  assert.deepEqual(await cdp.evaluate("window.__errors"), [], "room picking must not emit browser errors");
  result.status = "passed";
}

(async () => {
  try {
    await main();
  } catch (error) {
    result.status = "failed";
    result.error = String(error.stack || error);
    result.failureState = await routeState().catch(() => null);
  } finally {
    result.completedAt = new Date().toISOString();
    fs.writeFileSync(path.join(outputDir, "crossfloor-room-picking-results.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
    proc.kill();
    if (result.status !== "passed") process.exitCode = 1;
  }
})();
