"use strict";

// Node built-ins + Chromium CDP pipe; execute only in the pinned Docker image.
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { verifyGuidance, activateButton, assertSelected, exerciseGuidance, sceneOrigin } = require('./guidance.cjs');
const {exerciseCampus} = require('./campus.cjs');
assert.ok(fs.existsSync("/.dockerenv"), "Run this gate through Docker Compose.");
const runLabel = process.env.WAYFINDING_BROWSER_RUN_LABEL || "";
assert.ok(!runLabel || /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(runLabel), "Invalid evidence run label");
const outputDir = path.join("/workspace/build/takeover-browser", runLabel);
const baseUrl = process.env.WAYFINDING_BROWSER_BASE_URL || 'http://demo:8080';
const targetUrl = new URL(baseUrl);
assert.ok(targetUrl.protocol === 'http:' && ['demo','127.0.0.1','localhost'].includes(targetUrl.hostname)
  && !targetUrl.username && !targetUrl.password && targetUrl.pathname === '/' && !targetUrl.search && !targetUrl.hash,
  'Browser gate must target a local demo origin');
const reportBytes = fs.readFileSync("/workspace/docs/reports/DT-015-demo-routes.json");
const fixtures = JSON.parse(reportBytes).fixtures;
const results = {
  startedAt: new Date().toISOString(), node: process.version, baseUrl,
  reportSha256: crypto.createHash("sha256").update(reportBytes).digest("hex"),
  viewports: {}, checks: [], status: "running",
};

class Cdp {
  constructor(proc) {
    this.proc = proc; this.nextId = 1; this.pending = new Map();
    let buffer = "";
    const fail = error => {
      for (const { reject } of this.pending.values()) reject(error);
      this.pending.clear();
    };
    proc.on("error", fail);
    proc.on("exit", code => fail(new Error(`Chromium exited: ${code}`)));
    proc.stdio[3].on("error", fail);
    proc.stdio[4].setEncoding("utf8");
    proc.stdio[4].on("data", chunk => {
      buffer += chunk;
      const messages = buffer.split("\0"); buffer = messages.pop();
      for (const raw of messages) {
        if (!raw) continue;
        const message = JSON.parse(raw), pending = this.pending.get(message.id);
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
        this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`));
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
      expression, awaitPromise: true, returnByValue: true, userGesture: true,
    });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
    return response.result?.value;
  }
  async wait(expression) {
    const end = Date.now() + 30000;
    while (Date.now() < end) {
      if (await this.evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Timed out: ${expression}`);
  }
}
const quote = JSON.stringify;
const routes = "window.__requests.filter(r => r.url === '/demo/v1/route')";
const sceneReady = e => `document.querySelector('.unit-shape[data-unit-id="${e.unit_id}"]') && !document.querySelector('#map-status').textContent.includes('Loading')`;

async function screenshot(cdp, name, fullPage = false) {
  // Capture painted viewports: beyond-viewport snapshots can retain stale scroll surfaces.
  const captures = {};
  for (const [panel, selector] of Object.entries(fullPage
    ? {map:null, controls:'#route-form', current:'#current-instruction', rooms:'#room-list'} : {map:null})) {
    await cdp.evaluate(`(async () => {
      if (${quote(selector)}) {
        const node=document.querySelector(${quote(selector)});
        for(let p=node.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
        node.scrollIntoView({block:'start'});
      }
      else window.scrollTo(0, 0);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    })()`);
    const {data} = await cdp.call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
    const file = `${name}-${panel}.png`;
    fs.writeFileSync(path.join(outputDir, file), Buffer.from(data, 'base64'));
    captures[panel] = file;
  }
  return captures;
}
function svgLine(geometry, [originX,originY]) {
  assert.ok(["LineString", "MultiLineString"].includes(geometry.type));
  const lines = geometry.type === "LineString" ? [geometry.coordinates] : geometry.coordinates;
  return lines.map(line => line.map(([x, y], i) => `${i ? "L" : "M"}${x-originX} ${-(y-originY)}`).join(" ")).join(" ");
}
async function assertScene(cdp, endpoint, body) {
  await cdp.wait(sceneReady(endpoint));
  const sceneRooms = await cdp.evaluate(`window.__requests.filter(r => r.done && r.response?.level?.level_id === ${quote(endpoint.level_id)}).at(-1).response.units.map(u => u.unit_id)`);
  for (const selector of ['.unit-shape', '#room-list button']) {
    const roomIds = await cdp.evaluate(`[...document.querySelectorAll(${quote(selector)})].map(n => n.dataset.unitId)`);
    assert.deepEqual(roomIds, sceneRooms, `map and room list must both match ${endpoint.level_id}`);
  }
  const actual = await cdp.evaluate("[...document.querySelectorAll('#route-overlay .route-segment')].map(p => p.getAttribute('d'))");
  const origin=await sceneOrigin(cdp);
  const expected = body.guidance.geometries.filter(g => g.level_id === endpoint.level_id).map(g => svgLine(g.geometry,origin));
  assert.deepEqual(actual, expected, `overlay differs on ${endpoint.level_id}`);
  assert.ok(actual.length > 0 || body.guidance.markers.some(m => m.level_id === endpoint.level_id));
}
async function submit(cdp, fixture, chat = false) {
  const before = await cdp.evaluate(`${routes}.length`);
  const assistantCount = "window.__requests.filter(r => r.url === '/demo/v1/assistant').length";
  const beforeAssistant = await cdp.evaluate(assistantCount);
  if (chat) {
    const prompt = `${fixture.profile === "elevator_only" ? "mobility " : ""}directions from ${fixture.origin.room_id} to ${fixture.destination.room_id}`;
    await cdp.evaluate(`document.querySelector('#assistant-input').value = ${quote(prompt)}; document.querySelector('#assistant-form').requestSubmit()`);
  } else {
    await chooseFloor(cdp,fixture.origin.level_id);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(fixture.origin.level_id)}`);
    assert.equal(await cdp.evaluate(`!!document.querySelector('#route-origin option[value="${fixture.origin.unit_id}"]')`),true,
      `origin ${fixture.origin.unit_id} is missing from its viewed-floor dropdown`);
    await cdp.evaluate(`
      document.querySelector('#route-destination').value = '';
      document.querySelector('#route-origin').value = ${quote(fixture.origin.unit_id)};
      document.querySelector('#route-profile').value = ${quote(fixture.profile)};
      document.querySelector('#route-origin').dispatchEvent(new Event('change',{bubbles:true}));
    `);
    try {
      await cdp.wait(`document.querySelector('#route-options-status').dataset.state==='ready'
        && document.querySelector('#route-options-status').dataset.originUnitId===${quote(fixture.origin.unit_id)}
        && document.querySelector('#route-options-status').dataset.profile===${quote(fixture.profile)}`);
    } catch (error) {
      const state=await cdp.evaluate(`(() => {const node=document.querySelector('#route-options-status');return {
        origin:document.querySelector('#route-origin').value,destination:document.querySelector('#route-destination').value,
        state:node.dataset.state,stateOrigin:node.dataset.originUnitId,stateProfile:node.dataset.profile,text:node.textContent,
        latest:window.__requests.filter(item=>item.url.startsWith('/demo/v1/route-options?')).at(-1),errors:window.__errors};})()`);
      throw new Error(`${error.message}; state=${JSON.stringify(state)}`);
    }
    await cdp.evaluate(`
      document.querySelector('#route-destination').value = ${quote(fixture.destination.unit_id)};
      document.querySelector('#route-form').requestSubmit();
    `);
  }
  await cdp.wait(`${routes}[${before}]?.done`);
  const guidanceVersion = await cdp.evaluate(`${routes}[${before}].response.guidance?.version`);
  assert.equal(guidanceVersion, 'dt018-guidance-v1', 'real route needs structured guidance');
  await cdp.wait(`document.querySelector('#route-status').dataset.state === 'success'`);
  const sent = await cdp.evaluate(`${routes}.slice(${before})`);
  assert.equal(sent.length, 1, "each action submits exactly one route");
  const { body, response } = sent[0];
  verifyGuidance(response);
  assert.deepEqual(body, { origin: { unit_id: fixture.origin.unit_id }, destination: { unit_id: fixture.destination.unit_id }, profile: fixture.profile });
  assert.equal(response.status, 200);
  assert.equal(response.profile, fixture.profile);
  for (const name of ['origin', 'destination']) {
    const {node_id, ...endpoint} = fixture[name];
    assert.deepEqual(response[name], {...endpoint, anchor_node: node_id});
  }
  assert.equal(response.reachability_algorithm, fixture.reachability.algorithm);
  assert.equal(response.component_semantics, fixture.reachability.component_semantics);
  for (const key of ["network_distance_m", "edge_ids", "edges", "steps", "provenance", "warnings"]) assert.deepEqual(response[key], fixture[key], `canonical ${key} differs`);
  assert.deepEqual(response.geometries, fixture.geometries.map(({ edge_ids, source, ...geometry }) => geometry));
  await assertScene(cdp, fixture.origin, response);
  assert.equal(await cdp.evaluate("!document.querySelector('#route-accessibility').hidden"), fixture.profile === "elevator_only");
  assert.equal(await cdp.evaluate(assistantCount), beforeAssistant);
  return response;
}
async function activate(cdp, unitId, key = null) {
  const point = await cdp.evaluate(`(() => {
    const node = document.querySelector('.unit-shape[data-unit-id="${unitId}"]');
    if (!node) throw new Error('Room missing from scene');
    node.scrollIntoView({block:'center', inline:'center'});
    if (${quote(key)} !== null) { node.focus(); return document.activeElement === node; }
    const rect = node.getBoundingClientRect();
    for (let i=1;i<20;i++) for (let j=1;j<20;j++) {
      const x=rect.left+rect.width*i/20,y=rect.top+rect.height*j/20;
      if (document.elementFromPoint(x,y) === node) return {x,y};
    }
    throw new Error('No visible pointer hit point inside room');
  })()`);
  if (key) {
    assert.equal(point, true, "room could not receive focus");
    const props = { key, code: key === "Enter" ? "Enter" : "Space", windowsVirtualKeyCode: key === "Enter" ? 13 : 32 };
    await cdp.call("Input.dispatchKeyEvent", { type: "rawKeyDown", ...props });
    await cdp.call("Input.dispatchKeyEvent", { type: "keyUp", ...props });
  } else for (const type of ["mousePressed", "mouseReleased"]) await cdp.call("Input.dispatchMouseEvent", { type, ...point, button: "left", clickCount: 1 });
}
async function chooseFloor(cdp, levelId) {
  const facilityId = await cdp.evaluate(`window.__requests.find(r=>r.url==='/demo/v1/levels'&&r.done).response.levels.find(l=>l.level_id===${quote(levelId)}).facility_id`);
  if (await cdp.evaluate("document.querySelector('#facility-select').value") !== facilityId) {
    await activateButton(cdp, `#building-buttons [data-building-id="${facilityId}"]`);
  }
  await activateButton(cdp, `#floor-buttons [data-level-id="${levelId}"]`);
}
async function submitPair(cdp,origin,destination,profile='default') {
  await chooseFloor(cdp,origin.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(origin.level_id)}`);
  const before=await cdp.evaluate(`${routes}.length`);
  await cdp.evaluate(`
    document.querySelector('#route-destination').value='';
    document.querySelector('#route-origin').value=${quote(origin.unit_id)};
    document.querySelector('#route-profile').value=${quote(profile)};
    document.querySelector('#route-origin').dispatchEvent(new Event('change', { bubbles: true }));
  `);
  await cdp.wait(`document.querySelector('#route-options-status').dataset.state==='ready'
    && document.querySelector('#route-options-status').dataset.originUnitId===${quote(origin.unit_id)}
    && document.querySelector('#route-options-status').dataset.profile===${quote(profile)}`);
  const listed=await cdp.evaluate(`!!document.querySelector('#route-destination option[value="${destination.unit_id}"]')`);
  if (listed) {
    await cdp.evaluate(`
      document.querySelector('#route-destination').value=${quote(destination.unit_id)};
      document.querySelector('#route-form').requestSubmit();
    `);
  } else {
    await chooseFloor(cdp,destination.level_id);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(destination.level_id)}`);
    await activateButton(cdp,`#room-list [data-unit-id="${destination.unit_id}"]`);
  }
  await cdp.wait(`${routes}[${before}]?.done && ['success','error'].includes(document.querySelector('#route-status').dataset.state)`);
  assert.equal(await cdp.evaluate(`${routes}.length`),before+1);
  const response=await cdp.evaluate(`${routes}[${before}].response`);
  if(response.status===200){verifyGuidance(response);await assertScene(cdp,origin,response);}
  return response;
}

async function requestedRoutes(cdp,label,viewport) {
  const units=await cdp.evaluate("window.__requests.find(r=>r.url==='/demo/v1/units'&&r.done).response.units");
  function room(id){const matches=units.filter(u=>u.room_id===id);assert.equal(matches.length,1,`room ${id} must resolve uniquely`);return matches[0];}
  const origin=room('AQ1003'),destination=room('AQ5053.2');
  viewport.requestedRoutes={};
  for(const [name,a,b] of [['screenshot',origin,destination],['screenshot_reverse',destination,origin]]){
    const response=await submitPair(cdp,a,b);
    assert.equal(response.status,200,`requested ${name} no longer routes`);
    const record=viewport.requestedRoutes[name]={origin:a.unit_id,destination:b.unit_id,profile:response.profile,edgeIds:response.edge_ids,distanceM:response.network_distance_m,provenance:response.provenance};
    await exerciseGuidance(cdp,response,record);
    const walking=response.guidance.steps.find(s=>s.kind==='walk');
    if(walking)await activateButton(cdp,`button[data-step-id="${walking.step_id}"]`);
    record.screenshot=await screenshot(cdp,`${label}-${name}`,false);
  }
  const ecc=units.filter(u=>u.level_id?.includes('_ECC_')).sort((a,b)=>a.unit_id.localeCompare(b.unit_id));
  assert.ok(ecc.length>=2,'ECC catalog absent');
  await chooseFloor(cdp,ecc[0].level_id);
  await cdp.wait(sceneReady(ecc[0]));
  assert.ok((await cdp.evaluate("document.querySelector('#viewing-floor').textContent")).includes('ECC'));
  const record=viewport.ecc={levelId:ecc[0].level_id,attempts:[]};
  for(let i=1;i<Math.min(ecc.length,12);i++){
    const response=await submitPair(cdp,ecc[0],ecc[i]);
    record.attempts.push({origin:ecc[0].unit_id,destination:ecc[i].unit_id,status:response.status,code:response.code||null});
    if(response.status===200&&response.network_distance_m>0){
      record.origin=ecc[0].unit_id;record.destination=ecc[i].unit_id;
      record.edgeIds=response.edge_ids;record.distanceM=response.network_distance_m;record.provenance=response.provenance;
      await exerciseGuidance(cdp,response,record);
      record.screenshot=await screenshot(cdp,`${label}-ecc`,false);
      return;
    }
    assert.ok([200,409,422].includes(response.status),'unexpected ECC service failure');
  }
  record.limitation='No distinct-anchor connected pair among the first 11 tested destinations; failures recorded, no connection inferred.';
}

async function latestStepWins(cdp) {
  const body=await submit(cdp,fixtures.aq_elevator);
  const first=body.guidance.steps[0],last=body.guidance.steps.at(-1);
  await activateButton(cdp,`button[data-step-id="${last.step_id}"]`);
  await assertSelected(cdp,body,last);
  await cdp.evaluate(`window.__release=null;window.__released=false;window.__holdPath=${quote(`/demo/v1/levels/${first.level_id}/scene`)}`);
  await activateButton(cdp,`button[data-step-id="${first.step_id}"]`);
  await cdp.wait("typeof window.__release==='function'");
  await activateButton(cdp,`button[data-step-id="${last.step_id}"]`);
  await assertSelected(cdp,body,last);
  await cdp.evaluate('window.__release()');
  await cdp.wait('window.__released');
  await cdp.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  await assertSelected(cdp,body,last);
  results.checks.push('delayed step scene cannot replace the newest selected instruction or floor');

  await cdp.evaluate(`window.__release=null;window.__released=false;window.__holdPath=${quote(`/demo/v1/levels/${first.level_id}/scene`)}`);
  await activateButton(cdp,`button[data-step-id="${first.step_id}"]`);
  await cdp.wait("typeof window.__release==='function'");
  await activateButton(cdp,'#route-clear');
  await cdp.evaluate('window.__release()');
  await cdp.wait('window.__released');
  await cdp.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  assert.equal(await cdp.evaluate("document.querySelectorAll('.route-selected,.route-marker,button[data-step-id][aria-current=step]').length"),0);
  results.checks.push('Clear during step loading cannot restore an old highlight or marker');
}

async function actionableOrigin(cdp,label,viewport) {
  const units=await cdp.evaluate("window.__requests.find(r=>r.url==='/demo/v1/units'&&r.done).response.units");
  const origin=units.find(u=>u.room_id==='AQ6071');
  const destination=units.find(u=>u.room_id==='AQ6067');
  assert.ok(origin&&destination);
  const failure=await submitPair(cdp,origin,fixtures.strand_corridor.destination);
  assert.equal(failure.status,409);
  const oldError=await cdp.evaluate("document.querySelector('#route-status').textContent");
  await chooseFloor(cdp,origin.level_id);
  await cdp.wait(sceneReady(origin));
  await activate(cdp,origin.unit_id);
  await waitOptions(cdp,origin.unit_id,'default');
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),'');
  assert.notEqual(await cdp.evaluate("document.querySelector('#route-status').textContent"),oldError,
    'new map origin must remove the previous pair failure');
  const choices=await cdp.evaluate("[...document.querySelectorAll('#route-destination option[data-availability=connected]')].map(n=>({id:n.value,text:n.textContent}))");
  assert.equal(choices.length,1);
  assert.equal(choices[0].id,destination.unit_id);
  assert.ok(choices[0].text.includes('AQ6067'));
  const before=await cdp.evaluate(`${routes}.length`);
  await cdp.evaluate(`document.querySelector('#route-destination').value=${quote(destination.unit_id)};document.querySelector('#route-destination').dispatchEvent(new Event('change',{bubbles:true}));`);
  await cdp.wait(`${routes}[${before}]?.done&&document.querySelector('#route-status').dataset.state==='success'`);
  const body=await cdp.evaluate(`${routes}[${before}].response`);
  assert.equal(body.status,200);
  const walk=body.guidance.steps.find(s=>s.kind==='walk');
  await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);
  await assertSelected(cdp,body,walk);
  viewport.actionableOrigin={origin:origin.unit_id,destination:destination.unit_id,distanceM:body.network_distance_m,
    screenshot:await screenshot(cdp,`${label}-aq6071-mapped-destination`,Number(label.split('x')[0])<600)};
}

async function routeCamera(cdp,label,viewport) {
  const units=await cdp.evaluate("window.__requests.find(r=>r.url==='/demo/v1/units'&&r.done).response.units");
  const room=id=>{const matches=units.filter(u=>u.room_id===id);assert.equal(matches.length,1);return matches[0];};
  const response=await submitPair(cdp,room('AQ303'),room('AQ3149'));
  assert.equal(response.status,200);
  const levelId=response.guidance.steps[0].level_id;
  const points=response.guidance.geometries.filter(g=>g.level_id===levelId).flatMap(g=>g.geometry.coordinates)
    .concat(response.guidance.markers.filter(m=>m.level_id===levelId).map(m=>m.coordinates));
  assert.ok(points.length>2);
  async function contained() {
    const bounds=await cdp.evaluate(`(() => {
      const svg=document.querySelector('#floor-map'),r=svg.getBoundingClientRect(),m=svg.getScreenCTM();
      const ox=Number(svg.dataset.originX),oy=Number(svg.dataset.originY);
      const pathsFit=${quote(points)}.every(([x,y])=>{const p=new DOMPoint(x-ox,oy-y).matrixTransform(m);
        return p.x>=r.left+1&&p.x<=r.right-1&&p.y>=r.top+1&&p.y<=r.bottom-1;});
      const markersFit=[...svg.querySelectorAll('.route-marker circle')].every(n=>{const b=n.getBoundingClientRect();
        return b.left>=r.left+2&&b.right<=r.right-2&&b.top>=r.top+2&&b.bottom<=r.bottom-2;});
      return pathsFit&&markersFit;
    })()`);
    assert.ok(bounds,'initial/current-floor route must fit inside the visible SVG, not just exist in its DOM');
  }
  const box=()=>cdp.evaluate("document.querySelector('#floor-map').getAttribute('viewBox').split(' ').map(Number)");
  await contained();
  const initial=await box();
  const selected=await cdp.evaluate("document.querySelector('button[data-step-id][aria-current=step]').dataset.stepId");
  const originBefore=await sceneOrigin(cdp);
  viewport.camera={origin:response.origin.unit_id,destination:response.destination.unit_id,distanceM:response.network_distance_m,initial};
  viewport.camera.screenshot=await screenshot(cdp,`${label}-camera-initial`,Number(label.split('x')[0])<600);
  await activateButton(cdp,'#zoom-out','Enter');
  const expanded=await box();
  assert.ok(expanded[2]>initial[2]&&expanded[3]>initial[3],'map zoom out must expand the SVG camera');
  await contained();
  await activateButton(cdp,'#zoom-in',' ');
  const restored=await box();
  restored.forEach((v,i)=>assert.ok(Math.abs(v-initial[i])<1e-6));
  assert.equal(await cdp.evaluate("document.querySelector('button[data-step-id][aria-current=step]').dataset.stepId"),selected);
  assert.deepEqual(await sceneOrigin(cdp),originBefore);
  assert.equal(await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId"),levelId);
  await activateButton(cdp,'#zoom-in');
  assert.ok((await box())[2]<initial[2]);
  await activateButton(cdp,'#fit-route');
  await contained();
  const reset=await box();
  reset.forEach((v,i)=>assert.ok(Math.abs(v-initial[i])<1e-6));
  const walk=response.guidance.steps.find(s=>s.kind==='walk');
  await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);
  await assertSelected(cdp,response,walk);
  await activateButton(cdp,'#fit-floor');
  await contained();
  await activateButton(cdp,'#fit-route');
  await contained();
  viewport.camera.expanded=expanded;
  viewport.camera.reset=reset;
}

async function waitOptions(cdp,origin,profile) {
  try {
    await cdp.wait(`(() => {const n=document.querySelector('#route-options-status');return n?.dataset.state==='ready'&&n.dataset.originUnitId===${quote(origin)}&&n.dataset.profile===${quote(profile)};})()`);
  } catch (error) {
    const state=await cdp.evaluate(`(() => {const node=document.querySelector('#route-options-status');return {
      origin:document.querySelector('#route-origin').value,destination:document.querySelector('#route-destination').value,
      state:node.dataset.state,stateOrigin:node.dataset.originUnitId,stateProfile:node.dataset.profile,text:node.textContent,
      latest:window.__requests.filter(item=>item.url.startsWith('/demo/v1/route-options?')).at(-1),errors:window.__errors};})()`);
    throw new Error(`${error.message}; state=${JSON.stringify(state)}`);
  }
  const response=await cdp.evaluate(`window.__requests.filter(r=>r.done&&r.url.startsWith('/demo/v1/route-options?')&&r.response.origin_unit_id===${quote(origin)}&&r.response.profile===${quote(profile)}).at(-1)?.response`);
  assert.equal(response?.version,'route-options-v1');
  const actual=await cdp.evaluate(`[...document.querySelectorAll('#route-destination option[data-availability="connected"]')].map(n=>n.value).sort()`);
  assert.deepEqual(actual,response.destinations.filter(d=>d.availability==='connected').map(d=>d.unit_id).sort());
  assert.equal(actual.length,response.counts.connected);
  return response;
}

async function exerciseRouteChoices(cdp,viewport) {
  const originFixture=fixtures.strand_corridor.origin;
  const origin=originFixture.unit_id;
  const destination=fixtures.strand_corridor.destination.unit_id;
  await activateButton(cdp,'#route-clear');
  await chooseFloor(cdp,originFixture.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(originFixture.level_id)}`);
  assert.equal(await cdp.evaluate(`!!document.querySelector('#route-origin option[value="${origin}"]')`),true,
    'route-choice origin is missing from its viewed-floor dropdown');
  await cdp.evaluate(`document.querySelector('#route-profile').value='default';document.querySelector('#route-origin').value=${quote(origin)};document.querySelector('#route-origin').dispatchEvent(new Event('change'));`);
  const options=await waitOptions(cdp,origin,'default');
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),'','availability must not choose a destination');
  assert.ok(options.destinations.some(d=>d.unit_id===destination&&d.availability==='connected'));
  const before=await cdp.evaluate(`${routes}.length`);
  await cdp.evaluate(`document.querySelector('#route-destination').value=${quote(destination)};document.querySelector('#route-destination').dispatchEvent(new Event('change'));`);
  await cdp.wait(`${routes}[${before}]?.done&&document.querySelector('#route-status').dataset.state==='success'`);
  const body=await cdp.evaluate(`${routes}[${before}].response`);
  assert.ok(body.network_distance_m>0);
  const walk=body.guidance.steps.find(s=>s.kind==='walk');
  await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);
  await assertSelected(cdp,body,walk);
  for (const [expectedOrigin,expectedDestination] of [[destination,origin],[origin,destination]]) {
    const beforeSwap=await cdp.evaluate(`${routes}.length`);
    await activateButton(cdp,'#route-swap');
    await cdp.wait(`${routes}[${beforeSwap}]?.done&&document.querySelector('#route-status').dataset.state==='success'`);
    await waitOptions(cdp,expectedOrigin,'default');
    assert.equal(await cdp.evaluate("document.querySelector('#route-origin').value"),expectedOrigin);
    assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),expectedDestination);
    const swapped=await cdp.evaluate(`${routes}[${beforeSwap}].response`);
    assert.equal(swapped.status,200);
    assert.ok(swapped.network_distance_m>0);
    const swappedWalk=swapped.guidance.steps.find(s=>s.kind==='walk');
    await activateButton(cdp,`button[data-step-id="${swappedWalk.step_id}"]`);
    await assertSelected(cdp,swapped,swappedWalk);
  }
  const unavailable=options.destinations.find(d=>d.availability==='disconnected');
  assert.ok(unavailable);
  const units=await cdp.evaluate("window.__requests.find(r=>r.url==='/demo/v1/units'&&r.done).response.units");
  const originUnit=units.find(unit=>unit.unit_id===origin);
  const unavailableUnit=units.find(unit=>unit.unit_id===unavailable.unit_id);
  assert.ok(originUnit&&unavailableUnit);
  await activateButton(cdp,'#route-clear');
  await chooseFloor(cdp,originUnit.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(originUnit.level_id)}`);
  await activateButton(cdp,`#room-list [data-unit-id="${origin}"]`);
  await waitOptions(cdp,origin,'default');
  await chooseFloor(cdp,unavailableUnit.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(unavailableUnit.level_id)}`);
  const beforeFailure=await cdp.evaluate(`${routes}.length`);
  await activateButton(cdp,`#room-list [data-unit-id="${unavailable.unit_id}"]`);
  await cdp.wait(`${routes}[${beforeFailure}]?.done&&document.querySelector('#route-status').dataset.state==='error'`);
  assert.equal(await cdp.evaluate(`${routes}[${beforeFailure}].response.status`),409);
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),unavailable.unit_id,'unsupported choice was silently replaced');
  assert.equal(await cdp.evaluate("document.querySelector('#current-instruction').textContent"),await cdp.evaluate("document.querySelector('#route-status').textContent"),'map-adjacent card hides the routing failure');
  assert.equal(await cdp.evaluate("document.querySelector('.current-step').hidden"),false,'map-adjacent routing failure is hidden');
  await cdp.evaluate("document.querySelector('#route-profile').value='elevator_only';document.querySelector('#route-profile').dispatchEvent(new Event('change'));");
  const elevator=await waitOptions(cdp,origin,'elevator_only');
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),unavailable.unit_id);
  assert.equal(await cdp.evaluate("document.querySelector('#route-profile').value"),'elevator_only');
  viewport.routeChoices={origin,connectedDestination:destination,unsupportedDestination:unavailable.unit_id,defaultCounts:options.counts,elevatorCounts:elevator.counts};
}

async function latestOptionsWin(cdp) {
  const firstFixture=fixtures.strand_corridor.origin;
  const newestFixture=fixtures.aq_elevator.origin;
  const first=firstFixture.unit_id;
  const newest=newestFixture.unit_id;
  const heldPath=`/demo/v1/route-options?origin_unit_id=${encodeURIComponent(first)}&profile=default`;
  await chooseFloor(cdp,firstFixture.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(firstFixture.level_id)}`);
  await activateButton(cdp,'#route-clear');
  await cdp.evaluate(`document.querySelector('#route-profile').value='default';window.__release=null;window.__released=false;window.__holdPath=${quote(heldPath)};document.querySelector('#route-origin').value=${quote(first)};document.querySelector('#route-origin').dispatchEvent(new Event('change'));`);
  await cdp.wait("typeof window.__release==='function'");
  await chooseFloor(cdp,newestFixture.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(newestFixture.level_id)}`);
  await cdp.evaluate(`document.querySelector('#route-origin').value=${quote(newest)};document.querySelector('#route-origin').dispatchEvent(new Event('change'));`);
  await waitOptions(cdp,newest,'default');
  const before=await cdp.evaluate("document.querySelector('#route-destination').innerHTML");
  await cdp.evaluate('window.__release()');
  await cdp.wait('window.__released');
  await cdp.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  await waitOptions(cdp,newest,'default');
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').innerHTML"),before);
  await chooseFloor(cdp,firstFixture.level_id);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${quote(firstFixture.level_id)}`);
  await cdp.evaluate(`window.__release=null;window.__released=false;window.__holdPath=${quote(heldPath)};document.querySelector('#route-origin').value=${quote(first)};document.querySelector('#route-origin').dispatchEvent(new Event('change'));`);
  await cdp.wait("typeof window.__release==='function'");
  await activateButton(cdp,'#route-clear');
  await cdp.evaluate('window.__release()');
  await cdp.wait('window.__released');
  await cdp.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  assert.equal(await cdp.evaluate("document.querySelector('#route-options-status').dataset.state"),'empty');
  assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),'');
  results.checks.push('delayed availability cannot overwrite the latest origin or repopulate choices after Clear');
}

async function run() {
  fs.mkdirSync(outputDir, { recursive: true });
  // Replace one authoritative status file; old images cannot imply success.
  fs.writeFileSync(path.join(outputDir, "results.json"), JSON.stringify(results, null, 2));
  const proc = spawn("/ms-playwright/chromium-1140/chrome-linux/chrome", [
    "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--remote-debugging-pipe", "about:blank",
  ], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
  const cdp = new Cdp(proc);
  try {
    results.browser = await cdp.call("Browser.getVersion");
    const { targetId } = await cdp.call("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.call("Target.attachToTarget", { targetId, flatten: true });
    cdp.sessionId = sessionId;
    await cdp.call("Page.enable");
    await cdp.call("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
      window.__requests=[]; window.__errors=[];
      addEventListener('error',e=>__errors.push(String(e.error||e.message)));
      addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));
      const original=window.fetch;
      window.fetch=async(url,options)=>{
        const hold=window.__holdPath===String(url); if(hold)window.__holdPath=null;
        const entry={url:String(url),method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null};
        __requests.push(entry);
        const response=await original(url,options);
        entry.response=await response.clone().json(); entry.done=true;
        if(hold){await new Promise(resolve=>{window.__release=resolve;});window.__released=true;}
        return response;
      };
    })();` });
    await cdp.call("Page.navigate", { url: `${targetUrl.origin}/` });
    await cdp.wait("document.querySelector('#campus-view') && !document.querySelector('#campus-view').hidden && document.querySelectorAll('#route-origin option').length>1");
    for (const [width,height,key] of [[1440,1000,"Enter"],[390,844," "]]) {
      const label=`${width}x${height}`;
      await cdp.call("Emulation.setDeviceMetricsOverride", { width,height,deviceScaleFactor:1,mobile:width<600 });
      const viewport=results.viewports[label]={fixtures:{},interactions:[]};
      viewport.campus=await exerciseCampus(cdp,screenshot,label,width);
      await routeCamera(cdp,label,viewport);
      for(const [name,fixture] of Object.entries(fixtures)) {
        assert.ok(["default","elevator_only"].includes(fixture.profile));
        const response=await submit(cdp,fixture);
        viewport.fixtures[name]={distanceM:response.network_distance_m,edgeCount:response.edge_ids.length};
        await exerciseGuidance(cdp,response,viewport.fixtures[name]);
        viewport.fixtures[name].screenshot=await screenshot(cdp,`${label}-${name}`,width<600);
        const walk=response.guidance.steps.find(s=>s.kind==='walk');
        if(walk){
          await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);
          await assertSelected(cdp,response,walk);
          viewport.fixtures[name].walkingScreenshot=await screenshot(cdp,`${label}-${name}-walking`,width<600);
        }
        if(name==='aq_elevator') {
          const departure=response.guidance.steps.find(s=>s.kind==='transition'&&s.phase==='departure');
          await activateButton(cdp,`button[data-step-id="${departure.step_id}"]`);
          await assertSelected(cdp,response,departure);
          viewport.fixtures[name].departureScreenshot=await screenshot(cdp,`${label}-${name}-departure`,width<600);
          await activateButton(cdp,'#transition-arrival');
          await assertSelected(cdp,response,response.guidance.steps.find(s=>s.transition_id===departure.transition_id&&s.phase==='arrival'));
          viewport.fixtures[name].arrivalScreenshot=await screenshot(cdp,`${label}-${name}-arrival`,width<600);
          assert.deepEqual(await submit(cdp,fixture,true),response);
          await activateButton(cdp,`button[data-step-id="${response.guidance.steps.at(-1).step_id}"]`);
          await assertScene(cdp,fixture.destination,response);
          viewport.interactions.push("mobility-chat parity","cross-floor final-step navigation");
        }
      }
      const pair=fixtures.strand_corridor;
      await cdp.evaluate("document.querySelector('#route-clear').click()");
      const before=await cdp.evaluate(`${routes}.length`);
      await activate(cdp,pair.origin.unit_id);
      assert.equal(await cdp.evaluate("document.querySelector('#route-origin').value"),pair.origin.unit_id);
      assert.equal(await cdp.evaluate(`${routes}.length`),before);
      await activate(cdp,pair.destination.unit_id,key);
      await cdp.wait(`${routes}[${before}]?.done && document.querySelector('#route-status').dataset.state === 'success'`);
      const response=await cdp.evaluate(`${routes}[${before}].response`);
      assert.deepEqual(response.edge_ids,pair.edge_ids);
      assert.equal(await cdp.evaluate(`${routes}.length`),before+1);
      await assertScene(cdp,pair.origin,response);
      viewport.interactions.push("SVG pointer origin",key==='Enter'?"SVG Enter destination":"SVG Space destination");
      const layout=await cdp.evaluate(`(() => {
        const map=document.querySelector('.map-panel').getBoundingClientRect(),side=document.querySelector('.side-panel').getBoundingClientRect();
        const controls=[...document.querySelectorAll('select,input,.route-actions button')].filter(n=>n.checkVisibility()).map(n=>{const r=n.getBoundingClientRect();return {id:n.id,left:r.left,right:r.right,width:r.width,height:r.height};});
        return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,separated:map.right<=side.left+1||map.bottom<=side.top+1,controls};
      })()`);
      assert.ok(layout.scrollWidth<=width+1&&layout.separated,"panels overflow or overlap");
      assert.ok(layout.controls.every(r=>r.left>=0&&r.right<=width+1),`control clipped horizontally: ${JSON.stringify(layout.controls.filter(r=>r.left<0||r.right>width+1))}`);
      viewport.layout=layout;
      viewport.screenshot=await screenshot(cdp,`${label}-interactions`,width<600);
      await requestedRoutes(cdp,label,viewport);
      await exerciseRouteChoices(cdp,viewport);
      viewport.routeChoices.screenshot=await screenshot(cdp,`${label}-route-choice-failure`,width<600);
      await actionableOrigin(cdp,label,viewport);
      console.log(`${label}: all ${Object.keys(fixtures).length} fixtures, parity, floor steps, pointer/keyboard and layout passed`);
    }
    const pair = fixtures.strand_corridor;
    await submit(cdp,pair);
    const beforeCorrection = await cdp.evaluate(`${routes}.length`);
    await cdp.evaluate(`
      document.querySelector('#route-destination').value = '';
      document.querySelector('#route-destination').dispatchEvent(new Event('change'));
    `);
    assert.equal(await cdp.evaluate(`${routes}.length`), beforeCorrection);
    assert.equal(await cdp.evaluate("document.querySelectorAll('#route-overlay path').length"), 0);
    await activate(cdp, pair.destination.unit_id, "Enter");
    await cdp.wait(`${routes}[${beforeCorrection}]?.done && document.querySelector('#route-status').dataset.state === 'success'`);
    assert.equal(await cdp.evaluate("document.querySelector('#route-origin').value"), pair.origin.unit_id);
    assert.equal(await cdp.evaluate(`${routes}.length`), beforeCorrection + 1);
    await assertScene(cdp, pair.origin, await cdp.evaluate(`${routes}[${beforeCorrection}].response`));
    results.checks.push("manual incomplete pair retains origin and submits only after correction");

    const beforeFailure = await cdp.evaluate(`${routes}.length`);
    const failure = await submitPair(cdp,fixtures.aq_elevator.origin,pair.destination,'elevator_only');
    assert.equal(failure.status, 409);
    assert.equal(failure.code, 'no_elevator_only_route');
    assert.equal(await cdp.evaluate(`${routes}.length`), beforeFailure + 1);
    assert.deepEqual(await cdp.evaluate(`${routes}[${beforeFailure}].body`), {
      origin: {unit_id: fixtures.aq_elevator.origin.unit_id},
      destination: {unit_id: pair.destination.unit_id}, profile: 'elevator_only',
    });
    assert.ok((await cdp.evaluate("document.querySelector('.route-panel').textContent")).includes(failure.code));
    assert.equal(await cdp.evaluate("document.querySelectorAll('#route-overlay path').length"), 0);
    assert.equal(await cdp.evaluate("document.querySelector('#route-accessibility').hidden"), false);
    const disclosure = await cdp.evaluate("document.querySelector('#route-accessibility').textContent");
    assert.ok(disclosure.toLowerCase().includes('stairs excluded'));
    const details = await cdp.evaluate("document.querySelector('.route-panel').textContent.toLowerCase()");
    for (const term of ['door width', 'path width', 'slope', 'powered doors', 'surface']) assert.ok(details.includes(term));
    results.checks.push("disconnected elevator-only route clears geometry and preserves disclosures");
    results.failureScreenshot = await screenshot(cdp, '390x844-disconnected', true);

    const old=fixtures.aq_stairs.origin,current=fixtures.aq_elevator.origin;
    await cdp.evaluate(`window.__holdPath=${quote(`/demo/v1/levels/${old.level_id}/scene`)}`);
    await chooseFloor(cdp,old.level_id);
    await cdp.wait("typeof window.__release === 'function'");
    await chooseFloor(cdp,current.level_id);
    await cdp.wait(sceneReady(current));
    const scene=await cdp.evaluate("document.querySelector('#floor-map').innerHTML");
    await cdp.evaluate("window.__release()");
    await cdp.wait("window.__released");
    await cdp.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
    assert.equal(await cdp.evaluate("document.querySelector('#floor-map').innerHTML"),scene);
    results.checks.push("delayed old scene cannot replace current floor");
    await latestStepWins(cdp);
    await latestOptionsWin(cdp);
    await cdp.call('Emulation.setDeviceMetricsOverride',{width:320,height:844,deviceScaleFactor:1,mobile:true});
    results.narrowCampus=await exerciseCampus(cdp,screenshot,'320x844',320);
    const narrow=await submit(cdp,fixtures.strand_corridor);
    const step=narrow.guidance.steps.find(s=>s.kind==='walk');
    await activateButton(cdp,`button[data-step-id="${step.step_id}"]`);
    await assertSelected(cdp,narrow,step);
    await cdp.call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await activateButton(cdp,'#step-next','Enter');
    assert.ok(await cdp.evaluate('document.documentElement.scrollWidth<=320'),'320px layout overflows');
    results.narrowScreenshot=await screenshot(cdp,'320x844-selected',false);
    results.checks.push('320px layout and reduced-motion step navigation');
    assert.deepEqual(await cdp.evaluate("window.__errors"),[]);
    results.requestCounts=await cdp.evaluate("({read:__requests.filter(r=>r.method==='GET').length,post:__requests.filter(r=>r.method==='POST').length})");
    results.status="passed";
  } catch(error) {
    results.diagnostic=await cdp.evaluate(`({selected:document.querySelector('button[data-step-id][aria-current="step"]')?.dataset.stepId,focused:document.activeElement?.outerHTML,floor:document.querySelector('#viewing-floor')?.textContent,status:document.querySelector('#map-status')?.textContent,errors:window.__errors})`).catch(()=>null);
    results.errorScreenshot=await screenshot(cdp,'failure-state',false).catch(()=>null);
    throw error;
  } finally { proc.kill("SIGTERM"); }
}
run().catch(error=>{
  results.status="failed"; results.error=error.stack;
  console.error(error.stack); process.exitCode=1;
}).finally(()=>{
  results.finishedAt=new Date().toISOString();
  fs.writeFileSync(path.join(outputDir,"results.json"),JSON.stringify(results,null,2));
});
