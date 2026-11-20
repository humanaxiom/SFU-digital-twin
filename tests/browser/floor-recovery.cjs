"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createBrowserGate}=require('./room-search.cjs');
const {baseUrl,cdp,proc,result,outputDir,pointerClick,field,screenshot}=createBrowserGate('floor-recovery');
const q=JSON.stringify, aq='SFU_BURNABY_QUAD', from=aq+'_3000', target=aq+'_6000';
async function ready(level){await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${q(level)}&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);}
async function floor(level){await pointerClick(`#floor-buttons [data-level-id=${q(level)}]`);}
async function state(){return cdp.evaluate(`({roomShapeCount:document.querySelectorAll('.unit-shape').length,displayed:document.querySelector('#viewing-floor')?.dataset.levelId,selected:document.querySelector('#level-select')?.value,busy:document.querySelector('#floor-map')?.getAttribute('aria-busy'),retry:document.querySelector('#retry-scene')?.hidden===false,status:document.querySelector('#map-status')?.textContent,origin:document.querySelector('#route-origin')?.value,calls:window.__sceneCalls,errors:window.__errors})`);}
async function setup(suffix='/index.html'){
  await cdp.call('Page.navigate',{url:baseUrl.replace(/\/$/,'')+suffix});
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1");
  await pointerClick(`#building-buttons [data-building-id=${q(aq)}]`);
  await floor(from);await ready(from);
  const units=await cdp.evaluate("fetch('/demo/v1/units').then(r=>r.json()).then(b=>b.units)");
  const matches=units.filter(u=>u.level_id===from&&u.room_id==='AQ3024.1');assert.equal(matches.length,1);
  const room=matches[0];
  const began=Date.now();await pointerClick(`#room-list [data-unit-id=${q(room.unit_id)}]`);
  await cdp.wait(`document.querySelector('#route-origin').value===${q(room.unit_id)}`);
  result.origin=room.unit_id;result.originSelectionMs=Date.now()-began;
}
async function run(){
  result.browser={container:process.env.HOSTNAME,version:(await cdp.call('Browser.getVersion')).product};
  const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
  cdp.sessionId=(await cdp.call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await cdp.call('Page.enable');
  await cdp.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__sceneCalls=[];window.__errors=[];window.__routeCalls=[];
    addEventListener('error',e=>__errors.push(e.message));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));
    const actual=fetch.bind(window);window.fetch=async(url,init)=>{
      const isTarget=String(url)==='/demo/v1/levels/${target}/scene';
      if(isTarget)window.__sceneCalls.push({url:String(url),stage:window.__holdStage||'normal',started:performance.now()});
      const hold=isTarget?window.__holdStage:null;if(hold)window.__holdStage=null;
      if(String(url)==='/demo/v1/route'&&init?.method==='POST')window.__routeCalls.push(JSON.parse(init.body));
      const response=await actual(url,init);if(isTarget)window.__sceneCalls.at(-1).status=response.status;
      if(hold==='headers'){window.__heldHeaders=true;await new Promise(resolve=>window.__release=resolve);}
      if(hold==='body'){const text=response.text.bind(response);response.text=async()=>{const body=await text();window.__heldBody=true;await new Promise(resolve=>window.__release=resolve);return body;};}
      return response;
    };`});
  for(const suffix of ['/','/index.html']){
    await setup(suffix);const began=Date.now();await floor(target);await ready(target);
    assert.equal((await state()).roomShapeCount,263,'AQ6000 renders every recorded room shape');
    result.cases.push({name:'ordinary exact screenshot sequence',document:suffix,visibleFloorMs:Date.now()-began,state:await state()});
    console.log(JSON.stringify(result.cases.at(-1)));await screenshot(suffix==='/'?'ordinary-root.png':'ordinary-index.png');
  }
  if(process.env.WAYFINDING_BROWSER_RECOVERY_ORDINARY_ONLY==='1'){
    result.scope='Ordinary exact AQ floor sequence on / and /index.html; no fault injection';
    result.status='passed';return;
  }
  result.scope='Full ordinary sequence, body/fetch timeout recovery, late completion and default routing';
  for(const stage of ['body','headers']){
    await setup();
    await cdp.evaluate(`window.__holdStage=${q(stage)}`);
    const began=Date.now();await floor(target);
    await cdp.wait(stage==='body'?'window.__heldBody===true':'window.__heldHeaders===true');
    await floor(target);
    try{await cdp.wait("document.querySelector('#retry-scene').hidden===false&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'",12500);}
    finally{result.cases.push({name:`held ${stage} + same-floor reclick`,elapsedMs:Date.now()-began,state:await state()});}
    assert.equal((await state()).displayed,from);
    assert.match((await state()).status,/timed out|timeout|too long/i);
    assert.equal((await state()).calls[0].status,200,'the held response came from a healthy server');
    assert.equal((await state()).calls.length,1,'same-floor click deduplicates only the active request');
    assert.equal(await field('#route-origin','value'),result.origin);
    await screenshot(`${stage}-timeout.png`);
    await pointerClick('#retry-scene');await ready(target);
    assert.equal((await state()).calls.length,2,'Retry after timeout performs a fresh request');
    await cdp.evaluate(`window.__winningScene=loadedScenes.get(${q(target)})`);
    assert.equal(await cdp.evaluate('window.__winningScene.units.length'),263);
    await floor(from);await ready(from);
    await cdp.evaluate('window.__release()');
    await new Promise(resolve=>setTimeout(resolve,150));
    assert.equal((await state()).displayed,from,'late obsolete completion must preserve newer floor');
    assert.equal(await cdp.evaluate(`loadedScenes.get(${q(target)})===window.__winningScene`),true,'late obsolete completion cannot replace successful Retry cache');
    await floor(target);await ready(target);
    assert.equal((await state()).calls.length,2,'successful Retry remains cached');
    assert.deepEqual(await cdp.evaluate('window.__errors'),[]);
    result.checks.push(`${stage}: timeout exposes Retry; fresh retry preserves complete263rooms; late completion preserves newer floor and cache`);
    await screenshot(`${stage}-recovered.png`);
  }
  // A normal second room activation still submits directions after recovery.
  const units=await cdp.evaluate("fetch('/demo/v1/units').then(r=>r.json()).then(b=>b.units)");
  const options=await cdp.evaluate(`fetch('/demo/v1/route-options?origin_unit_id='+encodeURIComponent(${q(result.origin)})+'&profile=default').then(r=>r.json())`);
  const destination=units.find(u=>u.level_id===from&&u.unit_id!==result.origin&&options.destinations.some(d=>d.unit_id===u.unit_id&&d.availability==='connected'));
  assert.ok(destination,'connected same-floor AQ destination exists');
  await floor(from);await ready(from);
  await pointerClick(`#room-list [data-unit-id=${q(destination.unit_id)}]`);
  await cdp.wait("document.querySelector('#route-request-status').dataset.state==='success'");
  const calls=await cdp.evaluate('window.__routeCalls');
  assert.equal(calls.length,1);
  assert.equal(calls[0].origin.unit_id,result.origin);
  assert.equal(calls[0].destination.unit_id,destination.unit_id);
  result.checks.push('Default room A then connected B still automatically routes after scene recovery');
  result.status='passed';
}
run().catch(async e=>{result.status='failed';result.error=e.stack;result.failureState=await state().catch(()=>null);await screenshot('failure.png').catch(()=>{});process.exitCode=1;}).finally(()=>{result.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(outputDir,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));proc.kill();});
