"use strict";
// Docker Chromium regression for the default two-room route workflow.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {verifyGuidance}=require('./guidance.cjs');
const {createBrowserGate, strand: candidateStrand, defaultRoute: candidateRoute} = require('./room-search.cjs');
const {baseUrl, outputDir, proc, cdp, result, pointerClick, key, field, pickNativeOption, screenshot} = createBrowserGate('two-room-click');
const accepted=process.env.WAYFINDING_BROWSER_FIXTURE==='accepted';
const strand=accepted?{...candidateStrand,origin:'SFU_BURNABY_STRAND_1000_1001C',destination:'SFU_BURNABY_STRAND_1000_1003',floor3000:candidateStrand.floor1000}:candidateStrand;
const defaultRoute={...candidateRoute,origin:{unit_id:strand.origin},destination:{unit_id:strand.destination}};
const identity=accepted?/SH1001C.*SH1003/:/SH1036.*SH3050\.1/;
const q=JSON.stringify;
async function keyboard(selector) {
  assert.ok(await cdp.evaluate(`(()=>{const n=document.querySelector(${q(selector)});n?.scrollIntoView({block:'center'});n?.focus();return n===document.activeElement&&!n.disabled})()`));
  await key('Enter');
}
async function floor(level) {
  await pointerClick(`#floor-buttons [data-level-id=${q(level)}]`);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${q(level)} && document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
}
async function room(id, level, list=false) {
  await floor(level);
  if(list) return keyboard(`#room-list [data-unit-id=${q(id)}]`);
  const selector=`.unit-shape[data-unit-id=${q(id)}]`;
  const point=await cdp.evaluate(`(()=>{const n=document.querySelector(${q(selector)});n.scrollIntoView({block:'center',inline:'center'});const r=n.getBoundingClientRect();for(let i=1;i<30;i++)for(let j=1;j<30;j++){const x=r.left+r.width*i/30,y=r.top+r.height*j/30;if(document.elementFromPoint(x,y)===n)return {x,y}}throw Error('No visible room pointer hit')})()`);
  for(const type of ['mousePressed','mouseReleased'])await cdp.call('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1});
}
async function snapshot() {return cdp.evaluate(`({origin:document.querySelector('#route-origin')?.value,destination:document.querySelector('#route-destination')?.value,route:document.querySelector('#route-status')?.dataset.state,identity:document.querySelector('#route-committed-identity')?.textContent,mapIdentity:document.querySelector('#map-route-identity')?.textContent,level:document.querySelector('#viewing-floor')?.dataset.levelId,requests:window.__routeCalls,admission:window.__admission,title:document.title,bodyExcerpt:document.body?.textContent?.slice(0,300)})`);}
async function fresh(width) {
  await cdp.call('Emulation.setDeviceMetricsOverride',{width,height:width>500?1000:844,deviceScaleFactor:1,mobile:width<500});
  await cdp.call('Page.navigate',{url:baseUrl});
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1 && document.querySelector('#building-buttons [data-building-id=\"SFU_BURNABY_STRAND\"]')");
  await pointerClick('#building-buttons [data-building-id="SFU_BURNABY_STRAND"]');
  if(!await field('#directions-panel','open'))await pointerClick('#directions-panel > summary');
}
async function pair(width,list) {
  await fresh(width);
  // Do not touch the mode control: these are the user's two default room clicks.
  await room(strand.origin,strand.floor1000,list);
  await room(strand.destination,strand.floor3000,list);
  await cdp.wait("window.__routeCalls.length===1 && window.__routeCalls[0].done && document.querySelector('#route-request-status').dataset.state==='success'",10000);
  const call=await cdp.evaluate('window.__routeCalls[0]');
  assert.deepEqual(call.request,defaultRoute);
  assert.equal(call.status,200);
  const api=await cdp.evaluate(`fetch('/demo/v1/route',{method:'POST',headers:{'Content-Type':'application/json'},body:${q(JSON.stringify(defaultRoute))},__apiFixture:true}).then(async r=>({status:r.status,body:await r.json()}))`);
  assert.equal(api.status,200);
  assert.ok(Number.isFinite(api.body.network_distance_m)&&api.body.network_distance_m>0);
  verifyGuidance(api.body);
  assert.deepEqual(call.body.edge_ids,api.body.edge_ids,'browser and direct API exact edge parity');
  assert.equal(call.body.network_distance_m,api.body.network_distance_m);
  result.apiFixtures ??=[];
  result.apiFixtures.push({width,request:defaultRoute,status:api.status,edgeIds:api.body.edge_ids,distance:api.body.network_distance_m,provenance:api.body.provenance});
  assert.match(await field('#route-committed-identity','textContent'),identity);
  assert.match(await field('#map-route-identity','textContent'),identity);
  assert.equal(await field('#room-click-mode','value'),'route');
  assert.ok(await field('#room-click-mode','checkVisibility()'));
  result.cases.push({width,input:list?'keyboard room list':'real SVG pointer',call,state:await snapshot()});
  await screenshot(`${width}-two-click-route.png`);
}
async function invariants() {
  console.log('Checking inspect and unsupported selections');
  // This starts with the 320px committed route from pair().
  const committed=await field('#route-committed-identity','textContent');
  const before=await cdp.evaluate('window.__routeCalls.length');
  await pickNativeOption('#room-click-mode','inspect');
  await room(strand.origin,strand.floor1000,true);
  assert.equal(await field('#route-origin','value'),strand.origin);
  assert.equal(await field('#route-destination','value'),strand.destination);
  assert.equal(await field('#route-committed-identity','textContent'),committed);
  assert.equal(await cdp.evaluate('window.__routeCalls.length'),before);
  result.checks.push('Explicit inspect preserves endpoints and committed route');
  await pickNativeOption('#room-click-mode','route');
  await room(strand.origin,strand.floor1000,true);
  assert.equal(await cdp.evaluate('window.__routeCalls.length'),before,'same A only inspects');
  const options=await cdp.evaluate('window.__options.at(-1)');
  const unsupported=options.destinations.find(d=>d.availability==='disconnected' && d.unit_id.startsWith('SFU_BURNABY_STRAND_'));
  assert.ok(unsupported,'real disconnected Strand room fixture');
  const units=await cdp.evaluate("fetch('/demo/v1/units').then(r=>r.json()).then(b=>b.units)");
  const unit=units.find(u=>u.unit_id===unsupported.unit_id);
  await room(unit.unit_id,unit.level_id,true);
  await cdp.wait(`document.querySelector('#room-directions-here').dataset.unitId===${q(unit.unit_id)}`);
  assert.equal(await cdp.evaluate('window.__routeCalls.length'),before);
  assert.equal(await field('#route-committed-identity','textContent'),committed);
  assert.match(await field('#room-route-status','textContent'),/no mapped connection|disconnected/i);
  result.cases.push({name:'unsupported B preserves prior route without POST',unit:unit.unit_id,state:await snapshot()});
  const alternate=options.destinations.find(d=>d.availability==='connected'&&d.unit_id!==strand.destination&&d.unit_id!==strand.origin&&d.unit_id.startsWith('SFU_BURNABY_STRAND_'));
  assert.ok(alternate,'distinct connected replacement room');
  const replacement=units.find(u=>u.unit_id===alternate.unit_id);
  await room(replacement.unit_id,replacement.level_id,true);
  await cdp.wait(`window.__routeCalls.length===${before+1}&&window.__routeCalls.at(-1).done&&document.querySelector('#route-committed-identity').dataset.destinationUnitId===${q(replacement.unit_id)}`);
  assert.equal(await field('#route-origin','value'),strand.origin);
  assert.equal(await cdp.evaluate('window.__routeCalls.at(-1).request.origin.unit_id'),strand.origin);
  result.checks.push('Further room click automatically replaces B while retaining original A');
}
async function delayed() {
  console.log('Checking delayed availability and Clear');
  await fresh(1440);
  await cdp.evaluate('window.__holdOptions=true');
  await room(strand.origin,strand.floor1000,true);
  await cdp.wait('!!window.__releaseOptions');
  await room(strand.destination,strand.floor3000,true);
  const later='SFU_BURNABY_STRAND_2000';
  await floor(later);
  await cdp.evaluate('window.__holdOptions=false;window.__releaseOptions()');
  await cdp.wait("window.__routeCalls.length===1 && window.__routeCalls[0].done && document.querySelector('#route-request-status').dataset.state==='success'");
  assert.equal(await field('#viewing-floor','dataset.levelId'),later,'late availability/route must preserve newer floor');
  assert.deepEqual(await cdp.evaluate('window.__routeCalls[0].request'),defaultRoute);
  result.checks.push('Delayed availability submits original two-click intent while preserving newer exploration floor');
  await fresh(1440);
  await cdp.evaluate('window.__holdOptions=true');
  await room(strand.origin,strand.floor1000,true);
  await cdp.wait('!!window.__releaseOptions');
  await room(strand.destination,strand.floor3000,true);
  await pointerClick('#route-clear');
  await cdp.evaluate('window.__holdOptions=false;window.__releaseOptions()');
  await new Promise(r=>setTimeout(r,400));
  assert.equal(await cdp.evaluate('window.__routeCalls.length'),0);
  assert.equal(await field('#route-origin','value'),'');
  assert.equal(await field('#route-destination','value'),'');
  result.checks.push('Clear during delayed availability cancels automatic route intent');
  await fresh(1440);
  await cdp.evaluate('window.__holdRoute=true');
  await room(strand.origin,strand.floor1000,true);
  await room(strand.destination,strand.floor3000,true);
  await cdp.wait('!!window.__releaseRoute');
  await pointerClick('#route-clear');
  await cdp.evaluate('window.__holdRoute=false;window.__releaseRoute()');
  await cdp.wait('window.__routeCalls[0].done');
  await new Promise(r=>setTimeout(r,100));
  assert.equal(await field('#route-origin','value'),'');
  assert.equal(await field('#route-destination','value'),'');
  assert.equal(await field('#route-committed-identity','textContent'),'No committed route.');
  result.checks.push('Clear during pending automatic route prevents late route resurrection');
  await cdp.evaluate('window.__holdOptions=true;window.__releaseOptions=null');
  await room(strand.origin,strand.floor1000,true);
  await cdp.wait('!!window.__releaseOptions');
  await room(strand.destination,strand.floor3000,true);
  await pickNativeOption('#room-click-mode','inspect');
  const beforeMode=await cdp.evaluate('window.__routeCalls.length');
  await cdp.evaluate('window.__holdOptions=false;window.__releaseOptions()');
  await new Promise(r=>setTimeout(r,400));
  assert.equal(await cdp.evaluate('window.__routeCalls.length'),beforeMode);
  assert.equal(await field('#route-committed-identity','textContent'),'No committed route.');
  result.checks.push('Switching to Inspect cancels a waiting automatic selection');
}
async function run(){
  result.browser={container:process.env.HOSTNAME,version:(await cdp.call('Browser.getVersion')).product};
  const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
  cdp.sessionId=(await cdp.call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await cdp.call('Page.enable');
  await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__routeCalls=[];window.__errors=[];window.__options=[];window.__admission=[];
    addEventListener('error',e=>__errors.push(e.message));
    addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));
    const actual=fetch.bind(window);window.fetch=async(url,init)=>{
      const route=String(url)==='/demo/v1/route'&&init?.method==='POST'&&!init.__apiFixture;
      const call=route?{request:JSON.parse(init.body),done:false}:null;if(call)__routeCalls.push(call);
      const response=await actual(url,init);if(response.status===429)window.__admission.push({url:String(url),status:429});
      if(String(url).startsWith('/demo/v1/route-options?')){window.__options.push(await response.clone().json());if(window.__holdOptions)await new Promise(r=>window.__releaseOptions=r);}
      if(call){if(window.__holdRoute)await new Promise(r=>window.__releaseRoute=r);call.status=response.status;const body=await response.clone().json();call.body={edge_ids:body.edge_ids,network_distance_m:body.network_distance_m,guidanceStatus:body.guidance?.status,visitLevels:body.guidance?.visits.map(v=>v.level_id)};call.done=true;}
      return response;
    };`});
  await pair(1440,false); console.log('1440 SVG two-click passed');
  if(process.env.WAYFINDING_BROWSER_PAIR_ONLY==='1'){result.scope='Single default desktop pointer pair and direct API parity';result.status='passed';return;}
  await pair(390,true); console.log('390 keyboard two-click passed');
  await pair(320,true); console.log('320 keyboard two-click passed');
  await invariants();
  await delayed();
  assert.deepEqual(await cdp.evaluate('window.__errors'),[]);
  result.status='passed';
}
run().catch(async error=>{result.status='failed';result.error=error.stack;result.failureState=await snapshot().catch(()=>null);await screenshot('failure.png').catch(()=>{});process.exitCode=1;}).finally(()=>{result.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(outputDir,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,error:result.error,checks:result.checks,cases:result.cases.map(c=>({width:c.width,input:c.input,name:c.name})),outputDir},null,2));proc.kill();});
