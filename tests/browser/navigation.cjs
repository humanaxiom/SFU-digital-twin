"use strict";

// Stage B navigation regressions. Run only in the pinned Playwright container.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

assert.ok(fs.existsSync("/.dockerenv"), "Run this browser gate through Docker.");
const runLabel = process.env.WAYFINDING_BROWSER_RUN_LABEL || "phase-b";
const outputDir = path.join("/workspace/build/navigation-review", runLabel);
fs.mkdirSync(outputDir, { recursive: true });
const baseUrl = process.env.WAYFINDING_BROWSER_BASE_URL || "http://127.0.0.1:8080";

class Cdp {
  constructor(proc) {
    this.proc = proc; this.nextId = 1; this.pending = new Map(); let buffer = "";
    const fail = error => { for (const item of this.pending.values()) item.reject(error); this.pending.clear(); };
    proc.on("error", fail); proc.on("exit", code => fail(new Error(`Chromium exited: ${code}`)));
    proc.stdio[3].on("error", fail); proc.stdio[4].setEncoding("utf8");
    proc.stdio[4].on("data", chunk => {
      buffer += chunk; const messages = buffer.split("\0"); buffer = messages.pop();
      for (const raw of messages) {
        if (!raw) continue; const message = JSON.parse(raw); const pending = this.pending.get(message.id);
        if (!pending) continue; this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(JSON.stringify(message.error))); else pending.resolve(message.result);
      }
    });
  }
  call(method, params = {}, sessionId = this.sessionId) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
      this.pending.set(id, { resolve: value => { clearTimeout(timer); resolve(value); }, reject: error => { clearTimeout(timer); reject(error); } });
      this.proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0");
    });
  }
  async evaluate(expression) {
    const response = await this.call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result?.value;
  }
  async wait(expression, timeout = 30000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) { if (await this.evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 50)); }
    throw new Error(`Timed out: ${expression}`);
  }
}

const quote = JSON.stringify;
const proc = spawn("/ms-playwright/chromium-1140/chrome-linux/chrome", ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--remote-debugging-pipe", "about:blank"], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
const cdp = new Cdp(proc);
const result = { startedAt: new Date().toISOString(), checks: [], failures: [], status: "running" };
function check(name, fn) {
  return Promise.resolve().then(fn).then(() => result.checks.push(name)).catch(async error => {
    const state = await cdp.evaluate("({facility:document.querySelector('#facility-select')?.value, floor:document.querySelector('#level-select')?.value, displayed:document.querySelector('#viewing-floor')?.dataset.levelId, mapStatus:document.querySelector('#map-status')?.textContent, requests:window.__requests?.filter(r=>r.url.includes('/scene')).slice(-3)})").catch(() => null);
    result.failures.push({ name, error: String(error), state });
  });
}
async function pointerClick(selector) {
  const point = await cdp.evaluate(`(() => { const node=document.querySelector(${quote(selector)}); if(!node) throw new Error('Missing '+${quote(selector)}); node.scrollIntoView({block:'center',inline:'center'}); const r=node.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2}; })()`);
  await cdp.call("Input.dispatchMouseEvent", { type: "mousePressed", ...point, button: "left", clickCount: 1 });
  await cdp.call("Input.dispatchMouseEvent", { type: "mouseReleased", ...point, button: "left", clickCount: 1 });
}
async function keyboardActivate(selector, key = "Enter") {
  await cdp.evaluate(`document.querySelector(${quote(selector)})?.focus()`);
  assert.equal(await cdp.evaluate(`document.activeElement===document.querySelector(${quote(selector)})`), true, `focus failed for ${selector}`);
  const props = { key, code: key === " " ? "Space" : key, windowsVirtualKeyCode: key === " " ? 32 : key === "ArrowDown" ? 40 : 13 };
  const text = key === "Enter" ? "\r" : key === " " ? " " : undefined;
  await cdp.call("Input.dispatchKeyEvent", { type: "keyDown", ...(text ? { text, unmodifiedText: text } : {}), ...props });
  await cdp.call("Input.dispatchKeyEvent", { type: "keyUp", ...props });
}
async function sceneReady(levelId) {
  await cdp.wait(`document.querySelector('#viewing-floor')?.dataset.levelId===${quote(levelId)}&&window.__requests.some(r=>r.url===${quote(`/demo/v1/levels/${levelId}/scene`)}&&r.done&&r.status===200)&&!document.querySelector('#map-status')?.textContent.includes('Loading')`);
}
async function main() {
  const { targetId } = await cdp.call("Target.createTarget", { url: "about:blank" });
  cdp.sessionId = (await cdp.call("Target.attachToTarget", { targetId, flatten: true })).sessionId;
  await cdp.call("Page.enable");
  await cdp.call("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await cdp.call("Page.addScriptToEvaluateOnNewDocument", { source: `window.__requests=[];window.__errors=[];addEventListener('error',e=>__errors.push(String(e.message||e.error)));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));const originalFetch=window.fetch;window.fetch=async(...args)=>{const url=String(args[0]);const rec={url,done:false};window.__requests.push(rec);try{const response=await originalFetch(...args);rec.status=response.status;rec.response=await response.clone().json().catch(()=>null);rec.done=true;return response;}catch(error){rec.error=String(error);rec.done=true;throw error;}};` });
  await cdp.call("Page.navigate", { url: baseUrl });
  await cdp.wait("document.querySelector('#facility-select')?.options.length>1");
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1");
  const data = await cdp.evaluate(`({campus:window.__requests.find(r=>r.url==='/demo/v1/campus'&&r.done)?.response,levels:window.__requests.find(r=>r.url==='/demo/v1/levels'&&r.done)?.response.levels})`);
  assert.ok(data.campus && data.levels?.length === 11, "campus/level catalog must be complete");
  result.catalog = { facilities: data.campus.facilities.map(facility => facility.facility_id), levels: data.levels.map(level => level.level_id) };

  await check("all three buildings expose every recorded level through exact scoped controls", async () => {
    for (const facility of data.campus.facilities) {
      if (await cdp.evaluate("document.querySelector('#campus-view').hidden")) await pointerClick("#show-campus");
      const button = `#campus-buildings [data-campus-facility-id="${facility.facility_id}"]`;
      await pointerClick(button); await cdp.wait(`document.querySelector('#facility-select').value===${quote(facility.facility_id)}`);
      const visibleLevels = await cdp.evaluate("[...document.querySelectorAll('#campus-details [data-campus-level-id]')].map(n=>n.dataset.campusLevelId)");
      assert.deepEqual([...visibleLevels].sort(), facility.levels.map(level => level.level_id).sort());
      for (const [index, level] of facility.levels.entries()) {
        if (index) {
          await pointerClick("#show-campus");
          await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
        }
        await keyboardActivate(`#campus-details [data-campus-level-id=\"${level.level_id}\"]`);
        await sceneReady(level.level_id);
        assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), facility.facility_id);
        assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), level.level_id);
      }
    }
  });

  await check("explicit Open floor action opens an already-selected floor", async () => {
    if (!(await cdp.evaluate("!document.querySelector('#campus-view').hidden"))) await pointerClick("#show-campus");
    const facility = data.campus.facilities[0];
    await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
    const selectedLevel = await cdp.evaluate("document.querySelector('#level-select').value");
    assert.ok(selectedLevel && facility.levels.some(level => level.level_id === selectedLevel));
    assert.ok(await cdp.evaluate("document.querySelector('#open-floor').getBoundingClientRect().height>=44"), "Open floor must meet the 44px touch target");
    await pointerClick("#open-floor");
    await sceneReady(selectedLevel);
    assert.equal(await cdp.evaluate("document.querySelector('#floor-view').hidden"), false);
    assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), selectedLevel);
  });

  await check("native Floor picker responds to keyboard ArrowDown and Enter", async () => {
    await pointerClick("#show-campus");
    const facility = data.campus.facilities[0];
    await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
    const firstLevel = facility.levels[0];
    await pointerClick(`#campus-details [data-campus-level-id=\"${firstLevel.level_id}\"]`);
    await sceneReady(firstLevel.level_id);
    await pointerClick("#show-campus");
    await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
    const before = await cdp.evaluate("document.querySelector('#level-select').value");
    await keyboardActivate("#level-select", "ArrowDown");
    const after = await cdp.evaluate("document.querySelector('#level-select').value");
    assert.notEqual(after, before, "ArrowDown must select a different recorded floor");
    assert.ok(facility.levels.some(level => level.level_id === after));
    if (after !== before) await keyboardActivate("#level-select", "Enter");
    await sceneReady(after);
    assert.equal(await cdp.evaluate("document.querySelector('#floor-view').hidden"), false);
    assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), facility.facility_id);
    assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), after);
  });

  await check("late route completion cannot steal a deliberately selected floor", async () => {
    const fixture = JSON.parse(fs.readFileSync("/workspace/docs/reports/DT-015-demo-routes.json")).fixtures.aq_elevator;
    await cdp.evaluate(`window.__holdRoute=true;window.__releaseRoute=null;window.__routeOriginalFetch=window.fetch;window.fetch=async(...args)=>{const response=await window.__routeOriginalFetch(...args);if(String(args[0])==='/demo/v1/route'){await new Promise(resolve=>window.__releaseRoute=resolve);}return response;}`);
    await cdp.evaluate(`document.querySelector('#route-origin').value=${quote(fixture.origin.unit_id)};document.querySelector('#route-destination').value=${quote(fixture.destination.unit_id)};document.querySelector('#route-profile').value=${quote(fixture.profile)};document.querySelector('#route-form').requestSubmit()`);
    await cdp.wait("typeof window.__releaseRoute==='function'");
    const target = data.levels.find(level => level.level_id !== fixture.origin.level_id);
    await cdp.evaluate(`document.querySelector('#facility-select').value=${quote(target.facility_id)};document.querySelector('#facility-select').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#level-select').value=${quote(target.level_id)};document.querySelector('#level-select').dispatchEvent(new Event('change',{bubbles:true}))`);
    await sceneReady(target.level_id); await cdp.evaluate("window.__releaseRoute()");
    await cdp.wait("document.querySelector('#route-status')?.dataset.state && document.querySelector('#route-status').dataset.state!=='pending'");
    assert.equal(await cdp.evaluate("document.querySelector('#route-status').dataset.state"), "success");
    assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), target.level_id);
    assert.equal(await cdp.evaluate("document.querySelector('#return-to-route').hidden"), false);
    await pointerClick("#return-to-route");
    await sceneReady(fixture.origin.level_id);
    assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), fixture.origin.level_id);
  });

  await check("scene failure retains a labeled scene and offers Retry", async () => {
    await pointerClick("#show-campus");
    const facility = data.campus.facilities[0];
    await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
    const base = facility.levels[0];
    await pointerClick(`#campus-details [data-campus-level-id=\"${base.level_id}\"]`);
    await sceneReady(base.level_id);
    await pointerClick("#show-campus");
    await pointerClick(`#campus-buildings [data-campus-facility-id=\"${facility.facility_id}\"]`);
    const target = facility.levels.find(level => level.level_id !== base.level_id);
    assert.ok(target, "fixture needs two floors for Retry coverage");
    await cdp.evaluate(`window.__sceneFailOnce=${quote(target.level_id)};window.__sceneOriginalFetch=window.fetch;window.fetch=async(...args)=>{if(String(args[0])===${quote(`/demo/v1/levels/${target.level_id}/scene`)}&&window.__sceneFailOnce){window.__sceneFailOnce=null;return new Response('forced failure',{status:503});}return window.__sceneOriginalFetch(...args);}`);
    await pointerClick(`#campus-details [data-campus-level-id=\"${target.level_id}\"]`);
    await cdp.wait("document.querySelector('#retry-scene')?.hidden===false");
    assert.match(await cdp.evaluate("document.querySelector('#map-status').textContent"), /Could not load/);
    assert.match(await cdp.evaluate("document.querySelector('#map-status').textContent"), /Still showing/);
    assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"), base.level_id);
    assert.equal(await cdp.evaluate("document.querySelector('#level-select').value"), target.level_id);
    assert.ok(await cdp.evaluate("document.querySelector('#retry-scene')"), "#retry-scene is required");
    await pointerClick("#retry-scene"); await sceneReady(target.level_id);
    assert.deepEqual(await cdp.evaluate("window.__errors"), [], "navigation must not emit uncaught browser errors");
  });
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
    await cdp.call("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
    await cdp.evaluate("window.scrollTo(0,0); new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
    const { data: screenshot } = await cdp.call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const file = `${name}.png`; fs.writeFileSync(path.join(outputDir, file), Buffer.from(screenshot, "base64"));
    result.screenshots ??= {}; result.screenshots[name] = file;
  }
  result.status = result.failures.length ? "failed" : "passed";
}

(async () => { try { await main(); } catch (error) { result.failures.push({ name: "harness", error: String(error) }); result.status = "failed"; } finally { result.completedAt = new Date().toISOString(); fs.writeFileSync(path.join(outputDir, "navigation-results.json"), JSON.stringify(result, null, 2)); console.log(JSON.stringify(result, null, 2)); proc.kill(); if (result.failures.length) process.exitCode = 1; } })();
