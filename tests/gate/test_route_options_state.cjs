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
    routeOrigin.value='A';routeDestination.value='D';routeProfile.value='default';
    globalThis.gets=[];globalThis.posts=[];
    request=(path,options)=>new Promise((resolve,reject)=>{
      (options?.method==='POST'?posts:gets).push({path,payload:options?JSON.parse(options.body):null,resolve,reject});
    });`);
  if(nativeSelect)run("routeOrigin.replaceChildren(...routeUnits.map(u=>option(u.unit_id,u.room_id)));renderDestinationOptions();routeOrigin.value='A';routeDestination.value='D';");
  return {run,context,nodes};
}
function body(origin='A',profile='default'){
  return {version:'route-options-v1',status:200,origin_unit_id:origin,profile,availability_basis:'directed_profile_graph',destinations:[{unit_id:'B',availability:'connected'},{unit_id:'C',availability:'same_anchor'},{unit_id:'D',availability:'disconnected'},{unit_id:'E',availability:'endpoint_unavailable'}],counts:{connected:1,same_anchor:1,disconnected:1,endpoint_unavailable:1},warnings:[]};
}
(async()=>{
  const failures=[];async function check(name,fn){try{await fn();console.log('PASS '+name);}catch(error){failures.push(name+': '+error.stack);}}
  await check('availability groups preserve unsupported selection and separate same anchor',async()=>{
    const c=client();const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-destination').value,'D');
    const groups=c.nodes.get('#route-destination').querySelectorAll('optgroup');
    assert.deepEqual(groups.map(n=>n.dataset.availability),['connected','same_anchor','disconnected','endpoint_unavailable']);
    assert.match(groups[1].label,/no walking path/i);
    assert.match(c.nodes.get('#route-options-status').textContent,/1 mapped route/);
    assert.equal(c.context.posts.length,0);
  });
  await check('new profile response wins over delayed default response',async()=>{
    const c=client();const older=c.run('refreshRouteOptions()');c.run("routeProfile.value='elevator_only'");const newer=c.run('refreshRouteOptions()');
    const result=body('A','elevator_only');result.destinations[0].availability='disconnected';result.counts.connected=0;result.counts.disconnected=2;
    c.context.gets[1].resolve(result);await newer;c.context.gets[0].resolve(body());await older;
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
    const c=client();const pending=c.run('submitSelectedRoute()');
    assert.equal(c.context.posts.length,1);assert.equal(c.context.posts[0].payload.destination.unit_id,'D');
    assert.match(c.nodes.get('#current-instruction').textContent,/Finding/);
    c.context.gets[0].reject(new Error('offline'));await Promise.resolve();await Promise.resolve();
    assert.equal(c.nodes.get('#route-destination').value,'D');
    assert.match(c.nodes.get('#route-options-status').textContent,/choose any room/i);
    c.context.posts[0].reject({payload:{status:409,code:'disconnected',profile:'default'}});await pending;
    assert.match(c.nodes.get('#current-instruction').textContent,/connected route/);
    assert.equal(c.nodes.get('#step-next').disabled,true);
    c.run('updateGuidanceControls()');
    assert.match(c.nodes.get('#current-instruction').textContent,/connected route/,'map redraw must retain the failure');
  });
  await check('map origin selection starts availability without choosing destination',async()=>{
    const c=client();c.run("routeSelection='empty';routeOrigin.value='';routeDestination.value='';selectUnit=async()=>{};");
    await c.run("activateRouteEndpoint('B')");
    assert.equal(c.context.gets.length,1);assert.match(c.context.gets[0].path,/origin_unit_id=B/);
    assert.equal(c.nodes.get('#route-destination').value,'');assert.equal(c.context.posts.length,0);
  });
  await check('new map origin clears the previous failed pair message while destinations load',async()=>{
    const c=client(true);
    c.run("renderRoute({status:409,code:'disconnected',profile:'default'});routeSelection='failed';selectUnit=async()=>{};");
    const oldError=c.nodes.get('#route-status').textContent;
    assert.match(oldError,/connected route/);
    await c.run("activateRouteEndpoint('A')");
    assert.equal(c.nodes.get('#route-origin').value,'A');
    assert.equal(c.nodes.get('#route-destination').value,'');
    assert.equal(c.nodes.get('#route-status').attributes['data-state'],'empty');
    assert.notEqual(c.nodes.get('#route-status').textContent,oldError,'an empty new pair must not display the previous disconnected failure');
    assert.notEqual(c.nodes.get('#current-instruction').textContent,oldError);
    assert.equal(c.context.posts.length,0,'choosing a new origin must not choose or route to a destination');
    c.context.gets[0].resolve(body());await Promise.resolve();await Promise.resolve();
    assert.match(c.nodes.get('#route-options-status').textContent,/1 mapped route/);
    assert.notEqual(c.nodes.get('#route-status').textContent,oldError);
  });
  await check('a small connected set names its exact destination and routes only after deliberate click',async()=>{
    const c=client(true);c.run("routeDestination.value='';routeUnits.find(u=>u.unit_id==='A').room_id='AQ6071';routeUnits.find(u=>u.unit_id==='B').room_id='AQ6067';allLevels[0].short_name='6000';");
    const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await pending;
    const choices=c.nodes.get('#reachable-destinations');
    assert.equal(choices.hidden,false);
    const buttons=choices.querySelectorAll('button');
    assert.equal(buttons.length,1);
    assert.match(buttons[0].textContent,/Directions to AQ6067.*AQ 6000/);
    assert.equal(buttons[0].dataset.destinationUnitId,'B');
    assert.equal(c.nodes.get('#route-destination').value,'');
    assert.equal(c.context.posts.length,0);
    const route=buttons[0].handlers.click();
    assert.equal(c.nodes.get('#route-destination').value,'B');
    assert.deepEqual(JSON.parse(JSON.stringify(c.context.posts[0].payload)),{origin:{unit_id:'A'},destination:{unit_id:'B'},profile:'default'});
    assert.equal(choices.children.length,0,'the previous availability actions must disappear while refreshing');
    c.context.posts[0].reject({payload:{status:409,code:'disconnected',profile:'default'}});await route;
  });
  await check('stale named buttons cannot route after profile refresh or Clear',async()=>{
    const c=client(true);const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await pending;
    const old=c.nodes.get('#reachable-destinations').querySelectorAll('button')[0];
    c.run("routeProfile.value='elevator_only';refreshRouteOptions()");
    assert.equal(c.nodes.get('#reachable-destinations').children.length,0);
    await old.handlers.click();assert.equal(c.context.posts.length,0);
    c.run('clearRoute()');
    c.context.gets[1].resolve(body('A','elevator_only'));await Promise.resolve();await Promise.resolve();
    assert.equal(c.nodes.get('#reachable-destinations').children.length,0);
    await old.handlers.click();assert.equal(c.context.posts.length,0);
    assert.equal(c.nodes.get('#route-destination').value,'');
  });
  await check('large reachable sets remain in the catalog without an arbitrary five-room shortlist',async()=>{
    const c=client(true);
    c.run("routeUnits.push(...['F','G'].map(unit_id=>({unit_id,room_id:'Room '+unit_id,level_id:'L'})))");
    const response=body();response.destinations=['B','C','D','E','F','G'].map(unit_id=>({unit_id,availability:'connected'}));
    const pending=c.run('refreshRouteOptions()');c.context.gets[0].resolve(response);await pending;
    assert.equal(c.nodes.get('#reachable-destinations').children.length,0);
    assert.equal(c.nodes.get('#reachable-destinations').hidden,true);
    assert.equal(c.nodes.get('#route-destination').querySelectorAll('option').filter(n=>n.dataset.availability==='connected').length,6);
  });
  await check('older service without guidance reports update needed beside map and form',async()=>{
    const c=client();c.run("renderRoute({status:200,profile:'default',origin:{unit_id:'A'},destination:{unit_id:'B'},steps:[],geometries:[]})");
    assert.match(c.nodes.get('#current-instruction').textContent,/demo needs an update/i);
    assert.equal(c.nodes.get('#route-status').textContent,c.nodes.get('#current-instruction').textContent);
    assert.equal(c.nodes.get('#route-status').attributes['data-state'],'error');
    assert.equal(c.run('activeRoute'),null);
  });
  await check('a destination selected while availability loads is never replaced',async()=>{
    const c=client();const pending=c.run('refreshRouteOptions()');c.run("routeDestination.value='E'");c.context.gets[0].resolve(body());await pending;
    assert.equal(c.nodes.get('#route-destination').value,'E');
    assert.match(c.nodes.get('#route-options-status').textContent,/selected destination has no mapped route point/);
  });
  await check('assistant and swap refresh for exact current origin/profile while preserving route payload',async()=>{
    const c=client();c.run("assistantInput.value='wheelchair directions from A to B';");
    const chat=c.nodes.get('#assistant-form').handlers.submit({preventDefault(){}});
    assert.match(c.context.gets[0].path,/origin_unit_id=A&profile=elevator_only/);
    assert.equal(c.context.posts[0].payload.destination.unit_id,'B');
    c.context.posts[0].reject({payload:{status:409,code:'no_elevator_only_route',profile:'elevator_only'}});await chat;
    const swapped=c.nodes.get('#route-swap').handlers.click();
    assert.match(c.context.gets[1].path,/origin_unit_id=B&profile=elevator_only/);
    assert.equal(c.context.posts[1].payload.origin.unit_id,'B');
    assert.equal(c.context.posts[1].payload.destination.unit_id,'A');
    c.context.posts[1].reject({payload:{status:409,code:'no_elevator_only_route',profile:'elevator_only'}});await swapped;
    c.context.gets[0].resolve(body('A','elevator_only'));await Promise.resolve();await Promise.resolve();
    assert.equal(c.nodes.get('#route-options-status').attributes['data-origin-unit-id'],'B');
    assert.equal(c.nodes.get('#route-destination').value,'A');
  });
  await check('same-room choice stays selected with a visible request correction',async()=>{
    const c=client();c.run("routeDestination.value='A'");await c.run('submitSelectedRoute()');
    assert.equal(c.context.posts.length,0);
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.match(c.nodes.get('#current-instruction').textContent,/distinct/);
  });
  await check('native select swap retains previous origin after availability grouping',async()=>{
    const c=client(true);const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    const swapped=c.nodes.get('#route-swap').handlers.click();
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.equal(c.context.posts.length,1);
    assert.equal(c.context.posts[0].payload.destination.unit_id,'A');
    c.context.posts[0].reject({payload:{status:409,code:'disconnected',profile:'default'}});await swapped;
  });
  await check('native select assistant can choose previous origin as destination',async()=>{
    const c=client(true);const options=c.run('refreshRouteOptions()');c.context.gets[0].resolve(body());await options;
    c.run("assistantInput.value='directions from B to A';");
    const chat=c.nodes.get('#assistant-form').handlers.submit({preventDefault(){}});
    assert.equal(c.nodes.get('#route-destination').value,'A');
    assert.equal(c.context.posts[0].payload.destination.unit_id,'A');
    c.context.posts[0].reject({payload:{status:409,code:'disconnected',profile:'default'}});await chat;
  });
  await check('unavailable guidance message survives floor redraw',async()=>{
    const c=client();c.run("renderRoute({status:200,profile:'default',origin:{unit_id:'A'},destination:{unit_id:'B'},guidance:{version:'dt018-guidance-v1',status:'unavailable',steps:[],geometries:[],visits:[],markers:[],transitions:[],distance_m:null,warnings:['Preview unavailable.']}})");
    const message=c.nodes.get('#current-instruction').textContent;c.run('updateGuidanceControls()');
    assert.equal(c.nodes.get('#current-instruction').textContent,message);
    assert.match(message,/preview is unavailable/);
  });
  assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);process.exitCode=1;});
