"use strict";

// Candidate-specific browser/API evidence. Node built-ins; Docker Chromium only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const {verifyGuidance, activateButton, assertSelected, exerciseGuidance, sceneOrigin} = require('./guidance.cjs');
const {exerciseCampus} = require('./campus.cjs');
assert.ok(fs.existsSync('/.dockerenv'), 'Run the candidate browser gate in Docker.');
const label = process.env.WAYFINDING_BROWSER_RUN_LABEL || 'dt022-candidate';
assert.match(label, /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/);
const outputDir = path.join('/workspace/build/takeover-browser', label);
const reportPath = process.env.WAYFINDING_CANDIDATE_REPORT || '/workspace/build/experiments/evaluations/dt022.json';
const target = new URL(process.env.WAYFINDING_BROWSER_BASE_URL || 'http://demo:8080');
assert.ok(target.protocol === 'http:' && ['demo','localhost','127.0.0.1'].includes(target.hostname)
  && !target.username && !target.password && target.pathname === '/' && !target.search && !target.hash,
  'Target must be a local demo origin.');
const quote = JSON.stringify;
const requests = "window.__requests.filter(r=>r.url==='/demo/v1/route')";
const results = {status:'running',startedAt:new Date().toISOString(),node:process.version,
  baseUrl:target.origin,reportPath,viewports:{},availability:[]};
fs.mkdirSync(outputDir,{recursive:true});
const save = () => fs.writeFileSync(path.join(outputDir,'results.json'),JSON.stringify(results,null,2));
save();

class Cdp {
  constructor(proc) {
    this.proc=proc;this.nextId=1;this.pending=new Map();let buffer='';
    const fail=error=>{for(const p of this.pending.values())p.reject(error);this.pending.clear();};
    proc.on('error',fail);proc.on('exit',code=>fail(new Error(`Chromium exited: ${code}`)));
    proc.stdio[3].on('error',fail);proc.stdio[4].setEncoding('utf8');
    proc.stdio[4].on('data',chunk=>{
      buffer+=chunk;const messages=buffer.split('\0');buffer=messages.pop();
      for(const raw of messages){
        if(!raw)continue;const message=JSON.parse(raw),pending=this.pending.get(message.id);
        if(!pending)continue;this.pending.delete(message.id);
        if(message.error)pending.reject(new Error(JSON.stringify(message.error)));else pending.resolve(message.result);
      }
    });
  }
  call(method,params={},sessionId=this.sessionId) {
    const id=this.nextId++;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},15000);
      this.pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
      this.proc.stdio[3].write(JSON.stringify({id,method,params,sessionId})+'\0');
    });
  }
  async evaluate(expression) {
    const response=await this.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});
    if(response.exceptionDetails)throw new Error(response.exceptionDetails.exception?.description||response.exceptionDetails.text);
    return response.result?.value;
  }
  async wait(expression) {
    const end=Date.now()+30000;
    while(Date.now()<end){if(await this.evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,50));}
    throw new Error(`Timed out: ${expression}`);
  }
}

async function screenshot(cdp,name,mobile=false) {
  const captures={};
  for(const [panel,selector] of Object.entries(mobile?{map:null,current:'.current-step',controls:'#route-form'}:{map:null})){
    await cdp.evaluate(`(async()=>{
      const selector=${quote(selector)};
      if(selector)document.querySelector(selector).scrollIntoView({block:'start'});else window.scrollTo(0,0);
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    })()`);
    const {data}=await cdp.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    const file=`${name}-${panel}.png`;fs.writeFileSync(path.join(outputDir,file),Buffer.from(data,'base64'));captures[panel]=file;
  }
  return captures;
}

function compareRoute(actual,expected) {
  assert.equal(actual.status,expected.status,'candidate route status differs from its recorded fixture');
  for(const key of ['code','profile','origin','destination','network_distance_m','edge_ids','edges','geometries','guidance','provenance','warnings']){
    if(Object.hasOwn(expected,key))assert.deepEqual(actual[key],expected[key],`candidate ${key} differs from recorded fixture`);
  }
  if(actual.status===200)verifyGuidance(actual);
}

async function completedRoute(cdp,before,fixture) {
  const state=fixture.response.status===200?'success':'error';
  await cdp.wait(`${requests}[${before}]?.done&&document.querySelector('#route-status').dataset.state===${quote(state)}`);
  const sent=await cdp.evaluate(`${requests}.slice(${before})`);
  assert.equal(sent.length,1,'a single explicit action must send exactly one route request');
  assert.deepEqual(sent[0].body,{origin:{unit_id:fixture.origin.unit_id},destination:{unit_id:fixture.destination.unit_id},profile:fixture.profile});
  compareRoute(sent[0].response,fixture.response);
  const body=sent[0].response;
  if(body.status===200&&body.guidance.steps.length){
    const first=body.guidance.steps[0];
    if(first.level_id)await assertSelected(cdp,body,first);
    const levelId=await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId");
    const origin=await sceneOrigin(cdp);
    const expected=body.guidance.geometries.filter(g=>g.level_id===levelId).map(g=>({id:g.geometry_id,
      d:g.geometry.coordinates.map(([x,y],i)=>`${i?'L':'M'}${x-origin[0]} ${origin[1]-y}`).join(' ')}));
    assert.deepEqual(await cdp.evaluate("[...document.querySelectorAll('#route-overlay .route-segment')].map(p=>({id:p.dataset.geometryId,d:p.getAttribute('d')}))"),expected);
  } else if(body.status!==200){
    assert.equal(await cdp.evaluate("document.querySelectorAll('#route-overlay path').length"),0);
    assert.equal(await cdp.evaluate("document.querySelector('#current-instruction').textContent"),
      await cdp.evaluate("document.querySelector('#route-status').textContent"));
  }
  return body;
}

async function submit(cdp,fixture) {
  const before=await cdp.evaluate(`${requests}.length`);
  await cdp.evaluate(`document.querySelector('#route-origin').value=${quote(fixture.origin.unit_id)};
    document.querySelector('#route-destination').value=${quote(fixture.destination.unit_id)};
    document.querySelector('#route-profile').value=${quote(fixture.profile)};
    document.querySelector('#route-form').requestSubmit();`);
  return completedRoute(cdp,before,fixture);
}

async function routeFit(cdp,body) {
  const levelId=await cdp.evaluate("document.querySelector('#viewing-floor').dataset.levelId");
  const points=body.guidance.geometries.filter(g=>g.level_id===levelId).flatMap(g=>g.geometry.coordinates)
    .concat(body.guidance.markers.filter(m=>m.level_id===levelId).map(m=>m.coordinates));
  if(!points.length)return {status:'no geometry on displayed floor'};
  async function contained(){
    assert.ok(await cdp.evaluate(`(()=>{
      const svg=document.querySelector('#floor-map'),r=svg.getBoundingClientRect(),m=svg.getScreenCTM();
      const ox=Number(svg.dataset.originX),oy=Number(svg.dataset.originY);
      return ${quote(points)}.every(([x,y])=>{const p=new DOMPoint(x-ox,oy-y).matrixTransform(m);
        return p.x>=r.left+1&&p.x<=r.right-1&&p.y>=r.top+1&&p.y<=r.bottom-1;})
        &&[...svg.querySelectorAll('.route-marker circle')].every(n=>{const b=n.getBoundingClientRect();
          return b.left>=r.left+2&&b.right<=r.right-2&&b.top>=r.top+2&&b.bottom<=r.bottom-2;});
    })()`),'route and marker extents must fit the rendered viewport');
  }
  const box=()=>cdp.evaluate("document.querySelector('#floor-map').getAttribute('viewBox').split(' ').map(Number)");
  await contained();const initial=await box();
  await activateButton(cdp,'#zoom-out','Enter');const expanded=await box();
  assert.ok(expanded[2]>initial[2]&&expanded[3]>initial[3]);
  await activateButton(cdp,'#zoom-in',' ');
  (await box()).forEach((v,i)=>assert.ok(Math.abs(v-initial[i])<1e-6));
  await activateButton(cdp,'#fit-route');await contained();
  (await box()).forEach((v,i)=>assert.ok(Math.abs(v-initial[i])<1e-6));
  return {initial,expanded,levelId};
}

async function waitOptions(cdp,origin,profile,allowError=false) {
  await cdp.wait(`(()=>{const n=document.querySelector('#route-options-status');return ${allowError?"['ready','error'].includes(n.dataset.state)":"n.dataset.state==='ready'"}
    &&n.dataset.originUnitId===${quote(origin)}&&n.dataset.profile===${quote(profile)};})()`);
  const optionsPath=`/demo/v1/route-options?origin_unit_id=${encodeURIComponent(origin)}&profile=${encodeURIComponent(profile)}`;
  const body=await cdp.evaluate(`__requests.filter(r=>r.done&&r.url===${quote(optionsPath)}).at(-1).response`);
  if(body.status!==200){
    assert.ok(allowError,'expected availability must be usable');
    return body;
  }
  const connected=body.destinations.filter(d=>d.availability==='connected').map(d=>d.unit_id).sort();
  const options=await cdp.evaluate("[...document.querySelectorAll('#route-destination option[data-availability=connected]')].map(n=>n.value).sort()");
  assert.deepEqual(options,connected,'visible catalog choices differ from candidate reachability');
  return body;
}

async function availability(cdp,items,fixtures) {
  for(const item of items){
    await activateButton(cdp,'#route-clear');
    const before=await cdp.evaluate(`${requests}.length`);
    await cdp.evaluate(`document.querySelector('#route-profile').value=${quote(item.profile)};
      document.querySelector('#route-origin').value=${quote(item.origin_unit_id)};
      document.querySelector('#route-origin').dispatchEvent(new Event('change'));`);
    const body=await waitOptions(cdp,item.origin_unit_id,item.profile);
    assert.equal(await cdp.evaluate(`${requests}.length`),before,'origin selection must not automatically route');
    assert.equal(await cdp.evaluate("document.querySelector('#route-destination').value"),'');
    for(const key of ['version','status','origin_unit_id','profile','availability_basis','counts','destinations','provenance','warnings']){
      if(Object.hasOwn(item.response,key))assert.deepEqual(body[key],item.response[key],`candidate availability ${key} differs`);
    }
    const gained=item.gained===true||fixtures.some(f=>f.gained&&f.origin.unit_id===item.origin_unit_id&&f.profile===item.profile);
    if(gained){assert.ok(Number.isInteger(item.baseline_connected_count));assert.ok(body.counts.connected>item.baseline_connected_count,'flagged reachability gain was not demonstrated');}
    results.availability.push({origin:item.origin_unit_id,profile:item.profile,baselineConnected:item.baseline_connected_count,
      connected:body.counts.connected,gained});
  }
}

async function run() {
  const reportBytes=fs.readFileSync(reportPath),report=JSON.parse(reportBytes);
  results.reportSha256=crypto.createHash('sha256').update(reportBytes).digest('hex');
  assert.ok(Array.isArray(report.fixtures)&&report.fixtures.length>0,'recorded route fixtures required');
  assert.ok(Array.isArray(report.availability)&&report.availability.length>0,'recorded reachability responses required');
  for(const fixture of report.fixtures){
    assert.match(fixture.name,/^[A-Za-z0-9_-]+$/);assert.ok([200,400,404,409,422,503].includes(fixture.response.status));
    if(fixture.gained){assert.equal(fixture.baseline_status,409);assert.equal(fixture.response.status,200);}
  }
  const proc=spawn('/ms-playwright/chromium-1140/chrome-linux/chrome',
    ['--headless','--no-sandbox','--disable-dev-shm-usage','--remote-debugging-pipe','about:blank'],{stdio:['ignore','ignore','ignore','pipe','pipe']});
  const cdp=new Cdp(proc);
  try {
    results.browser=await cdp.call('Browser.getVersion');
    const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await cdp.call('Target.attachToTarget',{targetId,flatten:true});cdp.sessionId=sessionId;
    await cdp.call('Page.enable');
    await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{
      window.__requests=[];window.__errors=[];
      addEventListener('error',e=>__errors.push(String(e.error||e.message)));
      addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));
      const original=window.fetch;window.fetch=async(url,options)=>{
        const entry={url:String(url),method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null};__requests.push(entry);
        const response=await original(url,options);entry.response=await response.clone().json();entry.done=true;return response;
      };
    })()`});
    await cdp.call('Page.navigate',{url:target.origin+'/'});
    await cdp.wait("document.querySelector('#campus-view') && !document.querySelector('#campus-view').hidden && document.querySelectorAll('#route-origin option').length>1");
    for(const [width,height] of [[1440,1000],[390,844]]){
      const viewportLabel=`${width}x${height}`,viewport=results.viewports[viewportLabel]={fixtures:{}};
      await cdp.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<600});
      viewport.campus=await exerciseCampus(cdp,screenshot,viewportLabel,width);
      await availability(cdp,report.availability,report.fixtures);
      for(const fixture of report.fixtures){
        const body=await submit(cdp,fixture),record=viewport.fixtures[fixture.name]={status:body.status,
          distanceM:body.network_distance_m,edgeIds:body.edge_ids,provenance:body.provenance};
        if(body.status===200&&body.guidance.steps.length){
          record.camera=await routeFit(cdp,body);
          record.initialScreenshot=await screenshot(cdp,`${viewportLabel}-${fixture.name}-initial`,width<600);
          await exerciseGuidance(cdp,body,record);
          const event=body.guidance.transitions[0];
          if(event){
            record.transitionScreenshots={};
            for(const phase of ['departure','arrival']){
              const step=body.guidance.steps.find(s=>s.transition_id===event.transition_id&&s.phase===phase);
              await activateButton(cdp,`button[data-step-id="${step.step_id}"]`);await assertSelected(cdp,body,step);
              record.transitionScreenshots[phase]=await screenshot(cdp,`${viewportLabel}-${fixture.name}-${phase}`,width<600);
            }
          }
          const walk=body.guidance.steps.find(s=>s.kind==='walk');
          if(walk){await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);await assertSelected(cdp,body,walk);}
        }
        const choices=await waitOptions(cdp,fixture.origin.unit_id,fixture.profile,true);
        const connected=(choices.destinations||[]).filter(d=>d.availability==='connected');
        if(connected.some(d=>d.unit_id===fixture.destination.unit_id)){
          const before=await cdp.evaluate(`${requests}.length`);
          await cdp.evaluate(`document.querySelector('#route-destination').value=${quote(fixture.destination.unit_id)};document.querySelector('#route-destination').dispatchEvent(new Event('change',{bubbles:true}));`);
          await completedRoute(cdp,before,fixture);record.mappedChoiceSelected=true;
          const walk=body.guidance?.steps.find(s=>s.kind==='walk');
          if(walk){await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);await assertSelected(cdp,body,walk);}
        }
        record.screenshot=await screenshot(cdp,`${viewportLabel}-${fixture.name}-selected`,width<600);
        assert.ok(await cdp.evaluate(`document.documentElement.scrollWidth<=${width}`),'layout overflows viewport');save();
      }
    }
    const narrow=report.fixtures.find(f=>f.response.status===200&&f.response.guidance?.steps.some(s=>s.kind==='walk'));
    assert.ok(narrow,'candidate evidence must include at least one displayed walking route');
    await cdp.call('Emulation.setDeviceMetricsOverride',{width:320,height:844,deviceScaleFactor:1,mobile:true});
    results.narrowCampus=await exerciseCampus(cdp,screenshot,'320x844',320);
    const body=await submit(cdp,narrow);await routeFit(cdp,body);
    const walk=body.guidance.steps.find(s=>s.kind==='walk');await activateButton(cdp,`button[data-step-id="${walk.step_id}"]`);await assertSelected(cdp,body,walk);
    assert.ok(await cdp.evaluate('document.documentElement.scrollWidth<=320'),'320px layout overflows');
    results.narrowScreenshot=await screenshot(cdp,'320x844-selected',true);
    assert.deepEqual(await cdp.evaluate('window.__errors'),[]);
    results.requestCounts=await cdp.evaluate("({read:__requests.filter(r=>r.method==='GET').length,post:__requests.filter(r=>r.method==='POST').length})");
    results.status='passed';
  } catch(error){
    results.diagnostic=await cdp.evaluate("({status:document.querySelector('#route-status')?.textContent,map:document.querySelector('#map-status')?.textContent,errors:window.__errors})").catch(()=>null);
    results.errorScreenshot=await screenshot(cdp,'failure').catch(()=>null);throw error;
  } finally {proc.kill('SIGTERM');}
}
run().catch(error=>{results.status='failed';results.error=error.stack;console.error(error.stack);process.exitCode=1;})
  .finally(()=>{results.finishedAt=new Date().toISOString();save();});
