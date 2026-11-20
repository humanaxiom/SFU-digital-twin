"use strict";
// Docker Chromium: retained client update checks never replace user navigation.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {createBrowserGate,strand,defaultRoute}=require('./room-search.cjs');
const {baseUrl,cdp,proc,result,outputDir,pointerClick,field,screenshot,pickNativeOption,key}=createBrowserGate('client-update');
const q=JSON.stringify;
async function fresh(width=1440){
  await cdp.call('Emulation.setDeviceMetricsOverride',{width,height:width<500?844:1000,deviceScaleFactor:1,mobile:width<500});
  await cdp.call('Page.navigate',{url:baseUrl});
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1");
  assert.equal(await field('#check-client-update','tagName'),'BUTTON','A retained document needs a manual check without reloading');
  await cdp.wait("document.querySelector('#client-update-status').dataset.state==='current'");
  await cdp.evaluate('window.__initialRevision=loadedClientRevision');
}
async function status(expected){await cdp.wait(`document.querySelector('#client-update-status').dataset.state===${q(expected)}`,7000);}
async function floor(level){
  await pointerClick(`#floor-buttons [data-level-id=${q(level)}]`);
  await cdp.wait(`document.querySelector('#viewing-floor').dataset.levelId===${q(level)}&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'`);
}
async function room(id,level){await floor(level);await pointerClick(`#room-list [data-unit-id=${q(id)}]`);}
async function snap(){return cdp.evaluate(`({document:window.__documentToken,url:location.href,origin:document.querySelector('#route-origin').value,destination:document.querySelector('#route-destination').value,profile:document.querySelector('#route-profile').value,committed:document.querySelector('#route-committed-identity').textContent,displayed:document.querySelector('#viewing-floor').dataset.levelId,requested:document.querySelector('#level-select').value,camera:document.querySelector('#floor-map').getAttribute('viewBox'),instruction:document.querySelector('#current-instruction').textContent,step:document.querySelector('#step-position').textContent,selectedRoomId:navigationState.selectedUnitId,selected:[...document.querySelectorAll('.unit-shape.selected')].map(n=>n.dataset.unitId),roomDetails:document.querySelector('#unit-details').textContent,routePaths:document.querySelector('#route-overlay')?.innerHTML,routeCalls:window.__routeCalls.slice(),loadedRevision:loadedClientRevision})`);}
async function check(mode){
  await cdp.evaluate(`window.__mode=${q(mode)};checkClientUpdate()`);
}
async function buildRoute(){
  await pointerClick(`#building-buttons [data-building-id=${q(strand.facility)}]`);
  await room(strand.origin,strand.floor1000);await room(strand.destination,strand.floor3000);
  await cdp.wait("document.querySelector('#route-request-status').dataset.state==='success'");
  assert.deepEqual(await cdp.evaluate('window.__routeCalls'),[defaultRoute]);
  await pickNativeOption('#room-click-mode','inspect');
  await room(strand.origin,strand.floor1000);
  await cdp.wait("document.querySelector('#unit-details').textContent.includes('SH1036')");
  await floor('SFU_BURNABY_STRAND_2000');
  const selected=await cdp.evaluate("document.querySelector('#room-list [data-unit-id]').dataset.unitId");
  await pointerClick("#room-list [data-unit-id="+q(selected)+"]");
  await cdp.wait("!document.querySelector('#unit-details').textContent.includes('Loading room details')");
  assert.equal(await cdp.evaluate('navigationState.selectedUnitId'),selected);
  await pointerClick('#zoom-in');
  await cdp.wait('window.__actualPending===0');
}
async function manual(){
  if(!await field('.limitations','open'))await pointerClick('.limitations > summary');
  await pointerClick('#check-client-update');
}
async function initialize(){
  result.browser={container:process.env.HOSTNAME,version:(await cdp.call('Browser.getVersion')).product};
  const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
  cdp.sessionId=(await cdp.call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  await cdp.call('Page.enable');
  await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.__documentToken=String(Math.random());window.__errors=[];window.__routeCalls=[];window.__clientCalls=[];window.__actualPending=0;
    addEventListener('error',e=>__errors.push(e.message));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)));
    const actual=fetch.bind(window);window.fetch=async(url,init)=>{
      const client=String(url)==='/demo/v1/client';
      if(String(url)==='/demo/v1/route'&&init?.method==='POST')window.__routeCalls.push(JSON.parse(init.body));
      const mode=client?window.__mode:null;
      const call=client?{mode:mode||'actual',started:performance.now()}:null;if(call)__clientCalls.push(call);
      if(mode==='network')throw new TypeError('Injected offline check');
      let response;window.__actualPending++;try{response=await actual(url,init);}finally{window.__actualPending--;}
      if(!client)return response;
      call.http=response.status;
      if(mode==='headers'){window.__held=true;await new Promise(resolve=>window.__release=resolve);}
      const original=response.json.bind(response);
      response.json=async()=>{
        const body=await original();call.actual=body;
        if(mode==='body'){window.__held=true;await new Promise(resolve=>window.__release=resolve);}
        if(mode==='malformed')return {protocol:1,script_sha256:'not-a-digest'};
        if(mode==='wrong-protocol')return {protocol:2,script_sha256:body.script_sha256};
        if(mode==='mismatch'){call.delivered={protocol:1,script_sha256:body.script_sha256==='b'.repeat(64)?'c'.repeat(64):'b'.repeat(64)};return call.delivered;}
        return body;
      };
      return response;
    };`});
}
async function run(){
  await initialize();await fresh();
  assert.equal(await field('#client-update-status',"getAttribute('role')"),'status');
  assert.match(await cdp.evaluate('loadedClientRevision'),/^[a-f0-9]{64}$/);
  assert.equal(await cdp.evaluate('window.__clientCalls.length'),1,'server loaded hook starts one initial check');
  const initial=await cdp.evaluate('loadedClientRevision');
  if(process.env.WAYFINDING_BROWSER_CLIENT_ORDINARY_ONLY!=='1')await cdp.evaluate("setLoadedClientRevision('f'.repeat(64))");
  assert.equal(await cdp.evaluate('loadedClientRevision'),initial,'loaded identity is one-shot');
  await buildRoute();const before=await snap();
  if(process.env.WAYFINDING_BROWSER_CLIENT_ORDINARY_ONLY==='1'){
    await manual();await cdp.wait('!clientUpdatePending');await status('current');
    assert.deepEqual(await snap(),before,'ordinary manual check preserves real route/navigation');
    result.routeCalls=before.routeCalls;result.retainedNavigation={before,after:await snap()};
    result.scope='Ordinary actual loaded/current identity and manual check with real default route; no fault injection';
    result.checks.push('Actual A/A initial and manual checks preserve the real default route and retained navigation');
    result.status='passed';return;
  }
  result.scope='Full retained-client update, failure, deadline, startup race and viewport contract';
  await check('mismatch');await status('changed');
  assert.deepEqual(await snap(),before,'different served script preserves complete retained navigation');
  assert.equal(await field('#client-update-notice','hidden'),false);
  for(const mode of ['network',null]){await check(mode);await status('changed');assert.deepEqual(await snap(),before);}
  result.routeCalls=before.routeCalls;
  result.retainedNavigation={before,after:await snap()};
  result.checks.push('A/A current; observed A/B change is sticky after offline check and server rollback, without route/document/navigation mutation');
  // Repeated visible-return events are throttled; explicit manual action remains available.
  const count=await cdp.evaluate('window.__clientCalls.length');
  await cdp.evaluate("document.dispatchEvent(new Event('visibilitychange'));document.dispatchEvent(new Event('visibilitychange'))");
  assert.equal(await cdp.evaluate('window.__clientCalls.length'),count);
  await cdp.evaluate('clientUpdateLastStarted=Date.now()-60001');
  await cdp.evaluate("document.dispatchEvent(new Event('visibilitychange'))");
  await cdp.wait(`window.__clientCalls.length===${count+1}&&!clientUpdatePending`);
  assert.deepEqual(await snap(),before);
  result.checks.push('Visible-return checks are throttled and preserve navigation');
  for(const width of [390,320]){
    await cdp.call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
    await cdp.evaluate("document.querySelector('#client-update-notice').scrollIntoView({block:'start'})");
    const visible=await cdp.evaluate("['#client-update-notice','#open-updated-app'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return {selector:s,left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,viewportWidth:innerWidth,viewportHeight:innerHeight}})");
    for(const rect of visible){
      assert.ok(rect.width>0&&rect.height>0&&rect.left>=-1&&rect.right<=rect.viewportWidth+1&&rect.top>=-1&&rect.bottom<=rect.viewportHeight+1,`${width}px ${rect.selector} is fully inside viewport`);
    }
    result.cases.push({name:'notice viewport',width,rectangles:visible});
    await screenshot(`${width}-update-notice.png`);
    if(!await field('.limitations','open'))await pointerClick('.limitations > summary');
    await cdp.evaluate("document.querySelector('#check-client-update').scrollIntoView({block:'center'})");
    const manualVisible=await cdp.evaluate("(()=>{const r=document.querySelector('#check-client-update').getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=-1&&r.right<=innerWidth+1&&r.top>=-1&&r.bottom<=innerHeight+1})()");
    assert.equal(manualVisible,true,`${width}px manual update control is fully inside viewport`);
    await screenshot(`${width}-update-control.png`);
  }
  assert.equal(await field('#open-updated-app',"getAttribute('href')"),'/index.html');
  assert.equal(await field('#open-updated-app','target'),'_blank');
  assert.match(await field('#open-updated-app','rel'),/\bnoopener\b/);
  const oldSession=cdp.sessionId,targets=(await cdp.call('Target.getTargets')).targetInfos.map(t=>t.targetId);
  const preOpen=await snap();
  await cdp.evaluate("document.querySelector('#open-updated-app').scrollIntoView({block:'center'});document.querySelector('#open-updated-app').focus()");
  await key('Enter');
  let opened;
  for(let i=0;i<40&&!opened;i++){
    opened=(await cdp.call('Target.getTargets')).targetInfos.find(t=>t.type==='page'&&!targets.includes(t.targetId)&&t.url.endsWith('/index.html'));
    if(!opened)await new Promise(r=>setTimeout(r,50));
  }
  assert.ok(opened,'explicit link opens a fresh page');
  cdp.sessionId=(await cdp.call('Target.attachToTarget',{targetId:opened.targetId,flatten:true})).sessionId;
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1");
  assert.equal(await cdp.evaluate('window.opener===null'),true);
  assert.equal(await field('#route-origin','value'),'');
  cdp.sessionId=oldSession;
  assert.deepEqual(await snap(),preOpen,'new tab leaves original route and selection untouched');
  await cdp.call('Target.closeTarget',{targetId:opened.targetId});
  result.checks.push('Explicit noopener link opens fresh app while preserving original document and route');
  for(const mode of ['malformed','wrong-protocol','network']){
    await fresh();const prior=await snap();await check(mode);await status('unknown');
    assert.match(await field('#client-update-status','textContent'),/unable|unknown|unverified/i);
    assert.equal(await field('#client-update-notice','hidden'),true);assert.deepEqual(await snap(),prior);
    result.cases.push({name:mode,state:await field('#client-update-status','dataset.state'),requests:await cdp.evaluate('window.__clientCalls')});
  }
  for(const mode of ['headers','body']){
    await fresh();const prior=await snap();const began=Date.now();
    await cdp.evaluate(`window.__mode=${q(mode)};window.__checkPromise=checkClientUpdate();undefined`);
    await cdp.wait('window.__held===true');
    const calls=await cdp.evaluate('window.__clientCalls.length');
    assert.equal(await cdp.evaluate('checkClientUpdate()===window.__checkPromise'),true,'manual checks join active promise');
    assert.equal(await cdp.evaluate('window.__clientCalls.length'),calls);
    await status('unknown');assert.deepEqual(await snap(),prior);
    result.cases.push({name:`held ${mode}`,elapsedMs:Date.now()-began,state:await field('#client-update-status','dataset.state')});
    await check('mismatch');await status('changed');
    await cdp.evaluate('window.__release()');await new Promise(r=>setTimeout(r,100));
    await status('changed');assert.deepEqual(await snap(),prior);
    assert.equal(await cdp.evaluate('window.__clientCalls.length'),calls+1);
    assert.deepEqual(await cdp.evaluate('window.__errors'),[]);
  }
  result.checks.push('Malformed/offline results stay unknown; headers and body deadlines release singleflight; late old results cannot replace newer observed change');
  // Exercise actual manual button after the last timed-out response has settled.
  await cdp.evaluate('window.__mode=null');await manual();await cdp.wait('!clientUpdatePending');await status('changed');
  // Simulate a deployment appearing at the very first identity check, before
  // that endpoint has ever supplied a matching revision to this document.
  const startupScript=await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:"window.__mode='mismatch';"});
  await cdp.call('Page.navigate',{url:baseUrl});
  await cdp.wait("document.querySelector('#route-origin')?.options.length>1");
  await status('changed');
  const startup=await cdp.evaluate('({loaded:loadedClientRevision,calls:window.__clientCalls,routes:window.__routeCalls})');
  assert.equal(startup.calls.length,1);
  assert.equal(startup.loaded,startup.calls[0].actual.script_sha256,'loaded raw script stamp is authoritative before any matching endpoint response');
  assert.notEqual(startup.loaded,startup.calls[0].delivered.script_sha256,'first endpoint revision cannot become loaded baseline');
  assert.deepEqual(startup.routes,[]);
  assert.equal(await field('#client-update-notice','hidden'),false);
  result.cases.push({name:'first-check startup mismatch',...startup});
  await cdp.call('Page.removeScriptToEvaluateOnNewDocument',{identifier:startupScript.identifier});
  result.status='passed';
}
run().catch(async e=>{result.status='failed';result.error=e.stack;result.failureState=await cdp.evaluate("({status:document.querySelector('#client-update-status')?.textContent,state:document.querySelector('#client-update-status')?.dataset.state,calls:window.__clientCalls,errors:window.__errors})").catch(()=>null);await screenshot('failure.png').catch(()=>{});process.exitCode=1;}).finally(()=>{result.finishedAt=new Date().toISOString();fs.writeFileSync(path.join(outputDir,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));proc.kill();});
