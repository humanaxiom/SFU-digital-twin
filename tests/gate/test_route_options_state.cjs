// Exercise actual client availability state, preserving independent route requests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Run through Docker.');
function client(nativeSelect=false) {
  const nodes = new Map();
  class Node {
    constructor(tag='div') {this.tagName=tag;this._value='';this.textContent='';this.dataset={};this.attributes={};this.handlers={};this.children=[];this.classList={toggle(){}};}
    get value(){return this._value;}
    set value(value){this._value=this.tagName==='select'&&!this.querySelectorAll('option').some(n=>n.value===value)?'':value;}
    addEventListener(name,fn){this.handlers[name]=fn;}
    setAttribute(name,value){this.attributes[name]=String(value);}
    removeAttribute(name){delete this.attributes[name];}
    replaceChildren(...children){this.children=children;this.value='';}
    append(...children){this.children.push(...children);}
    querySelectorAll(selector){return this.children.flatMap(n=>[...(n.tagName===selector?[n]:[]),...n.querySelectorAll(selector)]);}
    querySelector(selector){return this.querySelectorAll(selector)[0];}
  }
  const document={querySelector(selector){if(!nodes.has(selector))nodes.set(selector,new Node(nativeSelect&&['#route-origin','#route-destination'].includes(selector)?'select':'div'));return nodes.get(selector);},querySelectorAll:()=>[],createElement:tag=>new Node(tag),createElementNS:(_,tag)=>new Node(tag)};
  const context=vm.createContext({document,console,fetch:()=>new Promise(()=>{}),URLSearchParams});
  const run=code=>vm.runInContext(code,context);
  run(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js','utf8'));
  run(`routeUnits=['A','B','C','D','E'].map(unit_id=>({unit_id,room_id:'Room '+unit_id,level_id:'L'}));
    allLevels=[{level_id:'L',facility_id:'F',short_name:'1000',vertical_order:0}];facilitiesById=new Map([['F',{code:'AQ'}]]);
    renderRouteOverlay=()=>{};updateEndpointStates=()=>{};restoreRenderedFloor=()=>{};activeLevel=()=>null;
    Object.assign(routeDraft,{origin:'A',destination:'D'});
    routeOrigin.value='A';routeDestination.value='D';routeProfile.value='default';
    globalThis.gets=[];globalThis.posts=[];
    request=(path,options)=>new Promise((resolve,reject)=>{
      (options?.method==='POST'?posts:gets).push({path,payload:options?JSON.parse(options.body):null,resolve,reject});
    });`);
  if(nativeSelect)run("routeOrigin.replaceChildren(...routeUnits.map(u=>option(u.unit_id,u.room_id)));renderDestinationOptions();routeOrigin.value='A';routeDestination.value='D';");
  return {run,context,nodes};
}
function body(origin='A',profile='default'){
  const outcomes={A:'connected',B:'connected',C:'same_anchor',D:'disconnected',E:'endpoint_unavailable'};
  const destinations=Object.keys(outcomes).filter(unit_id=>unit_id!==origin)
    .map(unit_id=>({unit_id,availability:outcomes[unit_id]}));
  return {version:'route-options-v1',status:200,origin_unit_id:origin,profile,
    availability_basis:'directed_profile_graph',destinations,warnings:[]};
}
async function tick(){for(let i=0;i<8;i++)await Promise.resolve();}
const preview=c=>c.nodes.get('#route-form').handlers.submit({preventDefault(){}});
const rejectRoute=request=>request.reject({payload:{status:409,code:'disconnected'}});
(async()=>{
  const failures=[];async function check(name,fn){try{await fn();console.log('PASS '+name);}catch(error){failures.push(name+': '+error.stack);}}
  await check('mapped-only catalog preserves an explicit unsupported selection',async()=>{
    const c=client();const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-destination').value,'D');
    const groups=c.nodes.get('#route-destination').querySelectorAll('optgroup');
    assert.deepEqual(groups.map(n=>n.dataset.availability),['connected']);
    assert.match(c.nodes.get('#route-options-status').textContent,/1 mapped destination/);
    assert.equal(c.context.posts.length,0);
  });
  await check('new profile response wins over delayed default response',async()=>{
    const c=client();const older=c.run('refreshRouteOptions()');
    c.run("editRouteDraft({profile:'elevator_only'})");
    const result=body('A','elevator_only');result.destinations[0].availability='disconnected';
    c.context.gets[1].resolve(result);await tick();c.context.gets[0].resolve(body());await older;
    assert.match(c.nodes.get('#route-options-status').textContent,/0 mapped routes/);
    assert.equal(c.nodes.get('#route-profile').value,'elevator_only');
    assert.equal(c.nodes.get('#route-destination').value,'D');
  });
  await check('clear cancels stale availability without restoring a destination',async()=>{
    const c=client();const pending=c.run('refreshRouteOptions()');c.run('clearRoute()');c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-origin').value,'');assert.equal(c.nodes.get('#route-destination').value,'');
    assert.match(c.nodes.get('#route-options-status').textContent,/Choose a starting room/i);
  });
  await check('availability failure preserves manual route request and reports error beside map',async()=>{
    const c=client();const options=c.run('refreshRouteOptions()');const pending=preview(c);
    assert.equal(c.context.posts.length,0,'Preview waits for the pending availability check');
    assert.match(c.nodes.get('#current-instruction').textContent,/Finding/);
    assert.equal(c.nodes.get('.current-step').hidden,false);
    c.context.gets[0].reject(new Error('offline'));await options;await tick();
    assert.equal(c.nodes.get('#route-destination').value,'D');
    assert.match(c.nodes.get('#route-options-status').textContent,/choose any room/i);
    assert.equal(c.context.posts.length,1);assert.equal(c.context.posts[0].payload.destination.unit_id,'D');
    rejectRoute(c.context.posts[0]);await pending;
    assert.match(c.nodes.get('#current-instruction').textContent,/no mapped connection/i);
    assert.equal(c.nodes.get('.current-step').hidden,false);
    assert.equal(c.nodes.get('#step-next').disabled,true);
    c.run('updateGuidanceControls()');
    assert.match(c.nodes.get('#current-instruction').textContent,/no mapped connection/i,'map redraw must retain the failure');
  });
  await check('the explicit Start here action refreshes availability without choosing To',async()=>{
    const c=client();c.run("editRouteDraft({origin:'',destination:''});selectUnit=async id=>{navigationState.selectedUnitId=id;};");
    c.nodes.get('#room-click-mode').handlers.change({target:{value:'inspect'}});
    await c.run("activateRouteEndpoint('B')");
    assert.equal(c.context.gets.length,0,'inspection alone must not choose From');
    c.nodes.get('#room-start-here').handlers.click();
    assert.equal(c.context.gets.length,1);assert.match(c.context.gets[0].path,/origin_unit_id=B/);
    assert.equal(c.nodes.get('#route-destination').value,'');assert.equal(c.context.posts.length,0);
  });
  await check('destination action after a failed route preserves From and changes only the draft',async()=>{
    const c=client(true);
    const failed=preview(c);
    rejectRoute(c.context.posts[0]);await failed;
    const oldError=c.nodes.get('#route-request-status').textContent;
    assert.match(oldError,/Room D.*no mapped connection/i);
    await c.run("activateRouteDestination('B')");
    assert.equal(c.nodes.get('#route-origin').value,'A');
    assert.equal(c.nodes.get('#route-destination').value,'B');
    assert.equal(c.nodes.get('#route-request-status').textContent,oldError,'old failure remains identified with its submitted pair');
    assert.equal(c.context.posts.length,1);
    const routed=preview(c);
    assert.equal(c.context.posts[1].payload.origin.unit_id,'A');
    assert.equal(c.context.posts[1].payload.destination.unit_id,'B');
    rejectRoute(c.context.posts[1]);await routed;
  });
  await check('guidance floor changes do not queue new availability catalogs',async()=>{
    const c=client(true);
    c.run("availabilityCalls=0;catalogCalls=0;refreshRouteOptions=()=>{availabilityCalls+=1};renderRouteCatalog=()=>{catalogCalls+=1};navigationState.context='route';selectFloorControls(allLevels[0])");
    assert.equal(c.run('availabilityCalls'),0);
    assert.equal(c.run('catalogCalls'),0);
    c.run("navigationState.context='floor';selectFloorControls(allLevels[0])");
    assert.equal(c.run('availabilityCalls'),0,'floor controls do not change the draft availability key');
    assert.equal(c.run('catalogCalls'),1);
  });
  await check('known disconnected room remains inspectable but cannot become the map destination',async()=>{
    const c=client(true);c.run("editRouteDraft({destination:''})");
    c.nodes.get('#room-click-mode').handlers.change({target:{value:'inspect'}});
    const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    c.run("selectUnit=async id=>{navigationState.selectedUnitId=id; updateRoomActions(); return true;};");
    assert.equal(await c.run("activateRouteEndpoint('D')"),true);
    assert.equal(c.nodes.get('#room-directions-here').disabled,true);
    await c.run("activateRouteDestination('D')");
    assert.equal(c.nodes.get('#route-destination').value,'');
    assert.equal(c.context.posts.length,0);
    assert.match(c.nodes.get('#map-status').textContent,/no mapped connection/i);
  });
  await check('destination action waits for pending availability before rejecting a disconnected destination',async()=>{
    const c=client(true);c.run("editRouteDraft({destination:''})");
    const options=c.run('refreshRouteOptions()');
    const clicked=c.run("activateRouteDestination('D')");
    assert.equal(c.nodes.get('#route-destination').value,'');
    assert.equal(c.context.posts.length,0);
    c.context.gets[0].resolve(body());await options;
    await clicked;
    assert.equal(c.context.posts.length,0);
    assert.equal(c.nodes.get('#route-destination').value,'');
  });
  await check('destination action follows a superseding same-origin availability request',async()=>{
    const c=client(true);c.run("editRouteDraft({destination:''})");
    const first=c.run('refreshRouteOptions()');
    const clicked=c.run("activateRouteDestination('D')");
    const second=c.run('refreshRouteOptions()');
    const stale=body();stale.destinations.find(unit=>unit.unit_id==='D').availability='connected';
    c.context.gets[0].resolve(stale);await first;await tick();
    assert.equal(c.nodes.get('#route-destination').value,'');
    c.context.gets[1].resolve(body());await second;
    await clicked;
    assert.equal(c.context.posts.length,0);
    assert.equal(c.nodes.get('#route-destination').value,'');
  });
  await check('destination action after a completed route keeps From and retains the displayed destination',async()=>{
    const c=client(true);const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    c.run("activeRoute={destination:{unit_id:'D'}}; committedRouteSnapshot={origin:'A',destination:'D',profile:'default'}; setRouteState('success'); renderRouteIdentity();");
    await c.run("activateRouteDestination('B')");
    assert.equal(c.nodes.get('#route-origin').value,'A');
    assert.equal(c.nodes.get('#route-destination').value,'B');
    assert.equal(c.run('activeRoute.destination.unit_id'),'D');
    assert.match(c.nodes.get('#route-draft-status').textContent,/Route changes not applied/);
    assert.equal(c.context.posts.length,0);
    const routed=preview(c);await tick();
    assert.equal(c.context.posts[0].payload.origin.unit_id,'A');
    assert.equal(c.context.posts[0].payload.destination.unit_id,'B');
    assert.equal(c.nodes.get('#route-status').attributes['data-state'],'success');
    rejectRoute(c.context.posts[0]);await routed;
    assert.equal(c.nodes.get('#route-status').attributes['data-state'],'success');
    assert.equal(c.nodes.get('#route-request-status').dataset.state,'error');
  });
  await check('explicit draft edit and Preview do not wait for room metadata',async()=>{
    const c=client(true);
    c.nodes.get('#room-click-mode').handlers.change({target:{value:'inspect'}});
    const inspection=c.run("activateRouteEndpoint('B')");
    assert.match(c.context.gets[0].path,/\/units\/B$/);
    await c.nodes.get('#room-directions-here').handlers.click();
    assert.equal(c.context.posts.length,0);
    const routed=preview(c);
    assert.equal(c.context.posts.length,1);
    assert.equal(c.context.posts[0].payload.origin.unit_id,'A');
    assert.equal(c.context.posts[0].payload.destination.unit_id,'B');
    rejectRoute(c.context.posts[0]);await routed;
    c.context.gets[0].resolve({unit_id:'B',room_id:'Room B'});await inspection;
  });
  await check('a mapped destination routes only after select change and Preview',async()=>{
    const c=client(true);c.run("editRouteDraft({destination:''});routeUnits.find(u=>u.unit_id==='A').room_id='AQ6071';routeUnits.find(u=>u.unit_id==='B').room_id='AQ6067';allLevels[0].short_name='6000';");
    const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-destination').value,'');
    assert.equal(c.context.posts.length,0);
    c.run("routeDestination.value='B'");
    c.nodes.get('#route-destination').handlers.change();
    assert.equal(c.nodes.get('#route-destination').value,'B');
    assert.equal(c.context.posts.length,0);
    const route=preview(c);await tick();
    assert.deepEqual(JSON.parse(JSON.stringify(c.context.posts[0].payload)),{origin:{unit_id:'A'},destination:{unit_id:'B'},profile:'default'});
    rejectRoute(c.context.posts[0]);await route;
  });
  await check('large reachable sets remain in the mapped selector',async()=>{
    const c=client(true);
    c.run("routeUnits.push(...['F','G'].map(unit_id=>({unit_id,room_id:'Room '+unit_id,level_id:'L'})))");
    const response=body();response.destinations=['B','C','D','E','F','G'].map(unit_id=>({unit_id,availability:'connected'}));
    const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(response);await pending;
    assert.equal(c.nodes.get('#route-destination').querySelectorAll('option').filter(n=>n.dataset.availability==='connected').length,6);
  });
  await check('older service without guidance reports update needed beside map and form',async()=>{
    const c=client();c.run("renderRoute({status:200,profile:'default',origin:{unit_id:'A'},destination:{unit_id:'B'},steps:[],geometries:[]})");
    assert.match(c.nodes.get('#current-instruction').textContent,/demo needs an update/i);
    assert.equal(c.nodes.get('#route-status').textContent,c.nodes.get('#current-instruction').textContent);
    assert.equal(c.nodes.get('#route-status').attributes['data-state'],'error');
    assert.equal(c.nodes.get('.current-step').hidden,false);
    assert.equal(c.run('activeRoute'),null);
  });
  await check('a destination selected while availability loads is never replaced',async()=>{
    const c=client();const pending=c.run('refreshRouteOptions()');c.run("editRouteDraft({destination:'E'})");c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-destination').value,'E');
    assert.match(c.nodes.get('#route-options-status').textContent,/selected destination has no mapped route point/);
  });
  await check('assistant and swap refresh for exact current origin/profile while preserving route payload',async()=>{
    const c=client();c.run("assistantInput.value='wheelchair directions from A to B';");
    await c.nodes.get('#assistant-form').handlers.submit({preventDefault(){}});
    assert.match(c.context.gets[0].path,/origin_unit_id=A&profile=elevator_only/);
    assert.equal(c.context.posts.length,0);
    c.context.gets[0].resolve(body('A','elevator_only'));await tick();
    const chat=preview(c);await tick();
    assert.equal(c.context.posts[0].payload.destination.unit_id,'B');
    assert.equal(c.context.posts[0].payload.profile,'elevator_only');
    c.context.posts[0].reject({payload:{status:409,code:'no_elevator_only_route',profile:'elevator_only'}});await chat;
    c.nodes.get('#route-swap').handlers.click();
    assert.match(c.context.gets[1].path,/origin_unit_id=B&profile=elevator_only/);
    assert.equal(c.context.posts.length,1);
    c.context.gets[1].resolve(body('B','elevator_only'));await tick();
    const swapped=preview(c);await tick();
    assert.equal(c.context.posts[1].payload.origin.unit_id,'B');
    assert.equal(c.context.posts[1].payload.destination.unit_id,'A');
    assert.equal(c.context.posts[1].payload.profile,'elevator_only');
    c.context.posts[1].reject({payload:{status:409,code:'no_elevator_only_route',profile:'elevator_only'}});await swapped;
    assert.equal(c.nodes.get('#route-options-status').attributes['data-origin-unit-id'],'B');
    assert.equal(c.nodes.get('#route-destination').value,'A');
  });
  await check('same-room choice stays selected with a visible request correction',async()=>{
    const c=client();c.run("editRouteDraft({destination:'A'})");await preview(c);
    assert.equal(c.context.posts.length,0);
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.match(c.nodes.get('#current-instruction').textContent,/distinct/);
  });
  await check('native select swap retains previous origin after availability grouping',async()=>{
    const c=client(true);const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    c.run("editRouteDraft({destination:'B'})");
    c.nodes.get('#route-swap').handlers.click();
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.equal(c.context.posts.length,0);
    c.context.gets[1].resolve(body('B'));await tick();
    assert.equal(c.nodes.get('#route-destination').value,'A');
    const swapped=preview(c);await tick();
    assert.equal(c.context.posts.length,1);
    assert.equal(c.context.posts[0].payload.destination.unit_id,'A');
    rejectRoute(c.context.posts[0]);await swapped;
  });
  await check('native select assistant can choose previous origin as destination',async()=>{
    const c=client(true);const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    c.run("assistantInput.value='directions from B to A';");
    await c.nodes.get('#assistant-form').handlers.submit({preventDefault(){}});
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.equal(c.context.posts.length,0);
    c.context.gets[1].resolve(body('B'));await tick();
    const chat=preview(c);await tick();
    assert.equal(c.context.posts[0].payload.destination.unit_id,'A');
    rejectRoute(c.context.posts[0]);await chat;
  });
  await check('assistant retains endpoints outside the viewed floor in scoped selects',async()=>{
    const c=client(true);
    c.run("routeUnits.push({unit_id:'Z',room_id:'Room Z',level_id:'OTHER'});assistantInput.value='directions from Z to B';");
    await c.nodes.get('#assistant-form').handlers.submit({preventDefault(){}});
    assert.equal(c.nodes.get('#route-origin').value,'Z');
    assert.equal(c.nodes.get('#route-destination').value,'B');
    assert.equal(c.context.posts.length,0);
    c.context.gets[0].resolve(body('Z'));await tick();
    assert.equal(c.nodes.get('#route-origin').value,'Z');
    const chat=preview(c);await tick();
    assert.equal(c.context.posts[0].payload.origin.unit_id,'Z');
    assert.equal(c.context.posts[0].payload.destination.unit_id,'B');
    rejectRoute(c.context.posts[0]);await chat;
  });
  await check('unavailable guidance message survives floor redraw',async()=>{
    const c=client();c.run("renderRoute({status:200,profile:'default',origin:{unit_id:'A'},destination:{unit_id:'B'},guidance:{version:'dt018-guidance-v1',status:'unavailable',steps:[],geometries:[],visits:[],markers:[],transitions:[],distance_m:null,warnings:['Preview unavailable.']}})");
    const message=c.nodes.get('#current-instruction').textContent;c.run('updateGuidanceControls()');
    assert.equal(c.nodes.get('#current-instruction').textContent,message);
    assert.match(message,/preview is unavailable/);
    assert.equal(c.nodes.get('.current-step').hidden,false);
  });
  assert.deepEqual(failures,[]);
  console.log('Route options regressions passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
