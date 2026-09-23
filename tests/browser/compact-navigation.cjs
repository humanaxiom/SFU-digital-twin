"use strict";
// Actual pointer/keyboard tasks for compact navigation. Execute only in Docker.
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path");
const {spawn} = require("node:child_process");
assert.ok(fs.existsSync("/.dockerenv"), "Docker required");
const output = path.join("/workspace/build/navigation-review", process.env.WAYFINDING_BROWSER_RUN_LABEL || "compact");
fs.mkdirSync(output, {recursive:true});
const proc = spawn("/ms-playwright/chromium-1140/chrome-linux/chrome", ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--remote-debugging-pipe", "about:blank"], {stdio:["ignore","ignore","ignore","pipe","pipe"]});
let nextId=0, sessionId, buffer="";
const pending=new Map();
proc.stdio[4].setEncoding("utf8");
proc.stdio[4].on("data", chunk=>{
  buffer+=chunk;const messages=buffer.split("\0");buffer=messages.pop();
  for(const raw of messages){if(!raw)continue;const m=JSON.parse(raw),p=pending.get(m.id);if(!p)continue;pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}
});
function call(method,params={}){const id=++nextId;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout ${method}`));},15000);pending.set(id,{resolve,reject,timer});proc.stdio[3].write(JSON.stringify({id,method,params,sessionId})+"\0");});}
async function evaluate(expression){const r=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result?.value;}
async function wait(expression){const end=Date.now()+30000;while(Date.now()<end){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,50));}throw new Error(`Timed out: ${expression}`);}
const q=JSON.stringify;
async function click(selector,key){
  const point=await evaluate(`(()=>{const n=document.querySelector(${q(selector)});if(!n)throw new Error('Missing control '+${q(selector)});n.scrollIntoView({block:'center'});const r=n.getBoundingClientRect();if(!n.checkVisibility()||!r.width||!r.height)throw new Error('Hidden control');if(n.isPointInFill){const b=n.getBBox();for(let i=1;i<20;i++)for(let j=1;j<20;j++){const p=n.ownerSVGElement.createSVGPoint();p.x=b.x+b.width*i/20;p.y=b.y+b.height*j/20;if(n.isPointInFill(p)){const s=p.matrixTransform(n.getScreenCTM());if(document.elementFromPoint(s.x,s.y)===n)return {x:s.x,y:s.y};}}throw new Error('No painted click point');}return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  if(key){await evaluate(`document.querySelector(${q(selector)}).focus()`);assert.equal(await evaluate(`document.activeElement===document.querySelector(${q(selector)})`),true);await call("Input.dispatchKeyEvent",{type:"keyDown",key,code:key===" "?"Space":key,text:key===" "?" ":"\r",windowsVirtualKeyCode:key===" "?32:13});await call("Input.dispatchKeyEvent",{type:"keyUp",key,code:key===" "?"Space":key,windowsVirtualKeyCode:key===" "?32:13});}
  else{await call("Input.dispatchMouseEvent",{type:"mousePressed",...point,button:"left",clickCount:1});await call("Input.dispatchMouseEvent",{type:"mouseReleased",...point,button:"left",clickCount:1});}
}
async function ready(id){await wait(`!document.querySelector('#floor-view').hidden&&document.querySelector('#viewing-floor').dataset.levelId===${q(id)}&&document.querySelector('#floor-map').getAttribute('aria-busy')==='false'&&!document.querySelector('#map-status').textContent.includes('Loading')`);}
async function openBuilding(id){await click(`#building-buttons [data-building-id="${id}"]`);await ready(await evaluate("document.querySelector('#level-select').value"));assert.equal(await evaluate("document.querySelector('#facility-select').value"),id);}
async function input(text){await click("#room-filter");await evaluate("document.querySelector('#room-filter').select()");if(text)await call("Input.insertText",{text});else{await call("Input.dispatchKeyEvent",{type:"keyDown",key:"Backspace",code:"Backspace",windowsVirtualKeyCode:8});await call("Input.dispatchKeyEvent",{type:"keyUp",key:"Backspace",code:"Backspace",windowsVirtualKeyCode:8});}}
async function top(){await evaluate("window.scrollTo(0,0);new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))");}
async function screenshot(name){await top();const {data}=await call("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});fs.writeFileSync(path.join(output,`${name}.png`),Buffer.from(data,"base64"));}
const result={startedAt:new Date().toISOString(),status:"running",checks:[],floors:[],viewports:{}};
async function main(){
  const target=await call("Target.createTarget",{url:"about:blank"});sessionId=(await call("Target.attachToTarget",{targetId:target.targetId,flatten:true})).sessionId;
  await call("Page.enable");await call("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await call("Page.addScriptToEvaluateOnNewDocument",{source:"window.__errors=[];addEventListener('error',e=>__errors.push(String(e.message)));addEventListener('unhandledrejection',e=>__errors.push(String(e.reason)))"});
  await call("Page.navigate",{url:process.env.WAYFINDING_BROWSER_BASE_URL||"http://127.0.0.1:8080"});
  await wait("document.querySelectorAll('#building-buttons button').length===3&&document.querySelector('#route-origin').options.length>1");
  const campus=await evaluate("fetch('/demo/v1/campus').then(r=>r.json())");
  await screenshot("mobile-campus");
  // A footprint's bounding-box center can lie in its empty courtyard.
  const aq=campus.facilities[0];await click(`#campus-map [data-campus-facility-id="${aq.facility_id}"]`);
  const footprintFloor=await evaluate("document.querySelector('#level-select').value");await ready(footprintFloor);
  assert.ok(aq.levels.some(l=>l.level_id===footprintFloor));assert.ok(await evaluate("document.querySelectorAll('.unit-shape').length>0"));
  result.checks.push("painted building footprint opens room geometry");
  for(const facility of campus.facilities){
    await openBuilding(facility.facility_id);
    assert.deepEqual(await evaluate("[...document.querySelectorAll('#floor-buttons button')].map(n=>n.dataset.levelId)"),facility.levels.map(l=>l.level_id));
    for(const [index,level] of facility.levels.entries()){
      await click(`#floor-buttons [data-level-id="${level.level_id}"]`,index%2?"Enter":undefined);await ready(level.level_id);
      const scene=await evaluate(`fetch('/demo/v1/levels/${level.level_id}/scene').then(r=>r.json())`);
      const actual=await evaluate("[...document.querySelectorAll('#room-list [data-unit-id]')].map(n=>n.dataset.unitId)");
      assert.deepEqual(actual,scene.units.map(u=>u.unit_id));assert.ok(actual.length>0);
      assert.deepEqual(await evaluate("[...document.querySelectorAll('.unit-shape')].map(n=>n.dataset.unitId)"),actual);
      assert.equal(await evaluate("document.querySelector('#facility-select').value"),facility.facility_id);
      assert.equal(await evaluate("document.querySelector('#room-list').closest('details')===null&&document.querySelector('#room-filter').checkVisibility()"),true);
      result.floors.push({levelId:level.level_id,rooms:actual.length});
    }
  }
  assert.equal(result.floors.length,11);result.checks.push("all three primary buildings and eleven exact floors expose their API room identities; pointer and keyboard");
  const id=await evaluate("document.querySelector('#viewing-floor').dataset.levelId");const scene=await evaluate(`fetch('/demo/v1/levels/${id}/scene').then(r=>r.json())`);
  const endpoints=await evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value]");
  for(const query of [scene.units[0].room_id,scene.units[0].room_id.slice(0,2),"NO_SUCH_ROOM",""]){
    await input(query);
    const expected=scene.units.filter(u=>`${u.room_id||''} ${u.use_type||''}`.toLowerCase().includes(query.toLowerCase())).map(u=>u.unit_id);
    assert.deepEqual(await evaluate("[...document.querySelectorAll('#room-list [data-unit-id]')].map(n=>n.dataset.unitId)"),expected);
    if(!expected.length)assert.match(await evaluate("document.querySelector('#room-list').textContent"),/No rooms match/);
  }
  assert.deepEqual(await evaluate("[document.querySelector('#route-origin').value,document.querySelector('#route-destination').value]"),endpoints);
  await input("NO_SUCH_ROOM");const next=await evaluate(`[...document.querySelectorAll('#floor-buttons button')].find(n=>n.dataset.levelId!==${q(id)}).dataset.levelId`);
  await click(`#floor-buttons [data-level-id="${next}"]`);await ready(next);assert.equal(await evaluate("document.querySelector('#room-filter').value"),"");assert.ok(await evaluate("document.querySelectorAll('#room-list button').length>0"));
  result.checks.push("actual typing filters exact/partial/no-match/clear without editing endpoints; floor change resets filter");
  const room=await evaluate("document.querySelector('#room-list button').textContent");await click("#room-list button");await wait("document.querySelector('.facts').open");
  assert.ok((await evaluate("document.querySelector('#unit-details').textContent")).includes(room));result.checks.push("visible room button selects its record without opening a disclosure first");
  // Build and follow a real cross-floor route using only visible room/floor controls.
  await click("#route-clear");
  await openBuilding(aq.facility_id);
  await click('#floor-buttons [data-level-id="SFU_BURNABY_QUAD_2000"]');await ready("SFU_BURNABY_QUAD_2000");
  assert.ok(await evaluate("[...document.querySelectorAll('#route-origin option')].filter(n=>n.value).every(n=>n.value.startsWith('SFU_BURNABY_QUAD_2000_'))"));
  await click('#room-list [data-unit-id="SFU_BURNABY_QUAD_2000_2035.2"]');
  await wait("document.querySelector('#route-origin').value==='SFU_BURNABY_QUAD_2000_2035.2'&&document.querySelector('#route-options-status').dataset.state==='ready'");
  assert.equal(await evaluate("document.querySelector('#reachable-destinations')"),null);
  assert.ok(!(await evaluate("document.querySelector('#route-options-status').textContent")).includes('below'));
  const available=await evaluate("fetch('/demo/v1/route-options?origin_unit_id=SFU_BURNABY_QUAD_2000_2035.2&profile=default').then(r=>r.json())");
  await click('#floor-buttons [data-level-id="SFU_BURNABY_QUAD_5000"]');await ready("SFU_BURNABY_QUAD_5000");
  await click('#room-list [data-unit-id="SFU_BURNABY_QUAD_5000_5046"]');
  await wait("document.querySelector('#route-status').dataset.state==='success'&&document.querySelectorAll('#floor-journey button').length>1");
  const destinationOptions=await evaluate("[...document.querySelectorAll('#route-destination option')].filter(n=>n.value).map(n=>n.value)");
  assert.ok(destinationOptions.length < available.destinations.length);
  assert.ok(destinationOptions.every(value=>value==='SFU_BURNABY_QUAD_2000_2035.2'||available.destinations.some(item=>item.unit_id===value&&item.availability==='connected')));
  const targetVisit=await evaluate("document.querySelectorAll('#floor-journey button')[1].dataset.visitId");
  await click("#floor-journey button:nth-of-type(2)");
  await wait(`document.querySelector('#route-steps button[aria-current="step"]')?.dataset.stepId&&document.querySelector('#viewing-floor').dataset.levelId===activeRoute.guidance.visits.find(v=>v.visit_id===${q(targetVisit)}).level_id`);
  assert.equal(await evaluate(`activeRoute.guidance.steps.find(s=>s.step_id===document.querySelector('#route-steps button[aria-current="step"]').dataset.stepId).visit_id`),targetVisit);
  result.checks.push("visible room actions build a mapped cross-floor route; route-floor click synchronizes map and first instruction; one compact dropdown contains mapped destinations without a duplicate action list");
  await click("#route-clear");await evaluate("document.querySelector('.facts').open=false");
  await openBuilding(aq.facility_id);
  for(const [name,width,height] of [["mobile-390",390,844],["mobile-320",320,700],["desktop-1440",1440,1000]]){
    await call("Emulation.setDeviceMetricsOverride",{width,height,deviceScaleFactor:1,mobile:false});await top();
    const layout=await evaluate("(()=>{const map=document.querySelector('#floor-map').getBoundingClientRect(),frame=document.querySelector('#floor-map').parentElement.getBoundingClientRect(),rooms=document.querySelector('#room-list').getBoundingClientRect(),w=document.documentElement.clientWidth;return {mapTop:map.top,mapHeight:map.height,frameHeight:frame.height,roomsTop:rooms.top,overflow:document.documentElement.scrollWidth>w,touch:[...document.querySelectorAll('#building-buttons button,#floor-buttons button')].every(n=>n.getBoundingClientRect().height>=44),clipped:[...document.querySelectorAll('#building-buttons button,#floor-buttons button,#room-filter,#room-count,#navigation-options')].some(n=>n.getBoundingClientRect().right>w+1)}})()");
    assert.equal(layout.overflow,false);assert.equal(layout.clipped,false);assert.equal(layout.touch,true);assert.ok(layout.frameHeight>=220&&layout.mapHeight>=218);
    if(width<500){assert.ok(layout.mapTop>=0&&layout.mapTop<400,JSON.stringify(layout));assert.ok(layout.roomsTop<height,JSON.stringify(layout));}
    result.viewports[name]=layout;await screenshot(name);
  }
  assert.deepEqual(await evaluate("window.__errors"),[]);result.checks.push("390px/320px/desktop visible map and room choices, 44px navigation buttons, no clipping or browser errors");result.status="passed";
}
(async()=>{try{await main();}catch(error){result.status="failed";result.error=String(error.stack||error);await screenshot("failure").catch(()=>{});}finally{result.completedAt=new Date().toISOString();fs.writeFileSync(path.join(output,"compact-navigation-results.json"),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));proc.kill();if(result.status!=="passed")process.exitCode=1;}})();
