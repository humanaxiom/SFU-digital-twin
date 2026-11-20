"use strict";

// Measurement only: keep full geometry and user controls; no latency pass threshold.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { createBrowserGate } = require("./room-search.cjs");
const { baseUrl, outputDir, proc, cdp, result, pointerClick, screenshot } = createBrowserGate("floor-performance");
const quote = JSON.stringify;
const measures = ["scene-transfer", "scene-parse", "scene-render"];
const floors = [1000, 2000, 3000, 4000, 5000, 6000].map(n => `SFU_BURNABY_QUAD_${n}`)
  .concat(["SFU_BURNABY_STRAND_1000", "SFU_BURNABY_STRAND_3000"]);

async function ready(levelId) {
  await cdp.wait(`!document.querySelector('#floor-view').hidden
    && document.querySelector('#viewing-floor').dataset.levelId === ${quote(levelId)}
    && document.querySelector('#floor-map').getAttribute('aria-busy') === 'false'`);
  await cdp.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
}

async function measure(levelId, selector, phase) {
  const before = await cdp.evaluate(`(() => {
    performance.clearMeasures();
    return {start: performance.now(), requests: window.__sceneRequests.length};
  })()`);
  await pointerClick(selector);
  await ready(levelId);
  const sample = await cdp.evaluate(`(() => {
    const map = document.querySelector('#floor-map');
    return {
      elapsedMs: performance.now() - ${before.start},
      componentsMs: Object.fromEntries(${quote(measures)}.map(name => [name,
        performance.getEntriesByName(name, 'measure').at(-1)?.duration ?? null])),
      counts: Object.fromEntries(['unit', 'detail', 'landmark', 'level'].map(kind =>
        [kind, map.querySelectorAll('.' + kind + '-shape').length])),
      geometry: [...map.querySelectorAll('.unit-shape,.detail-shape,.landmark-shape,.level-shape')]
        .map(node => [node.getAttribute('class'), node.dataset.unitId || null,
          node.getAttribute('d'), node.getAttribute('cx'), node.getAttribute('cy')]),
      requests: window.__sceneRequests.slice(${before.requests})
    };
  })()`);
  sample.geometrySha256 = crypto.createHash("sha256").update(JSON.stringify(sample.geometry)).digest("hex");
  delete sample.geometry;
  assert.ok(sample.counts.unit > 0);
  assert.equal(sample.requests.length, phase === "cold-client" ? 1 : 0);
  assert.ok(sample.requests.every(request => request.status === 200));
  assert.ok(Number.isFinite(sample.componentsMs["scene-render"]));
  if (phase === "warm-client") {
    assert.equal(sample.componentsMs["scene-transfer"], null);
    assert.equal(sample.componentsMs["scene-parse"], null);
  }
  return {levelId, phase, ...sample};
}

async function main() {
  result.browser = {container: process.env.HOSTNAME, ...await cdp.call("Browser.getVersion")};
  result.definition = "Cold means fresh page/client scene cache, not cold operating-system or server filesystem cache. Warm means revisit after another floor. Elapsed includes visible pointer activation, ready state, and two animation frames.";
  const health = await fetch(new URL("/demo/v1/health", baseUrl)).then(r => r.json());
  const levels = await fetch(new URL("/demo/v1/levels", baseUrl)).then(r => r.json());
  result.artifact = health.provenance;
  const {targetId} = await cdp.call("Target.createTarget", {url: "about:blank"});
  cdp.sessionId = (await cdp.call("Target.attachToTarget", {targetId, flatten: true})).sessionId;
  await cdp.call("Page.enable");
  await cdp.call("Network.enable");
  await cdp.call("Network.setCacheDisabled", {cacheDisabled: true});
  await cdp.call("Emulation.setDeviceMetricsOverride", {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
  await cdp.call("Page.addScriptToEvaluateOnNewDocument", {source: `(() => {
    window.__sceneRequests = []; window.__sceneErrors = [];
    addEventListener('error', e => __sceneErrors.push(String(e.message)));
    addEventListener('unhandledrejection', e => __sceneErrors.push(String(e.reason)));
    const original = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const url = String(args[0]);
      if (!/^\\/demo\\/v1\\/levels\\/[^/]+\\/scene$/.test(url)) return original(...args);
      const entry = {url}; __sceneRequests.push(entry);
      const response = await original(...args); entry.status = response.status; return response;
    };
  })()`});
  result.samples = [];
  for (const levelId of floors) {
    await cdp.call("Page.navigate", {url: baseUrl});
    await cdp.wait("document.querySelector('#route-origin')?.options.length > 1 && document.querySelectorAll('#building-buttons button').length === 3");
    const level = levels.levels.find(item => item.level_id === levelId);
    assert.ok(level);
    const buildingLevels = levels.levels.filter(item => item.facility_id === level.facility_id);
    const initial = buildingLevels.find(item => item.vertical_order === 0) || buildingLevels[0];
    const buildingSelector = `#building-buttons [data-building-id=${quote(level.facility_id)}]`;
    if (initial.level_id !== levelId) {
      await pointerClick(buildingSelector);
      await ready(initial.level_id);
    }
    const cold = await measure(levelId, initial.level_id === levelId ? buildingSelector
      : `#floor-buttons [data-level-id=${quote(levelId)}]`, "cold-client");
    const alternate = buildingLevels.find(item => item.level_id !== levelId);
    await pointerClick(`#floor-buttons [data-level-id=${quote(alternate.level_id)}]`);
    await ready(alternate.level_id);
    const warm = await measure(levelId, `#floor-buttons [data-level-id=${quote(levelId)}]`, "warm-client");
    assert.equal(warm.geometrySha256, cold.geometrySha256, "Warm geometry remains exact");
    assert.deepEqual(warm.counts, cold.counts);
    assert.deepEqual(await cdp.evaluate("window.__sceneErrors"), []);
    result.samples.push(cold, warm);
    console.log(JSON.stringify({levelId, coldMs: cold.elapsedMs, warmMs: warm.elapsedMs,
      componentsMs: cold.componentsMs, counts: cold.counts}));
    if (levelId === "SFU_BURNABY_QUAD_3000") await screenshot("aq3000.png");
  }
  result.checks.push("Eight floors measured cold/warm through visible controls with unchanged full rendered geometry and no browser errors");
}

main().then(() => {result.status = "passed";}, async error => {
  result.status = "failed"; result.error = error.stack; process.exitCode = 1;
  await screenshot("failure.png").catch(() => {});
}).finally(() => {
  result.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(outputDir, "results.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({status: result.status, error: result.error, outputDir}));
  proc.kill();
});
