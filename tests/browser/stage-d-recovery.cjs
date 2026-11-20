"use strict";
// Stage D N10–N12: real canonical routes plus explicitly labeled failure injection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createBrowserGate} = require('./room-search.cjs');
const gate = createBrowserGate('stage-d-recovery');
const {cdp, proc, result, outputDir, pointerClick, key, field, typeQuery, resultClick, activateChoice, prepareViewport, screenshot} = gate;
const q = JSON.stringify;
async function keyboard(selector) {
  assert.equal(await cdp.evaluate(`(()=>{const n=document.querySelector(${q(selector)});n.focus();return n===document.activeElement&&!n.disabled&&n.checkVisibility()})()`),true);
  await key('Enter');
}
async function choose(role, room) {
  const finder = `#route-${role}-finder`, search = `#route-${role}-search`;
  if (!(await field(finder,'open'))) await pointerClick(`${finder} > summary`);
  await typeQuery(search, room.room_id);
  await resultClick(`${search}-results`, room.unit_id);
  await activateChoice(search,false);
  await cdp.wait(`document.querySelector('#route-${role}').value===${q(room.unit_id)}`);
}
async function draft(a,b) {
  await pointerClick('#route-clear');
  await choose('origin',a);
  await cdp.wait("['ready','error'].includes(document.querySelector('#route-options-status').dataset.state)");
  await choose('destination',b);
}
async function preview() {
  const before=await cdp.evaluate('window.__routeCalls.length');
  await keyboard('#route-submit');
  await cdp.wait(`window.__routeCalls.length===${before+1} && document.querySelector('#route-request-status').dataset.state==='success'`);
  return cdp.evaluate(`window.__routeCalls[${before}]`);
}
async function initialize() {
  result.browser={container:process.env.HOSTNAME,version:(await cdp.call('Browser.getVersion')).product};
  const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
  cdp.sessionId=(await cdp.call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await cdp.call('Page.enable');
  await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__routeCalls=[];window.__errors=[];window.__options=[];
    addEventListener('error',e=>window.__errors.push(e.message));
    addEventListener('unhandledrejection',e=>window.__errors.push(String(e.reason)));
    const actual=fetch.bind(window);
    window.fetch=async(url,init)=>{
      if(url===window.__slowScene){await new Promise(resolve=>window.__releaseScene=resolve);window.__slowScene=null;
        if(window.__failScene)return new Response('Injected scene failure',{status:503});}
      if(String(url).startsWith('/demo/v1/route-options?')&&window.__unknownOptions)return new Response('{}',{status:503});
      const response=await actual(url,init);
      if(String(url).startsWith('/demo/v1/route-options?')){
        const body=await response.clone().json();
        if(window.__availability){const item=body.destinations.find(d=>d.unit_id===window.__availability.id);item.availability=window.__availability.status;}
        window.__options.push(body);
        return new Response(JSON.stringify(body),{status:response.status,headers:{'Content-Type':'application/json'}});
      }
      if(url==='/demo/v1/route'&&init?.method==='POST'){
        const body=await response.clone().json();
        const originalStatus=body.guidance?.status;
        if(window.__unavailableGuidance&&body.status===200){Object.assign(body.guidance,{status:'unavailable',distance_m:null,
          warnings:['Injected unavailable guidance fixture; inspect route details.'],steps:[],visits:[],geometries:[],markers:[],transitions:[]});}
        window.__routeCalls.push({request:JSON.parse(init.body),httpStatus:response.status,originalStatus,body});
        return new Response(JSON.stringify(body),{status:response.status,headers:{'Content-Type':'application/json'}});
      }
      return response;
    };`});
}
async function run() {
  await initialize();
  for(const width of [1440,390]) {
    await prepareViewport(width);
    result.health ??= await cdp.evaluate("fetch('/demo/v1/health').then(r=>r.json())");
    const units=await cdp.evaluate("fetch('/demo/v1/units').then(r=>r.json()).then(b=>b.units)");
    const room=id=>{const matches=units.filter(u=>u.room_id===id);assert.equal(matches.length,1);return matches[0];};
    const a=room('SH1001C'), b=room('SH1003');
    await draft(a,b);
    const available=await preview();
    assert.equal(available.body.guidance.status,'available');
    assert.match(await field('#route-status','textContent'),/About \d+ m mapped route/);
    result.cases.push({width,name:'N10 available',request:available.request,status:available.httpStatus,edgeIds:available.body.edge_ids});
    await draft(room('AQ1003'),room('AQ5053.2'));
    const limited=await preview();
    assert.equal(limited.body.guidance.status,'limited');
    assert.equal(limited.body.guidance.distance_m,null);
    assert.match(await field('#route-status','textContent'),/geometry needs review/);
    assert.doesNotMatch(await field('#route-status','textContent'),/About \d+ m/);
    for(const step of limited.body.guidance.steps.filter(s=>s.kind==='walk')) assert.doesNotMatch(step.instruction,/\b\d+(?:\.\d+)?\s*m\b/);
    result.cases.push({width,name:'N10 real limited',request:limited.request,status:limited.httpStatus,edgeIds:limited.body.edge_ids,warnings:limited.body.guidance.warnings});
    await cdp.evaluate('window.__unavailableGuidance=true');
    await draft(a,b);await preview();
    assert.match(await field('#current-instruction','textContent'),/preview is unavailable/i);
    assert.equal(await field('#step-next','disabled'),true);
    assert.equal(await field('#step-previous','disabled'),true);
    assert.equal(await cdp.evaluate("document.querySelectorAll('#route-overlay path').length"),0);
    await screenshot(`${width}-unavailable.png`);
    await cdp.evaluate('window.__unavailableGuidance=false');
    await preview();
    assert.match(await field('#route-status','textContent'),/About \d+ m mapped route/);
    result.checks.push(`${width}: N10 real available/limited and synthetic unavailable guidance with successful Preview recovery`);
    // N11 real disconnected catalog; absent same-anchor/unavailable-endpoint cases are explicitly synthetic.
    const beforeAvailability=await cdp.evaluate('window.__routeCalls.length');
    await pointerClick('#route-clear');await choose('origin',a);
    await cdp.wait("document.querySelector('#route-options-status').dataset.state==='ready'");
    const options=await cdp.evaluate('window.__options.at(-1)');
    for(const [status,label] of [['disconnected','No mapped connection']]) {
      const item=options.destinations.find(d=>d.availability===status);assert.ok(item,`canonical ${status} fixture`);
      const selected=units.find(u=>u.unit_id===item.unit_id);
      if(!(await field('#route-destination-finder','open')))await pointerClick('#route-destination-finder > summary');
      await typeQuery('#route-destination-search',selected.room_id);
      const selector=`#route-destination-search-results option[value=${q(item.unit_id)}]`;
      assert.equal(await field(selector,'disabled'),true);assert.match(await field(selector,'textContent'),new RegExp(label));
      result.cases.push({width,name:`N11 real ${status}`,origin:a.unit_id,destination:item.unit_id});
    }
    for (const [status,label] of [["same_anchor","Same route point"],["endpoint_unavailable","No mapped route point"]]) {
    await cdp.evaluate(`window.__availability=${q({id:b.unit_id,status})}`);
    await pointerClick('#route-clear');await choose('origin',a);
    await cdp.wait("document.querySelector('#route-options-status').dataset.state==='ready'");
    await typeQuery('#route-destination-search',b.room_id);
    const same=`#route-destination-search-results option[value=${q(b.unit_id)}]`;
    assert.equal(await field(same,'disabled'),true);assert.match(await field(same,'textContent'),new RegExp(label));
    result.cases.push({width,name:'N11 synthetic '+status,origin:a.unit_id,destination:b.unit_id});
    }
    const count=await cdp.evaluate('window.__routeCalls.length');
    assert.equal(count,beforeAvailability,"Unavailable destination choices never post a walking route");
    assert.equal(await field('#route-destination-search-choose','disabled'),true);
    await cdp.evaluate('window.__availability=null;window.__unknownOptions=true');
    await draft(a,b);
    assert.match(await field('#route-destination-search-status','textContent'),/unknown/i);
    assert.equal(await cdp.evaluate('window.__routeCalls.length'),count);
    const fallback=await preview();assert.equal(fallback.httpStatus,200);
    await cdp.evaluate('window.__unknownOptions=false');
    result.checks.push(`${width}: N11 real disconnected, synthetic unavailable endpoint/same-anchor and unknown availability with real route validation`);
    // N12 extends existing navigation.cjs Retry coverage with delayed failure and keyboard retry at both widths.
    await pointerClick('#route-clear');
    await pointerClick('#show-campus');
    await pointerClick('#building-buttons [data-building-id="SFU_BURNABY_QUAD"]');
    const base='SFU_BURNABY_QUAD_1000',target='SFU_BURNABY_QUAD_2000';
    await pointerClick(`#floor-buttons [data-level-id="${base}"]`);
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${q(base)}&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
    const beforeMap=await field('#floor-map','innerHTML');
    await cdp.evaluate(`window.__slowScene=${q(`/demo/v1/levels/${target}/scene`)};window.__failScene=true`);
    await keyboard(`#floor-buttons [data-level-id="${target}"]`);
    await cdp.wait('!!window.__releaseScene');
    assert.equal(await field('#viewing-floor','dataset.levelId'),base);
    assert.equal(await field('#level-select','value'),target);
    assert.equal(await field('#floor-map','innerHTML'),beforeMap);
    await cdp.evaluate('window.__releaseScene()');
    await cdp.wait("document.querySelector('#retry-scene').hidden===false");
    assert.match(await field('#map-status','textContent'),/Could not load.*Still showing/);
    assert.equal(await field('#viewing-floor','dataset.levelId'),base);
    await keyboard('#retry-scene');
    await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${q(target)}&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
    assert.equal(await field('#retry-scene','hidden'),true);
    await screenshot(`${width}-retry-recovered.png`);
    assert.deepEqual(await cdp.evaluate('window.__errors'),[]);
    result.routeCalls.push(...await cdp.evaluate('window.__routeCalls.map(c=>({request:c.request,httpStatus:c.httpStatus,originalGuidance:c.originalStatus,deliveredGuidance:c.body.guidance?.status}))'));
    result.checks.push(`${width}: N12 slow failed floor retains exact prior map and requested identity; keyboard Retry loads real target scene`);
  }
  result.status='passed';
}
run().catch(async error=>{result.status='failed';result.error=error.stack;await screenshot('failure.png').catch(()=>{});process.exitCode=1;}).finally(()=>{
  result.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(outputDir,'results.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));proc.kill();
});
