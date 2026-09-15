"use strict";

const assert = require('node:assert/strict');
const {activateButton} = require('./guidance.cjs');

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
  const controlsBefore = await cdp.evaluate("[document.querySelector('#facility-select').value,Number(document.querySelector('#level-select').value)]");
  await cdp.evaluate(`(() => {const input=document.querySelector('#campus-search');input.value=${JSON.stringify(facility.code)};input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  assert.deepEqual(await cdp.evaluate("document.querySelector('#campus-map').getAttribute('viewBox').split(/\\s+/).map(Number)"),zoomed,'search preserves deliberate camera');
  const selector = `#campus-buildings [data-campus-facility-id="${facility.facility_id}"]`;
  await cdp.evaluate("window.__campusRequests=[];window.__campusOriginalFetch=window.fetch;window.fetch=async(...args)=>{window.__campusRequests.push(String(args[0]));return window.__campusOriginalFetch(...args)}");
  await activateButton(cdp, selector, 'Enter');
  assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), facility.facility_id,
    'building selection synchronizes the Building control');
  const expectedFacilityOrder = facility.levels.some(level => level.vertical_order === controlsBefore[1])
    ? controlsBefore[1] : (facility.levels.some(level => level.vertical_order === 0) ? 0 : facility.levels[0].vertical_order);
  assert.equal(Number(await cdp.evaluate("document.querySelector('#level-select').value")), expectedFacilityOrder,
    'building selection keeps or deterministically falls back global floor order');
  assert.deepEqual(await cdp.evaluate("window.__campusRequests.filter(url=>url.includes('/scene')||url.includes('/route'))"), [],
    'building selection does not request a scene or route');
  await cdp.evaluate("window.fetch=window.__campusOriginalFetch");
  assert.equal(await cdp.evaluate("document.querySelector('#map-context').textContent"), 'Building');
  const synchronizedImage = await screenshot(cdp, `${label}-campus-synchronized`, false);
  const floors = await cdp.evaluate("[...document.querySelectorAll('#campus-details [data-campus-level-id]')].map(n=>n.dataset.campusLevelId)");
  assert.deepEqual([...floors].sort(), facility.levels.map(l=>l.level_id).sort());
  assert.deepEqual(await cdp.evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value,document.querySelector('#route-profile').value]"),selectedBefore);
  await activateButton(cdp, `#campus-details [data-campus-level-id="${floors[0]}"]`);
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
  for (const [other, key] of [[ecc, 'ECC'], [strand, 'SH']]) {
    await activateButton(cdp, `#campus-buildings [data-campus-facility-id="${facility.facility_id}"]`, 'Enter');
    await activateButton(cdp, `#campus-details [data-campus-level-id="${aqOnly.level_id}"]`);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(aqOnly.level_id)}`);
    await activateButton(cdp, '#show-campus');
    const previousOrder = Number(await cdp.evaluate("document.querySelector('#level-select').value"));
    assert.equal(previousOrder, aqOnly.vertical_order);
    await activateButton(cdp, `#campus-map [data-campus-facility-id="${other.facility_id}"]`, key==='ECC' ? undefined : ' ');
    assert.ok((await cdp.evaluate("document.querySelector('#campus-details').textContent")).includes(other.name));
    assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), other.facility_id,
      `${key} footprint selection synchronizes the Building control`);
    const expectedOtherOrder = other.levels.some(level => level.vertical_order === previousOrder)
      ? previousOrder : (other.levels.some(level => level.vertical_order === 0) ? 0 : other.levels[0].vertical_order);
    assert.equal(Number(await cdp.evaluate("document.querySelector('#level-select').value")), expectedOtherOrder,
      `${key} selection keeps or falls back to a recorded global floor order`);
    assert.equal(await cdp.evaluate("document.querySelector('#map-context').textContent"), 'Building');
  }
  // A shared non-default order must be retained, regardless of local floor labels.
  const shared=facility.levels.find(level=>level.vertical_order!==0 && strand.levels.some(other=>
    other.vertical_order===level.vertical_order));
  assert.ok(shared, 'fixture must contain a shared nonzero AQ/Strand global order');
  await activateButton(cdp, `#campus-buildings [data-campus-facility-id="${facility.facility_id}"]`, 'Enter');
  await activateButton(cdp, `#campus-details [data-campus-level-id="${shared.level_id}"]`);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${JSON.stringify(shared.level_id)}`);
  await activateButton(cdp, '#show-campus');
  await activateButton(cdp, `#campus-buildings [data-campus-facility-id="${strand.facility_id}"]`, 'Enter');
  assert.equal(Number(await cdp.evaluate("document.querySelector('#level-select').value")),shared.vertical_order);
  assert.deepEqual(await cdp.evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value,document.querySelector('#route-profile').value]"),selectedBefore);
  // Hold a real floor response, then make a newer campus context choice.
  const delayedLevel=ecc.levels[0].level_id;
  await activateButton(cdp, `#campus-map [data-campus-facility-id="${ecc.facility_id}"]`, ' ');
  await cdp.evaluate(`(() => {
    window.__campusOriginalFetch=window.fetch;window.__campusReleased=false;window.__campusRelease=null;
    window.fetch=async(...args)=>{
      const response=await window.__campusOriginalFetch(...args);
      if(String(args[0])===${JSON.stringify('/demo/v1/levels/'+delayedLevel+'/scene')}) {
        await new Promise(resolve=>{window.__campusRelease=resolve;});
        window.__campusReleased=true;
      }
      return response;
    };
  })()`);
  await activateButton(cdp, `#campus-details [data-campus-level-id="${delayedLevel}"]`);
  await cdp.wait("typeof window.__campusRelease==='function'");
  await activateButton(cdp, '#show-campus');
  await activateButton(cdp, `#campus-map [data-campus-facility-id="${strand.facility_id}"]`, ' ');
  assert.equal(await cdp.evaluate("document.querySelector('#facility-select').value"), strand.facility_id,
    'latest building selection wins while an older scene response is pending');
  const latestControls=await cdp.evaluate("[document.querySelector('#facility-select').value,document.querySelector('#level-select').value]");
  await cdp.evaluate("window.fetch=window.__campusOriginalFetch;window.__campusRelease()");
  await cdp.wait("window.__campusReleased");
  await cdp.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
  assert.equal(await cdp.evaluate("document.querySelector('#campus-view').hidden"),false,'late floor response cannot replace campus');
  assert.deepEqual(await cdp.evaluate("[document.querySelector('#facility-select').value,document.querySelector('#level-select').value]"),latestControls,
    'late scene cannot restore older dropdowns');
  assert.equal(await cdp.evaluate("document.querySelector('#map-context').textContent"),'Building');
  return {version:body.version, artifactSha256:health.artifact_sha256, facilityIds:body.facilities.map(f=>f.facility_id),initial,zoomed,screenshot:image,synchronizedScreenshot:synchronizedImage};
}

module.exports = {exerciseCampus};
