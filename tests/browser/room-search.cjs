"use strict";

// Real Chromium gate for searching and choosing route endpoints.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

assert.ok(fs.existsSync("/.dockerenv"), "Run this browser gate through Docker.");

const baseUrl = process.env.WAYFINDING_BROWSER_BASE_URL || "http://127.0.0.1:8080";

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
const strand = {
  facility: "SFU_BURNABY_STRAND",
  floor100: "SFU_BURNABY_STRAND_100",
  floor1000: "SFU_BURNABY_STRAND_1000",
  floor3000: "SFU_BURNABY_STRAND_3000",
  origin: "SFU_BURNABY_STRAND_1000_1036",
  destination: "SFU_BURNABY_STRAND_3000_3050.1",
  disconnected: "SFU_BURNABY_STRAND_100_110",
  duplicate: "SH110",
};

const origin = "#route-origin-search";
const destination = "#route-destination-search";
const defaultRoute = { origin: { unit_id: strand.origin }, destination: { unit_id: strand.destination }, profile: "default" };

function createBrowserGate(defaultLabel) {
  const runLabel = process.env.WAYFINDING_BROWSER_RUN_LABEL || defaultLabel;
  const outputDir = path.join("/workspace/build/navigation-review", runLabel);
  fs.mkdirSync(outputDir, { recursive: true });

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

  async function key(name) {
    const codes = { Enter: 13, Tab: 9, Home: 36, ArrowDown: 40 };
    const down = name === "Enter" ? "keyDown" : "rawKeyDown";
    for (const type of [down, "keyUp"]) {
      await cdp.call("Input.dispatchKeyEvent", {
        type, key: name, code: name,
        windowsVirtualKeyCode: codes[name],
        ...(type === "keyDown" ? {text: "\r", unmodifiedText: "\r"} : {}),
      });
    }
  }

  function field(selector, property) {
    return cdp.evaluate(`document.querySelector(${quote(selector)})?.${property}`);
  }

  async function typeQuery(selector, value) {
    await pointerClick(selector);
    await cdp.call("Input.dispatchKeyEvent", {
      type: "rawKeyDown", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2,
    });
    await cdp.call("Input.dispatchKeyEvent", {
      type: "keyUp", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2,
    });
    await cdp.call("Input.insertText", {text: value});
    assert.equal(await field(selector, "value"), value, `Typed into ${selector}`);
  }

  function options(selector) {
    return cdp.evaluate(`Array.from(document.querySelector(${quote(selector)}).options,
      node => ({id: node.value, label: node.label, disabled: node.disabled}))`);
  }

  async function pickNativeOption(selector, id) {
    const index = (await options(selector)).findIndex(item => item.id === id);
    assert.ok(index >= 0, `Option ${id} is present in ${selector}`);
    await cdp.evaluate(`document.querySelector(${quote(selector)}).focus()`);
    await key("Home");
    for (let selected = 0; selected < index; selected++) await key("ArrowDown");
    assert.equal(await field(selector, "value"), id, `Keyboard selected ${id} in ${selector}`);
  }

  async function assertIdle(expectedOrigin, expectedDestination, routeCount) {
    assert.deepEqual(
      await cdp.evaluate("[document.querySelector('#route-origin').value, document.querySelector('#route-destination').value, window.__routeCalls.length]"),
      [expectedOrigin, expectedDestination, routeCount],
      "The draft room IDs and number of submitted route requests match the current action",
    );
  }

  async function assertCandidate(selector, id, expectedLabel) {
    const candidate = (await options(selector)).find(item => item.id === id);
    assert.ok(candidate, `Found exact room ${id}`);
    assert.match(candidate.label, expectedLabel);
    return candidate;
  }

  async function resultClick(selector, id) {
    await pointerClick(`${selector} option[value=${quote(id)}]`);
    assert.equal(await field(selector, "value"), id, "Pointer selected the exact option");
  }

  async function activateChoice(selector, keyboard) {
    const choose = `${selector}-choose`;
    if (keyboard) {
      await key("Tab");
      assert.equal(await field(choose, "matches(':focus')"), true, "Tab reaches the choose button from results");
      await key("Enter");
    } else {
      await pointerClick(choose);
    }
  }

  async function prepareViewport(width) {
    await cdp.call("Emulation.setDeviceMetricsOverride", {
      width, height: width > 500 ? 1000 : 844, deviceScaleFactor: 1, mobile: width < 500,
    });
    await cdp.call("Page.navigate", {url: baseUrl});
    await cdp.wait("document.querySelectorAll('#building-buttons button').length===3 && document.querySelector('#route-origin')?.options.length>1");
    await pointerClick("#directions-panel > summary");
    assert.ok(await field("#directions-panel", "open"), "Directions disclosure opens");
    await pointerClick("#route-origin-finder > summary");
    assert.ok(await field(origin, "checkVisibility()"), "Directions exposes a usable From room search");
    assert.equal(await field(origin, "labels[0].textContent.trim()"), "Search From rooms");
    assert.equal(await field(`${origin}-status`, "getAttribute('role')"), "status");
    assert.equal(await field(`${origin}-results`, "getAttribute('aria-describedby')"), "route-origin-search-status");
  }

  async function screenshot(filename) {
    const {data} = await cdp.call("Page.captureScreenshot", {format: "png"});
    fs.writeFileSync(path.join(outputDir, filename), Buffer.from(data, "base64"));
  }

  return {
    baseUrl, outputDir, proc, cdp, result, pointerClick, key, field, typeQuery, options,
    pickNativeOption, assertIdle, assertCandidate, resultClick, activateChoice,
    prepareViewport, screenshot,
  };
}

module.exports = { createBrowserGate, strand, origin, destination, defaultRoute };

if (require.main === module) runRoomSearch().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

async function runRoomSearch() {
  const {
    baseUrl, outputDir, proc, cdp, result, pointerClick, key, field, typeQuery, options,
    pickNativeOption, assertIdle, assertCandidate, resultClick, activateChoice,
    prepareViewport, screenshot,
  } = createBrowserGate("room-search");

  async function exerciseAuthority() {
    for (const [label, query] of [
      ["Exact authoritative room ID", "sh1036"],
      ["Partial authoritative room ID", "h103"],
      ["Authoritative building ID", "sfu_burnaby_strand"],
      ["Authoritative building name", "Strand Hall"],
      ["Authoritative building acronym", "SH"],
    ]) {
      await typeQuery(origin, query);
      const found = await options(`${origin}-results`);
      assert.ok(found.some(item => item.id === strand.origin), `${label} returns SH1036`);
      assert.ok(found.every(item => !item.id || item.id.startsWith("SFU_BURNABY_STRAND_")), `${label} excludes other buildings`);
      if (label.startsWith("Exact")) assert.equal(found.filter(item => item.id).length, 1);
      result.checks.push(label);
    }
    await typeQuery(origin, "Staff Lounge");
    assert.equal((await options(`${origin}-results`)).filter(item => item.id).length, 0, "Room use text is excluded from location search");
    result.checks.push("Search excludes room use text");
    await assertIdle("", "", 0);
    await typeQuery(origin, strand.duplicate);
    const duplicates = (await options(`${origin}-results`)).filter(item => /^SH110\b/i.test(item.label));
    assert.equal(duplicates.length, 2, "Catalog shows both rooms with the same recorded room ID");
    assert.notEqual(duplicates[0].label, duplicates[1].label, "Duplicate room codes carry distinct floor labels");
    await pickNativeOption(`${origin}-building`, "SFU_BURNABY_QUAD");
    assert.equal((await options(`${origin}-results`)).filter(item => item.id).length, 0, "Wrong building excludes room matches");
    await pickNativeOption(`${origin}-building`, strand.facility);
    assert.ok((await options(`${origin}-floor`)).filter(item => item.id)
      .every(item => item.id.startsWith("SFU_BURNABY_STRAND_")), "Scoped floor list only offers Strand exact floors");
    await pickNativeOption(`${origin}-floor`, strand.floor100);
    await assertCandidate(`${origin}-results`, strand.disconnected, /SH110.*(?:Strand Hall|SH).*100/i);
    assert.equal((await options(`${origin}-results`)).filter(item => item.id).length, 1, "Exact scoped floor disambiguates SH110");
    result.checks.push("Building and exact floor scope disambiguate both recorded SH110 rooms");
    await assertIdle("", "", 0);
    return duplicates;
  }

  async function exerciseSelection(width, keyboard) {
    await pickNativeOption(`${origin}-building`, strand.facility);
    await pickNativeOption(`${origin}-floor`, strand.floor1000);
    await typeQuery(origin, "SH1036");
    const start = await assertCandidate(`${origin}-results`, strand.origin, /SH1036.*(?:Strand Hall|SH).*1000/i);
    if (keyboard) await pickNativeOption(`${origin}-results`, strand.origin);
    else await resultClick(`${origin}-results`, strand.origin);
    await assertIdle("", "", 0);
    await activateChoice(origin, keyboard);
    await cdp.wait("document.querySelector('#route-options-status')?.dataset.state==='ready'");
    await assertIdle(strand.origin, "", 0);

    await pointerClick("#route-destination-finder > summary");
    assert.ok(await field(destination, "checkVisibility()"), "Directions exposes a usable To room search");
    await typeQuery(destination, "SH110");
    const blocked = await assertCandidate(`${destination}-results`, strand.disconnected, /SH110.*(?:Strand Hall|SH).*100/i);
    assert.equal(blocked.disabled, true, "Known disconnected room stays visible and is disabled");
    await pickNativeOption(`${destination}-building`, strand.facility);
    await pickNativeOption(`${destination}-floor`, strand.floor100);
    assert.ok(await field(`${destination}-choose`, "disabled"), "Choose To is disabled when the only match is disconnected");
    await pointerClick(`${destination}-choose`);
    await assertIdle(strand.origin, "", 0);
    result.checks.push(`${width}px To search displays a disconnected SH110 and blocks route submission`);

    await pickNativeOption(`${destination}-floor`, strand.floor3000);
    await typeQuery(destination, "3050.1");
    const end = await assertCandidate(`${destination}-results`, strand.destination, /SH3050\.1.*(?:Strand Hall|SH).*3000/i);
    if (keyboard) await pickNativeOption(`${destination}-results`, strand.destination);
    else await resultClick(`${destination}-results`, strand.destination);
    await assertIdle(strand.origin, "", 0);

    await screenshot(`search-${width}.png`);
    await activateChoice(destination, keyboard);
    await assertIdle(strand.origin, strand.destination, 0);
    if (keyboard) {
      await cdp.evaluate("document.querySelector('#route-submit').focus()");
      await key("Enter");
    } else {
      await pointerClick("#route-submit");
    }
    const route = await assertStrandRoute();

    await typeQuery(destination, "xxxxx");
    await key("Enter");
    await pickNativeOption(`${destination}-floor`, strand.floor100);
    await assertIdle(strand.origin, strand.destination, 1);
    assert.equal(await field("#route-status", "dataset.state"), "success", "Searching after a route preserves the route");
    assert.deepEqual(await cdp.evaluate("window.__errors"), [], "Room search emits no browser errors");
    result.cases.push({width, input: keyboard ? "keyboard" : "pointer", start, end, blocked});
    result.routeCalls.push(route);
    result.checks.push(`${width}px ${keyboard ? "keyboard" : "pointer"} selects exact A/B rooms and routes across three Strand floors`);
  }

  async function assertStrandRoute() {
    await cdp.wait("window.__routeCalls.some(call => call.status === 200) && document.querySelector('#route-status')?.dataset.state==='success'");
    await assertIdle(strand.origin, strand.destination, 1);
    const [route] = await cdp.evaluate("window.__routeCalls");
    assert.deepEqual(route.payload, defaultRoute);
    assert.deepEqual(route.visitLevels, [strand.floor1000, "SFU_BURNABY_STRAND_2000", strand.floor3000]);
    assert.ok(route.geometryPointCount > 0, "Route contains real path geometry");
    return route;
  }

  async function exerciseToFirst() {
    await prepareViewport(320);
    await pointerClick("#route-destination-finder > summary");
    await pickNativeOption(`${destination}-building`, strand.facility);
    await pickNativeOption(`${destination}-floor`, strand.floor3000);
    await typeQuery(destination, "3050.1");
    await pickNativeOption(`${destination}-results`, strand.destination);
    await activateChoice(destination, false);
    await assertIdle("", strand.destination, 0);

    await pickNativeOption(`${origin}-building`, strand.facility);
    await pickNativeOption(`${origin}-floor`, strand.floor1000);
    await typeQuery(origin, "SH1036");
    await pickNativeOption(`${origin}-results`, strand.origin);
    await activateChoice(origin, false);
    await cdp.wait("document.querySelector('#route-options-status').dataset.state === 'ready'");
    await assertIdle(strand.origin, strand.destination, 0);
    await pointerClick("#route-submit");
    result.routeCalls.push(await assertStrandRoute());
    result.checks.push("320px To-first selection retains B and submits once on explicit preview");

    await pickNativeOption(`${origin}-floor`, strand.floor100);
    await typeQuery(origin, strand.duplicate);
    await pickNativeOption(`${origin}-results`, strand.disconnected);
    await assertIdle(strand.origin, strand.destination, 1);
    await cdp.evaluate(`window.__holdOptionsFor = ${quote(strand.disconnected)}`);
    await activateChoice(origin, false);
    await cdp.wait("typeof window.__releaseRouteOptions === 'function' && document.querySelector('#route-options-status').dataset.state === 'pending'");
    await assertIdle(strand.disconnected, strand.destination, 1);
    assert.equal(await field("#route-status", "dataset.state"), "success", "The committed route stays visible when From changes");
    assert.match(await field("#route-draft-status", "textContent"), /route changes not applied/i);
    await cdp.evaluate("window.__holdOptionsFor = null; window.__releaseRouteOptions()");
    await cdp.wait("document.querySelector('#route-options-status').dataset.state === 'ready'");
    await assertIdle(strand.disconnected, strand.destination, 1);
    assert.match(await field("#route-options-status", "textContent"), /selected destination has no mapped connection/i);
    await pointerClick("#route-submit");
    await cdp.wait("document.querySelector('#route-request-status').dataset.state === 'error'");
    await assertIdle(strand.disconnected, strand.destination, 1);
    assert.match(await field("#route-committed-identity", "textContent"), /SH1036.*SH3050\.1/i);
    assert.match(await field("#route-request-status", "textContent"), /previous route remains displayed/i);
    result.checks.push("320px From replacement checks availability, retains exact To, and preserves the committed route");
  }
  async function verifyApi() {
    const get = async endpoint => {
      const response = await fetch(new URL(`/demo/v1/${endpoint}`, baseUrl));
      assert.equal(response.status, 200);
      return response.json();
    };
    const [health, facilities, levels, units, choices] = await Promise.all([
      get("health"), get("facilities"), get("levels"), get("units"),
      get(`route-options?origin_unit_id=${strand.origin}&profile=default`),
    ]);
    assert.equal(choices.destinations.find(item => item.unit_id === strand.disconnected)?.availability, "disconnected");
    assert.equal(choices.destinations.find(item => item.unit_id === strand.destination)?.availability, "connected");
    const blocked = await fetch(new URL("/demo/v1/route", baseUrl), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...defaultRoute, destination: {unit_id: strand.disconnected}}),
    });
    assert.equal(blocked.status, 409);
    assert.equal((await blocked.json()).code, "disconnected");
    result.api = {
      facilities: facilities.count, levels: levels.count, rooms: units.units.length,
      routeOptions: choices.destinations.length, disconnectedRouteHTTP: blocked.status,
      provenance: health.provenance,
    };
    result.checks.push("Direct API confirms disconnected and connected outcomes and rejects disconnected route with HTTP 409");
  }

  async function main() {
    result.browser = {container: process.env.HOSTNAME, chromium: (await cdp.call("Browser.getVersion")).product};
    const {targetId} = await cdp.call("Target.createTarget", {url: "about:blank"});
    const {sessionId} = await cdp.call("Target.attachToTarget", {targetId, flatten: true});
    cdp.sessionId = sessionId;
    await cdp.call("Page.enable");
    await cdp.call("Page.addScriptToEvaluateOnNewDocument", {source: `
      window.__routeCalls = [];
      window.__errors = [];
      window.__holdOptionsFor = null;
      addEventListener("error", event => window.__errors.push(String(event.message)));
      addEventListener("unhandledrejection", event => window.__errors.push(String(event.reason)));
      const realFetch = window.fetch.bind(window);
      window.fetch = async (url, init) => {
        if (url.startsWith("/demo/v1/route-options?") && window.__holdOptionsFor &&
          new URL(url, window.location.origin).searchParams.get("origin_unit_id") === window.__holdOptionsFor) {
          await new Promise(resolve => { window.__releaseRouteOptions = resolve; });
        }
        if (url !== "/demo/v1/route" || init?.method !== "POST") return realFetch(url, init);
        const call = {payload: JSON.parse(init.body)};
        window.__routeCalls.push(call);
        const response = await realFetch(url, init);
        const body = await response.clone().json();
        call.status = response.status;
        call.visitLevels = body.guidance?.visits?.map(visit => visit.level_id);
        call.geometryPointCount = body.guidance?.geometries?.reduce((sum, item) => sum + item.geometry.coordinates.length, 0);
        return response;
      };
    `});
    await prepareViewport(1440);
    result.duplicates = await exerciseAuthority();
    await exerciseSelection(1440, false);
    await prepareViewport(390);
    await exerciseSelection(390, true);
    await exerciseToFirst();
    assert.ok(await cdp.evaluate(`document.documentElement.scrollWidth <= 321 &&
      ["${origin}", "${destination}", "${origin}-results", "${destination}-results"].every(selector => {
        const rect = document.querySelector(selector).getBoundingClientRect();
        return rect.left >= 0 && rect.right <= 321 && rect.width > 0;
      })`), "Search controls remain within the 320px viewport");
    result.checks.push("Both endpoint search controls fit the 320px viewport");
    assert.deepEqual(await cdp.evaluate("window.__errors"), [], "Room search emits no browser errors at 320px");
    await screenshot("search-320.png");
    await verifyApi();
  }

  await main().then(() => { result.status = "passed"; }, async error => {
    result.status = "failed";
    result.error = error.stack;
    process.exitCode = 1;
    await screenshot("failure.png").catch(() => {});
  }).finally(() => {
    result.finishedAt = new Date().toISOString();
    fs.writeFileSync(path.join(outputDir, "results.json"), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
    proc.kill();
  });
}
