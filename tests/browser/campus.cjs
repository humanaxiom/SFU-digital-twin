"use strict";

const assert = require('node:assert/strict');
const {activateButton} = require('./guidance.cjs');


async function assertFloorContext(cdp) {
  const state = await cdp.evaluate(`({
    context: document.querySelector('#map-context').textContent,
    displayed: document.querySelector('#viewing-floor').textContent,
    canReturn: !document.querySelector('#return-to-route').hidden
  })`);
  if (state.canReturn) {
    assert.equal(state.context, `Exploring ${state.displayed.replace(/^Viewing /, '')}`);
  } else {
    assert.equal(state.context, 'Floor');
  }
}

async function exerciseColdSceneRace(cdp, width, facility, strand) {
  // Prior campus and route checks may have loaded every eligible fixture floor.
  // Use a separate page for a real cold request without changing the main scenario.
  const baseUrl = await cdp.evaluate("location.href");
  const originalSession = cdp.sessionId;
  const {targetId} = await cdp.call("Target.createTarget", {url: "about:blank"});
  try {
    cdp.sessionId = (await cdp.call("Target.attachToTarget", {targetId, flatten: true})).sessionId;
    await cdp.call("Page.enable");
    await cdp.call("Emulation.setDeviceMetricsOverride", {
      width, height: width < 600 ? 844 : 1000, deviceScaleFactor: 1, mobile: width < 600,
    });
    await cdp.call("Page.navigate", {url: baseUrl});
    await cdp.wait("document.querySelector('#facility-select')?.options.length>1");
    await activateButton(cdp, `#building-buttons [data-building-id="${facility.facility_id}"]`);
    const initialLevel = await cdp.evaluate("document.querySelector('#level-select').value");
    const delayedLevel = facility.levels.find(level => level.level_id !== initialLevel)?.level_id;
    assert.ok(delayedLevel, 'fixture needs a cold AQ floor');
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(initialLevel)}
      && document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
    await cdp.evaluate(`(() => {
      const originalFetch = window.fetch;
      const delayedPath = ${JSON.stringify('/demo/v1/levels/'+delayedLevel+'/scene')};
      window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        if (String(args[0]) === delayedPath) {
          await new Promise(resolve => {window.__campusRelease = resolve;});
          window.__campusReleased = true;
        }
        return response;
      };
    })()`);
    await activateButton(cdp, `#floor-buttons [data-level-id="${delayedLevel}"]`);
    await cdp.wait("typeof window.__campusRelease==='function'");
    await activateButton(cdp, '#show-campus');
    await activateButton(cdp, `#campus-map [data-campus-facility-id="${strand.facility_id}"]`, ' ');
    assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), strand.facility_id,
      'latest building selection wins while an older scene response is pending');
    const controls = "[document.querySelector('#facility-select').value, document.querySelector('#level-select').value]";
    const latestControls = await cdp.evaluate(controls);
    await cdp.evaluate("window.__campusRelease()");
    await cdp.wait("window.__campusReleased");
    await cdp.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(latestControls[1])}
      && document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
    assert.equal(await cdp.evaluate("document.querySelector('#campus-view').hidden"), true,
      'late floor response cannot replace the newer building floor');
    assert.deepEqual(await cdp.evaluate(controls), latestControls, 'late scene cannot restore older dropdowns');
    await assertFloorContext(cdp);
  } finally {
    cdp.sessionId = originalSession;
    await cdp.call("Target.closeTarget", {targetId});
    await cdp.call("Page.bringToFront");
  }
}

// Shared by accepted-artifact and candidate-backed real Chromium gates.
async function exerciseCampus(cdp, screenshot, label, width) {
  await activateButton(cdp, '#show-campus');
  await cdp.wait("!document.querySelector('#campus-view').hidden && document.querySelectorAll('#campus-map [data-campus-facility-id]').length > 0");
  const body = await cdp.evaluate("fetch('/demo/v1/campus').then(r=>r.json())");
  assert.equal(body.version, 'campus-overview-v1');
  assert.equal(body.scope, 'three-building-pilot');
  assert.equal(body.campus_inventory_complete, false);
  assert.equal(body.facilities.length, 3);
  const health = await cdp.evaluate("fetch('/demo/v1/health').then(r=>r.json())");
  assert.equal(body.provenance.artifact_sha256, health.artifact_sha256);
  assert.deepEqual(await cdp.evaluate("fetch('/demo/v1/campus').then(r=>r.json())"), body);
  for (const facility of body.facilities) {
    assert.equal(facility.coverage, 'partial_indoor');
    assert.equal(facility.verified_building_destination, false);
    assert.equal(facility.outdoor_routing, 'unavailable');
    assert.deepEqual(facility.known_entrances, []);
    assert.ok(facility.levels.length);
  }
  await activateButton(cdp, '#campus-reset');
  const initial = await cdp.evaluate("document.querySelector('#campus-map').getAttribute('viewBox').split(/\\s+/).map(Number)");
  assert.ok(initial.every(Number.isFinite) && initial[2] > 0 && initial[3] > 0);
  const contained = await cdp.evaluate(`(() => {
    const svg=document.querySelector('#campus-map'), box=svg.getBoundingClientRect();
    return [...svg.querySelectorAll('[data-campus-facility-id]')].every(node=>{
      const r=node.getBoundingClientRect();
      return r.width>0&&r.height>0&&r.left>=box.left-1&&r.right<=box.right+1&&r.top>=box.top-1&&r.bottom<=box.bottom+1;
    });
  })()`);
  assert.ok(contained, 'all pilot footprints fit painted campus viewport');
  assert.ok(await cdp.evaluate(`document.documentElement.scrollWidth<=${width}`), 'campus viewport overflows');
  const image = await screenshot(cdp, `${label}-campus`, false);
  await activateButton(cdp, '#campus-zoom-out', 'Enter');
  const zoomed = await cdp.evaluate("document.querySelector('#campus-map').getAttribute('viewBox').split(/\\s+/).map(Number)");
  assert.ok(zoomed[2]>initial[2] && zoomed[3]>initial[3]);
  const facility = body.facilities.find(f=>f.code==='AQ') || body.facilities[0];
  const selectedBefore = await cdp.evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value,document.querySelector('#route-profile').value]");
  if (!(await cdp.evaluate("document.querySelector('#building-search').open"))) await activateButton(cdp, '#building-search summary');
  await cdp.evaluate(`(() => {const input=document.querySelector('#campus-search');input.value=${JSON.stringify(facility.code)};input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  assert.deepEqual(await cdp.evaluate("document.querySelector('#campus-map').getAttribute('viewBox').split(/\\s+/).map(Number)"),zoomed,'search preserves deliberate camera');
  const selector = `#campus-buildings [data-campus-facility-id="${facility.facility_id}"]`;
  await cdp.evaluate("window.__campusRequests=[];window.__campusOriginalFetch=window.fetch;window.fetch=async(...args)=>{window.__campusRequests.push(String(args[0]));return window.__campusOriginalFetch(...args)}");
  await activateButton(cdp, selector, 'Enter');
  assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), facility.facility_id,
    'building selection synchronizes the Building control');
  assert.ok(facility.levels.map(level => level.level_id).includes(await cdp.evaluate("document.querySelector('#level-select').value")),
    'building selection chooses an exact recorded floor belonging to that building');
  assert.deepEqual((await cdp.evaluate("[...document.querySelector('#facility-select').options].map(item=>item.value)")).sort(),
    body.facilities.map(item=>item.facility_id).sort(), 'every recorded building remains discoverable');
  assert.deepEqual((await cdp.evaluate("[...document.querySelector('#level-select').options].map(item=>item.value)")).sort(),
    facility.levels.map(item=>item.level_id).sort(), 'floor choices contain only this building exact levels');
  const selectedAfter = await cdp.evaluate("document.querySelector('#level-select').value");
  await cdp.wait(`!document.querySelector('#floor-view').hidden
    && document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(selectedAfter)}
    && !document.querySelector('#map-status').textContent.includes('Loading')`);
  await cdp.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
  const sceneRequests = await cdp.evaluate("window.__campusRequests.filter(url=>url.endsWith('/scene'))");
  assert.ok(sceneRequests.length <= 1 && sceneRequests.every(url => url === `/demo/v1/levels/${selectedAfter}/scene`),
    'building selection loads only its floor or reuses its exact cached scene');
  assert.deepEqual(await cdp.evaluate("window.__campusRequests.filter(url=>url==='/demo/v1/route')"), [],
    'building selection opens its remembered floor without requesting a route');
  await cdp.evaluate("window.fetch=window.__campusOriginalFetch");
  await assertFloorContext(cdp);
  const synchronizedImage = await screenshot(cdp, `${label}-campus-synchronized`, false);
  const floors = await cdp.evaluate("[...document.querySelectorAll('#floor-buttons [data-level-id]')].map(n=>n.dataset.levelId)");
  assert.deepEqual([...floors].sort(), facility.levels.map(l=>l.level_id).sort());
  assert.deepEqual(await cdp.evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value,document.querySelector('#route-profile').value]"),selectedBefore);
  await activateButton(cdp, `#floor-buttons [data-level-id="${floors[0]}"]`);
  await cdp.wait(`document.querySelector('#campus-view').hidden && document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(floors[0])}`);
  assert.ok(await cdp.evaluate("document.querySelectorAll('.unit-shape').length>0"));
  await activateButton(cdp, '#show-campus');
  await cdp.evaluate("document.querySelector('#campus-search').value='';document.querySelector('#campus-search').dispatchEvent(new Event('input',{bubbles:true}))");
  await activateButton(cdp, '#campus-reset');
  assert.deepEqual(await cdp.evaluate("document.querySelector('#campus-map').getAttribute('viewBox').split(/\\s+/).map(Number)"),initial);
  const ecc=body.facilities.find(f=>f.code==='ECC');
  const strand=body.facilities.find(f=>f.code==='SH');
  const aqOnly=facility.levels.find(level=>[ecc,strand].every(other=>
    !other.levels.some(candidate=>candidate.vertical_order===level.vertical_order)));
  assert.ok(aqOnly, 'fixture must contain an AQ-only global order');
  const remembered = new Map();
  for (const [other, key] of [[ecc, 'ECC'], [strand, 'SH']]) {
    await activateButton(cdp, `#building-buttons [data-building-id="${facility.facility_id}"]`, 'Enter');
    await activateButton(cdp, `#floor-buttons [data-level-id="${aqOnly.level_id}"]`);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(aqOnly.level_id)}`);
    await activateButton(cdp, '#show-campus');
    assert.equal(await cdp.evaluate("document.querySelector('#level-select').value"), aqOnly.level_id);
    await activateButton(cdp, `#campus-map [data-campus-facility-id="${other.facility_id}"]`, key==='ECC' ? undefined : ' ');
    assert.ok((await cdp.evaluate("document.querySelector('#campus-details').textContent")).includes(other.name));
    assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), other.facility_id,
      `${key} footprint selection synchronizes the Building control`);
    const selectedLevel = await cdp.evaluate("document.querySelector('#level-select').value");
    assert.ok(other.levels.some(level=>level.level_id===selectedLevel), `${key} selection belongs to its exact recorded floors`);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(selectedLevel)} && !document.querySelector('#map-status').textContent.includes('Loading')`);
    // Deliberately inspect a known floor, then leave it: later building selection
    // must remember this floor rather than inherit another building's global order.
    const rememberedLevel = other.levels.at(-1).level_id;
    await activateButton(cdp, `#floor-buttons [data-level-id="${rememberedLevel}"]`);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(rememberedLevel)}`);
    remembered.set(other.facility_id, rememberedLevel);
    await activateButton(cdp, '#show-campus');
    await activateButton(cdp, `#campus-buildings [data-campus-facility-id="${other.facility_id}"]`, 'Enter');
    assert.equal(await cdp.evaluate("document.querySelector('#level-select').value"), rememberedLevel,
      `${key} remembers its own inspected exact floor`);
    await assertFloorContext(cdp);
  }
  // Visiting a shared global order in AQ cannot replace Strand's remembered floor.
  const shared=facility.levels.find(level=>level.vertical_order!==0 && strand.levels.some(other=>
    other.vertical_order===level.vertical_order));
  assert.ok(shared, 'fixture must contain a shared nonzero AQ/Strand global order');
  await activateButton(cdp, `#building-buttons [data-building-id="${facility.facility_id}"]`, 'Enter');
  await activateButton(cdp, `#floor-buttons [data-level-id="${shared.level_id}"]`);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(shared.level_id)}`);
  await activateButton(cdp, '#show-campus');
  await activateButton(cdp, `#campus-buildings [data-campus-facility-id="${strand.facility_id}"]`, 'Enter');
  assert.equal(await cdp.evaluate("document.querySelector('#level-select').value"),remembered.get(strand.facility_id));
  assert.deepEqual(await cdp.evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value,document.querySelector('#route-profile').value]"),selectedBefore);
  await exerciseColdSceneRace(cdp, width, facility, strand);
  return {version:body.version, artifactSha256:health.artifact_sha256, facilityIds:body.facilities.map(f=>f.facility_id),initial,zoomed,screenshot:image,synchronizedScreenshot:synchronizedImage};
}

module.exports = {exerciseCampus};
