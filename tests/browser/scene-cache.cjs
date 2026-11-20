"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createBrowserGate, strand } = require("./room-search.cjs");

const { baseUrl, outputDir, proc, cdp, result, pointerClick, screenshot } =
  createBrowserGate("scene-cache");
const quote = JSON.stringify;
const scenePath = levelId => `/demo/v1/levels/${levelId}/scene`;
const measureNames = ["scene-transfer", "scene-parse", "scene-render"];

function measurements() {
  return cdp.evaluate(`Object.fromEntries(${quote(measureNames)}.map(name => {
    const entry = performance.getEntriesByName(name, "measure").at(-1);
    return [name, entry ? { startTime: entry.startTime, duration: entry.duration } : null];
  }))`);
}

function requests() {
  return cdp.evaluate("window.__sceneRequests");
}

async function displayedScene(levelId) {
  await cdp.wait(`!document.querySelector('#floor-view')?.hidden
    && document.querySelector('#viewing-floor')?.dataset.levelId === ${quote(levelId)}
    && document.querySelector('#floor-map')?.getAttribute('aria-busy') === 'false'
    && document.querySelectorAll('#floor-map .unit-shape').length > 0`);
  await cdp.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
  return cdp.evaluate(`({
    levelId: document.querySelector('#viewing-floor').dataset.levelId,
    rooms: Array.from(document.querySelectorAll('#floor-map .unit-shape'),
      room => [room.dataset.unitId, room.getAttribute('d')])
  })`);
}

function verifyMeasurements(sample) {
  for (const name of measureNames) {
    assert.ok(Number.isFinite(sample[name]?.duration) && sample[name].duration >= 0,
      `${name} reports a duration in milliseconds`);
  }
}

async function loadFloor(levelId) {
  await pointerClick(`#floor-buttons [data-level-id=${quote(levelId)}]`);
  return displayedScene(levelId);
}

async function main() {
  result.browser = await cdp.call("Browser.getVersion");
  const {targetId} = await cdp.call("Target.createTarget", {url: "about:blank"});
  cdp.sessionId = (await cdp.call("Target.attachToTarget", {targetId, flatten: true})).sessionId;
  await cdp.call("Page.enable");
  await cdp.call("Network.enable");
  await cdp.call("Network.setCacheDisabled", {cacheDisabled: true});
  await cdp.call("Emulation.setDeviceMetricsOverride", {
    width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false,
  });
  await cdp.call("Page.addScriptToEvaluateOnNewDocument", {source: `(() => {
    window.__sceneRequests = [];
    window.__sceneErrors = [];
    addEventListener("error", event => __sceneErrors.push(String(event.error || event.message)));
    addEventListener("unhandledrejection", event => __sceneErrors.push(String(event.reason)));
    const fetchActual = window.fetch.bind(window);
    window.fetch = async (resource, init) => {
      const url = String(resource);
      if (!url.match(/^\\/demo\\/v1\\/levels\\/[^/]+\\/scene$/)) return fetchActual(resource, init);
      const entry = {url};
      __sceneRequests.push(entry);
      const response = await fetchActual(resource, init);
      entry.status = response.status;
      return response;
    };
  })();`});
  await cdp.call("Page.navigate", {url: baseUrl});
  await cdp.wait(`document.querySelector('#building-buttons [data-building-id=${quote(strand.facility)}]')`);
  const health = await cdp.evaluate("fetch('/demo/v1/health').then(response => response.json())");
  assert.equal(health.status, "ok");
  assert.equal(health.capabilities.routing, true);
  const { gpkg_sha256: gpkg, graph_sha256: graph, stats_sha256: stats } = health.provenance;
  assert.equal(gpkg, health.artifact_sha256);
  for (const digest of [gpkg, graph, stats]) assert.match(digest, /^[a-f0-9]{64}$/);
  result.artifact = {gpkg, graph, stats};

  assert.deepEqual(await requests(), [], "The page starts with cold floor scenes");
  await pointerClick(`#building-buttons [data-building-id=${quote(strand.facility)}]`);
  const first = await displayedScene(strand.floor1000);
  const coldFirst = await measurements();
  verifyMeasurements(coldFirst);
  const firstRequest = {url: scenePath(strand.floor1000), status: 200};
  assert.deepEqual(await requests(), [firstRequest]);

  const second = await loadFloor(strand.floor3000);
  const coldSecond = await measurements();
  verifyMeasurements(coldSecond);
  const secondRequest = {url: scenePath(strand.floor3000), status: 200};
  const coldRequests = [firstRequest, secondRequest];
  assert.deepEqual(await requests(), coldRequests);
  for (const name of measureNames) assert.ok(coldSecond[name].startTime > coldFirst[name].startTime);
  assert.notDeepEqual(second.rooms, first.rooms, "Different floor IDs render different room paths");
  result.checks.push("Both cold floors fetch once and record transfer, parse and render times");

  const revisited = await loadFloor(strand.floor1000);
  const warm = await measurements();
  assert.deepEqual(revisited, first, "Warm revisit restores the exact floor and room SVG paths");
  assert.deepEqual(await requests(), coldRequests, "Warm revisit makes no scene fetch");
  assert.deepEqual(warm["scene-transfer"], coldSecond["scene-transfer"]);
  assert.deepEqual(warm["scene-parse"], coldSecond["scene-parse"]);
  assert.ok(warm["scene-render"].startTime > coldSecond["scene-render"].startTime);
  assert.ok(Number.isFinite(warm["scene-render"].duration) && warm["scene-render"].duration >= 0);
  result.checks.push("Warm revisit reuses exact geometry and records a render without a new transfer or parse");

  result.sceneRequests = await requests();
  result.measurementsMs = {
    cold: [
      {levelId: first.levelId, roomCount: first.rooms.length, transfer: coldFirst["scene-transfer"].duration,
        parse: coldFirst["scene-parse"].duration, render: coldFirst["scene-render"].duration},
      {levelId: second.levelId, roomCount: second.rooms.length, transfer: coldSecond["scene-transfer"].duration,
        parse: coldSecond["scene-parse"].duration, render: coldSecond["scene-render"].duration},
    ],
    warm: {levelId: revisited.levelId, roomCount: revisited.rooms.length,
      transfer: null, parse: null, render: warm["scene-render"].duration},
  };
  assert.deepEqual(await cdp.evaluate("window.__sceneErrors"), []);
  await screenshot("warm-scene.png");
}

main().then(() => {
  result.status = "passed";
}, async error => {
  result.status = "failed";
  result.error = error.stack;
  result.sceneRequests = await requests().catch(() => null);
  process.exitCode = 1;
  await screenshot("failure.png").catch(() => {});
}).finally(() => {
  result.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(outputDir, "results.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  proc.kill();
});
