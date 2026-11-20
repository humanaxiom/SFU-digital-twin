const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Docker required');
const nodes = new Map();
let focusedElement;
class Node {
  constructor(tagName='div') { Object.assign(this,{tagName,value:'',dataset:{},attributes:{},children:[],handlers:{},hidden:false,textContent:''});this.classList={toggle(){}}; }
  addEventListener(k,v){this.handlers[k]=v;}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k];}
  removeAttribute(k){delete this.attributes[k];}
  append(...v){this.children.push(...v);v.forEach(n=>n.parent=this);}
  replaceChildren(...v){this.children=[];this.append(...v);if(this.tagName==='select')this.value=v[0]?.value||'';}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
  focus(){this.focused=true;focusedElement=this;}
  getBoundingClientRect(){return {width:800,height:600};}
  querySelectorAll(selector){const out=[];for(const n of this.children){if(selector===n.tagName||selector.startsWith('.')&&n.attributes.class?.split(' ').includes(selector.slice(1)))out.push(n);out.push(...n.querySelectorAll(selector));}return out;}
}
const document={querySelector(s){if(!nodes.has(s))nodes.set(s,new Node(s.includes('select')?'select':'div'));return nodes.get(s);},querySelectorAll(){return [];},createElement:n=>new Node(n),createElementNS:(_ns,n)=>new Node(n)};
const context=vm.createContext({document,console,CSS:{escape:s=>s},fetch:()=>new Promise(()=>{})});
const run=s=>vm.runInContext(s,context);
run(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js','utf8'));
run(`campusData={facilities:[
 {facility_id:'AQ',code:'AQ',name:'Academic Quadrangle',levels:[{level_id:'AQ0',short_name:'1',vertical_order:0,facility_id:'AQ'},{level_id:'AQ2',short_name:'3',vertical_order:2,facility_id:'AQ'},{level_id:'AQ5',short_name:'5',vertical_order:5,facility_id:'AQ'}]},
 {facility_id:'ECC',code:'ECC',name:'Education Centre',levels:[{level_id:'ECC0',short_name:'G',vertical_order:0,facility_id:'ECC'},{level_id:'ECC2',short_name:'2',vertical_order:2,facility_id:'ECC'}]},
 {facility_id:'SH',code:'SH',name:'Strand Hall',levels:[],coverage:'overview_only'}]};
 facilitiesById=new Map(campusData.facilities.map(x=>[x.facility_id,x]));
 initializeFloorControls(campusData.facilities.flatMap(x=>x.levels));
 selectCampusBuilding('AQ');
 globalThis.calls=[];globalThis.pending=[];
 request=(path,options)=>{calls.push(path);return new Promise((resolve,reject)=>pending.push({path,options,resolve,reject}));};
 globalThis.scene=id=>({level:{...allLevels.find(x=>x.level_id===id),geometry:{type:'Polygon',coordinates:[[[0,0],[20,0],[20,20],[0,0]]]}},details:[],units:[],landmarks:[]});
`);
const get=id=>document.querySelector(id);
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const resolveScene=async(id)=>{run(`pending.filter(x=>x.path.endsWith('/${id}/scene')).at(-1).resolve(scene('${id}'))`);await tick();};
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
const requests=path=>run(`pending.filter(item => item.path.startsWith(${JSON.stringify(path)}))`);
const routeRequests=()=>requests('/demo/v1/route').filter(item=>item.path==='/demo/v1/route');
const optionsRequests=()=>requests('/demo/v1/route-options?');
const change=(id,value)=>{const control=get(id);control.value=value;return control.handlers.change({target:control});};
const preview=()=>get('#route-form').handlers.submit({preventDefault(){}});
const assistant=message=>{get('#assistant-input').value=message;return get('#assistant-form').handlers.submit({preventDefault(){}});};
const catalog=[
 {unit_id:'unit-a',room_id:'AQ1001',facility_id:'AQ',level_id:'AQ0'},
 {unit_id:'unit-b',room_id:'AQ1002',facility_id:'AQ',level_id:'AQ0'},
 {unit_id:'unit-c',room_id:'AQ3001',facility_id:'AQ',level_id:'AQ2'},
];
const setCatalog=()=>run(`routeUnits=${JSON.stringify(catalog)};renderRouteCatalog();`);
const editDraft=changes=>run(`editRouteDraft(${JSON.stringify(changes)})`);
const chooseDestination=id=>run(`activateRouteDestination(${JSON.stringify(id)})`);
async function openDraft() {
  setCatalog();
  await open('AQ0');
  editDraft({origin:'unit-a'});
  assert.equal(optionsRequests().length,1,'a draft starting room checks mapped connections');
}
async function resolveOptions(overrides={}, request=optionsRequests().at(-1)) {
  const query=new URL(request.path,'http://fixture.invalid').searchParams;
  const origin=query.get('origin_unit_id');
  request.resolve({version:'route-options-v1',origin_unit_id:origin,profile:query.get('profile'),
    destinations:catalog.filter(({unit_id})=>unit_id!==origin).map(({unit_id})=>({
      unit_id,availability:overrides[unit_id] || 'connected',
    }))});
  await tick();
}
function step(levelId, instruction) {
  return {step_id:`step-${levelId}`,visit_id:`visit-${levelId}`,level_id:levelId,instruction,geometry_ids:[],marker_ids:[]};
}
function routeResult(origin, destination, profile='default', steps=[]) {
  return {status:200,profile,origin:{unit_id:origin},destination:{unit_id:destination},levels:[],
    guidance:{version:'dt018-guidance-v1',status:'available',distance_m:1,warnings:[],transitions:[],
      geometries:[],markers:[],visits:steps.map(({visit_id,level_id})=>({visit_id,level_id,label:level_id})),steps}};
}
async function open(id){const p=run(`previewFloor('${id}')`);await resolveScene(id);await p;}
async function roomAccessibility(fixture) {
  await open('AQ0');
  const inspection = run(`selectUnit('${fixture.unit_id}', true)`);
  const endpoint = `/demo/v1/units/${fixture.unit_id}`;
  run(`pending.find(request => request.path === '${endpoint}').resolve(${JSON.stringify(fixture)})`);
  assert.equal(await inspection, true);
  const rows = get('#unit-details').children.map(row => row.children.map(cell => cell.textContent));
  assert.deepEqual(rows, [
    ['Room', fixture.room_id],
    ['Recorded category', fixture.category],
    ['Source use type', fixture.use_type],
    ['Physical accessibility', 'Unverified. This demo has no physical accessibility survey for this room.'],
  ], `legacy accessibility value ${fixture.accessible} must not imply physical verification`);
  assert.equal(get('.facts').open, true);
  assert.equal(get(`[data-unit-id="${fixture.unit_id}"]`).focused, true);
}
async function delayedAvailability(fail = false) {
  await openDraft();
  const selection=chooseDestination('unit-b');
  assert.equal(get('#route-destination').value,'','destination action must wait for matching availability');
  await open('AQ2');
  if(fail) optionsRequests().at(-1).reject(new Error('choices unavailable'));
  else await resolveOptions();
  await selection;
  assert.equal(get('#route-destination').value,'unit-b','connected or unknown room may become the draft destination');
  assert.equal(routeRequests().length,0,'resolved availability may edit the draft only');
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ2','availability must not steal newer floor');
  assert.equal(get('#level-select').value,'AQ2','requested floor must remain owned by newer intent');
  assert.equal(requests('/demo/v1/units/unit-b').length,0,'draft actions must not start obsolete room inspections');
  if(fail) assert.equal(get('#route-options-status').getAttribute('data-state'),'error');
  const submitted=preview();
  await tick();
  assert.equal(routeRequests().length,1,'the explicit Preview permits unknown availability as fallback');
  routeRequests()[0].resolve(routeResult('unit-a','unit-b'));
  await submitted;
}
const cases={
 async artifact_scene_cache(){
  const scopedScene=(id,hash)=>({...run(`scene('${id}')`),provenance:[{artifact_sha256:hash}]});
  run("setSceneArtifact('first')");
  const first=run("getFloorScene('AQ0')");
  const duplicate=run("getFloorScene('AQ0')");
  assert.equal(requests('/demo/v1/levels/AQ0/scene').length,1);
  requests('/demo/v1/levels/AQ0/scene')[0].resolve(scopedScene('AQ0','first'));
  assert.equal(await first,await duplicate);
  assert.equal(await run("getFloorScene('AQ0')"),await first);
  assert.equal(requests('/demo/v1/levels/AQ0/scene').length,1);
  const obsolete=run("getFloorScene('AQ2')");
  run("setSceneArtifact('second')");
  const current=run("getFloorScene('AQ2')");
  const loads=requests('/demo/v1/levels/AQ2/scene');
  assert.equal(loads.length,2);
  loads[1].resolve(scopedScene('AQ2','second'));
  const currentScene=await current;
  loads[0].resolve(scopedScene('AQ2','first'));
  await obsolete;
  assert.equal(await run("getFloorScene('AQ2')"),currentScene);
  const mismatch=run("getFloorScene('AQ0')");
  requests('/demo/v1/levels/AQ0/scene').at(-1).resolve(run("scene('AQ2')"));
  await assert.rejects(mismatch,/does not match/);
  const wrongArtifact=run("getFloorScene('AQ0')");
  requests('/demo/v1/levels/AQ0/scene').at(-1).resolve(scopedScene('AQ0','first'));
  await assert.rejects(wrongArtifact,/artifact/i);
  const retry=run("getFloorScene('AQ0')");
  requests('/demo/v1/levels/AQ0/scene').at(-1).resolve(scopedScene('AQ0','second'));
  assert.equal((await retry).level.level_id,'AQ0');
  run(`activeRoute={guidance:{visits:[
    {visit_id:'v1', level_id:'AQ0'}, {visit_id:'v2', level_id:'AQ2'},
    {visit_id:'v3', level_id:'AQ5'}]}}; prefetchAdjacentVisits('v2')`);
  assert.equal(requests('/demo/v1/levels/AQ5/scene').length,1);
  const displayedBeforePrefetch=get('#viewing-floor').textContent;
  const statusBeforePrefetch=get('#map-status').textContent;
  requests('/demo/v1/levels/AQ5/scene').at(-1).resolve(scopedScene('AQ5','second'));
  await tick();
  assert.equal(get('#viewing-floor').textContent,displayedBeforePrefetch);
  assert.equal(get('#map-status').textContent,statusBeforePrefetch);
  assert.equal((await run("getFloorScene('AQ5')")).level.level_id,'AQ5');
  assert.equal(requests('/demo/v1/levels/AQ5/scene').length,1);
  // More distinct floors than the cache budget should evict the oldest one.
  for(let index=0;index<8;index++){
    const id=`extra-${index}`;
    const load=run(`getFloorScene('${id}')`);
    requests(`/demo/v1/levels/${id}/scene`).at(-1).resolve({level:{level_id:id},provenance:[{artifact_sha256:'second'}]});
    await load;
  }
  const evicted=run("getFloorScene('AQ5')");
  assert.equal(requests('/demo/v1/levels/AQ5/scene').length,2);
  requests('/demo/v1/levels/AQ5/scene').at(-1).resolve(scopedScene('AQ5','second'));
  await evicted;
 },
 async edits_require_preview(){
  setCatalog();
  change('#route-origin','unit-a');
  change('#route-destination','unit-b');
  change('#route-profile','elevator_only');
  get('#route-swap').handlers.click();
  assert.equal(routeRequests().length,0,'endpoint, profile and Swap edits must never submit');
  assert.equal(get('#route-origin').value,'unit-b');
  assert.equal(get('#route-destination').value,'unit-a');
  await resolveOptions();
  const submitted=preview();
  await tick();
  assert.equal(routeRequests().length,1);
  assert.deepEqual(JSON.parse(routeRequests()[0].options.body),{
    origin:{unit_id:'unit-b'},destination:{unit_id:'unit-a'},profile:'elevator_only',
  });
  routeRequests()[0].resolve(routeResult('unit-b','unit-a','elevator_only'));
  await submitted;
  assert.equal(get('#route-accessibility').hidden,false);
  change('#route-profile','default');
  assert.equal(routeRequests().length,1);
  assert.equal(get('#route-profile-help').hidden,true);
  assert.equal(get('#route-accessibility').hidden,false,'editing the draft preserves the committed elevator-only disclosure');
  assert.match(get('#map-route-identity').textContent,/elevator only.*stairs excluded/i);
 },
 async assistant_drafts_exact_ids(){
  setCatalog();
  const command=assistant('Accessible directions from aq1001 to AQ3001');
  assert.equal(routeRequests().length,0,'assistant directions must wait for Preview route');
  await command;
  assert.equal(get('#route-origin').value,'unit-a');
  assert.equal(get('#route-destination').value,'unit-c');
  assert.equal(get('#route-profile').value,'elevator_only');
  assert.match(get('#assistant-response').textContent,/Preview route/i);
  await resolveOptions();
  const submitted=preview();
  await tick();
  assert.deepEqual(JSON.parse(routeRequests()[0].options.body),{
    origin:{unit_id:'unit-a'},destination:{unit_id:'unit-c'},profile:'elevator_only',
  });
  routeRequests()[0].resolve(routeResult('unit-a','unit-c','elevator_only'));
  await submitted;
 },
 async assistant_requires_unambiguous_ids(){
  setCatalog();
  run("routeUnits.push({...routeUnits[1],unit_id:'another-unit',room_id:'AQ3001'});");
  editDraft({origin:'unit-a',destination:'unit-b'});
  await assistant('Directions from AQ1001 to AQ3001');
  assert.equal(routeRequests().length,0);
  assert.equal(get('#route-origin').value,'unit-a');
  assert.equal(get('#route-destination').value,'unit-b','ambiguous code must preserve the draft');
  assert.match(get('#assistant-response').textContent,/choose|search|match/i);
  await assistant('Directions from AQ1001 to UNKNOWN');
  assert.equal(routeRequests().length,0);
  assert.equal(get('#route-destination').value,'unit-b','unresolved room cannot become a draft identity');
  assert.match(get('#assistant-response').textContent,/choose|search|match|find/i);
 },
 async map_room_actions_preserve_inspection(){
  setCatalog();
  run(`globalThis.baseScene=scene;
    scene=id=>{
      const value=baseScene(id);
      value.units=routeUnits.filter(room=>room.level_id===id).map(room=>({...room,geometry:value.level.geometry}));
      return value;
    };`);
  await open('AQ0');
  const rooms=get('#floor-map').querySelectorAll('path');
  const first=rooms.find(node=>node.dataset.unitId==='unit-a');
  const second=rooms.find(node=>node.dataset.unitId==='unit-b');
  first.handlers.click();
  requests('/demo/v1/units/unit-a')[0].resolve(catalog[0]);
  await tick();
  assert.equal(get('#route-origin').value,'','clicking a room only inspects it');
  assert.match(text(get('#unit-details')),/AQ1001/);
  get('#room-start-here').handlers.click();
  assert.equal(get('#route-origin').value,'unit-a');
  assert.equal(get('#room-directions-here').disabled,true,'the current From room cannot be selected as To');
  await resolveOptions({'unit-b':'disconnected'});

  let prevented=false;
  second.handlers.keydown({key:'Enter',preventDefault(){prevented=true;}});
  if (/AQ1001/.test(text(get('#unit-details')))) {
    assert.equal(get('#room-start-here').disabled,true,'old room details cannot accompany an enabled action for the newly selected room');
    assert.equal(get('#room-directions-here').disabled,true,'old room details cannot accompany an enabled destination action');
  }
  requests('/demo/v1/units/unit-b')[0].resolve(catalog[1]);
  await tick();
  assert.equal(prevented,true);
  assert.match(text(get('#unit-details')),/AQ1002/,'keyboard can inspect an unsupported destination');
  assert.equal(get('#room-directions-here').disabled,true,'disconnected room cannot be selected via the map action');
  assert.equal(get('#route-destination').value,'');
  assert.equal(second.getAttribute('aria-disabled'),undefined,'map inspection remains available');

  prevented=false;
  first.handlers.keydown({key:' ',preventDefault(){prevented=true;}});
  requests('/demo/v1/units/unit-a').at(-1).resolve(catalog[0]);
  await tick();
  assert.equal(prevented,true);
  assert.match(text(get('#unit-details')),/AQ1001/,'Space also opens the room inspector');

  run('void refreshRouteOptions()');
  await resolveOptions();
  const inList=get('#room-list').children.find(node=>node.dataset.unitId==='unit-b');
  inList.handlers.click();
  requests('/demo/v1/units/unit-b').at(-1).resolve(catalog[1]);
  await tick();
  get('#room-directions-here').handlers.click();
  await tick();
  assert.equal(get('#route-destination').value,'unit-b');
  assert.equal(routeRequests().length,0,'both explicit map actions only edit the draft');

  get('#zoom-in').handlers.click();
  const inspectedCamera=get('#floor-map').getAttribute('viewBox');
  get('#route-clear').handlers.click();
  assert.equal(get('#route-origin').value,'');
  assert.equal(get('#route-destination').value,'');
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  assert.equal(get('#floor-map').getAttribute('viewBox'),inspectedCamera,'Clear preserves deliberate camera');
  assert.match(text(get('#unit-details')),/AQ1002/,'Clear preserves the inspected room');
  get('#room-start-here').handlers.click();
  assert.equal(get('#route-origin').value,'unit-b','the preserved inspection can start a new draft');
  assert.equal(routeRequests().length,0);
 },
 async preview_commits_snapshot_after_draft_edits(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const submitted=preview();
  await tick();
  editDraft({destination:'unit-c',profile:'elevator_only'});
  assert.match(get('#route-request-status').textContent,/AQ1001.*AQ1002/,'pending label identifies the submitted pair');
  assert.equal(routeRequests().length,1,'newer edits must not submit a replacement');
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Original route instruction')]));
  await submitted;
  await tick();
  assert.equal(get('#route-destination').value,'unit-c');
  assert.equal(get('#route-profile').value,'elevator_only');
  assert.match(get('#route-draft-status').textContent,/Route changes not applied/i);
  assert.match(get('#map-route-identity').textContent,/AQ1001.*AQ1002.*stairs or elevators/i);
  assert.match(get('#route-committed-identity').textContent,/AQ1001.*AQ1002.*stairs or elevators/i);
  assert.match(get('#current-instruction').textContent,/Original route instruction/);
  assert.equal(get('#route-accessibility').hidden,true,'draft profile must not qualify the committed stairs-capable route');
 },
 async failed_replacement_preserves_committed_route(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const original=preview();
  await tick();
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Keep this instruction')]));
  await original;
  await tick();
  const identity=get('#map-route-identity').textContent;
  editDraft({destination:'unit-c',profile:'elevator_only'});
  await resolveOptions();
  const replacement=preview();
  await tick();
  assert.equal(get('#map-route-identity').textContent,identity,'pending replacement preserves committed label');
  assert.equal(get('#route-status').getAttribute('data-state'),'success','pending request does not change committed status');
  assert.match(get('#current-instruction').textContent,/Keep this instruction/);
  routeRequests()[1].reject(Object.assign(new Error('No elevator-only route'),{
    payload:{status:409,code:'no_elevator_only_route',profile:'elevator_only'},
  }));
  await replacement;
  assert.equal(get('#map-route-identity').textContent,identity,'failed replacement preserves committed label');
  assert.equal(get('#route-status').getAttribute('data-state'),'success','failed replacement does not change committed status');
  assert.equal(get('#route-request-status').dataset.state,'error');
  assert.match(get('#current-instruction').textContent,/Keep this instruction/);
  assert.match(get('#route-request-status').textContent,/AQ1001.*AQ3001.*elevator only/i);
  assert.match(get('#route-request-status').textContent,/stairs|unavailable/i);
  assert.match(get('#route-draft-status').textContent,/Route changes not applied/i);
  assert.equal(get('#route-accessibility').hidden,true);
 },
 async latest_preview_wins(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const old=preview();
  await tick();
  await chooseDestination('unit-c');
  const latest=preview();
  await tick();
  assert.equal(routeRequests().length,2);
  routeRequests()[1].resolve(routeResult('unit-a','unit-c','default',[step('AQ0','New instruction')]));
  await latest;
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Obsolete instruction')]));
  await old;
  await tick();
  assert.match(get('#map-route-identity').textContent,/AQ1001.*AQ3001/);
  assert.match(get('#current-instruction').textContent,/New instruction/);
  assert.doesNotMatch(text(get('#route-steps')),/Obsolete instruction/);
 },
 async clear_cancels_preview(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const submitted=preview();
  await tick();
  get('#route-clear').handlers.click();
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Obsolete instruction')]));
  await submitted;
  assert.equal(run('activeRoute'),null,'a response to a cleared request cannot restore a route');
  assert.equal(get('#route-origin').value,'');
  assert.equal(get('#route-destination').value,'');
  assert.equal(get('#route-options-status').getAttribute('data-state'),'empty');
  assert.doesNotMatch(text(get('#route-steps')),/Obsolete instruction/);
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
 },
 async preview_checks_known_outcomes(){
  await openDraft();
  for (const [outcome, expected] of [
    ['disconnected',/no mapped connection/i],
    ['same_anchor',/same route point.*no walking path/i],
    ['endpoint_unavailable',/no mapped route point/i],
  ]) {
    editDraft({destination:'unit-b'});
    const submitted=preview();
    assert.equal(routeRequests().length,0,'Preview must wait for pending availability');
    await resolveOptions({'unit-b':outcome});
    await submitted;
    assert.equal(routeRequests().length,0,'known unsupported result must not submit');
    assert.match(get('#route-request-status').textContent,expected);
    assert.equal(get('#route-destination').value,'unit-b','unsupported identity remains in the draft');
    run('void refreshRouteOptions()');
  }
 },
 async preview_uses_matching_options_after_draft_edit(){
  await openDraft();
  editDraft({destination:'unit-b'});
  const originalOptions=optionsRequests()[0];
  const submitted=preview();
  assert.equal(routeRequests().length,0,'Preview waits for the submitted origin/profile options');
  editDraft({origin:'unit-c',destination:'unit-a',profile:'elevator_only'});
  await resolveOptions();
  assert.equal(routeRequests().length,0,'newer draft options must not release the older Preview');
  await resolveOptions({'unit-b':'disconnected'},originalOptions);
  await submitted;
  assert.equal(routeRequests().length,0,'matching disconnected outcome prevents a route POST');
  assert.match(get('#route-request-status').textContent,/AQ1001.*AQ1002.*stairs or elevators.*no mapped connection/i);
  assert.equal(get('#route-origin').value,'unit-c');
  assert.equal(get('#route-destination').value,'unit-a');
  assert.equal(get('#route-profile').value,'elevator_only');
  assert.equal(get('#route-options-status').getAttribute('data-origin-unit-id'),'unit-c');
 },
 async malformed_success_preserves_committed_route(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const original=preview();
  await tick();
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Keep this route')]));
  await original;
  await tick();
  const identity=get('#map-route-identity').textContent;
  await chooseDestination('unit-c');
  const malformed=routeResult('unit-a','unit-c');
  malformed.guidance.version='unsupported-fixture';
  const invalidDistance=routeResult('unit-a','unit-c');
  invalidDistance.guidance.distance_m='unknown';
  for (const invalid of [malformed, invalidDistance, routeResult('unit-a','unit-b'), routeResult('unit-a','unit-c','elevator_only')]) {
    const replacement=preview();
    await tick();
    routeRequests().at(-1).resolve(invalid);
    await replacement;
    assert.equal(get('#map-route-identity').textContent,identity,'invalid success response must not replace the displayed identity');
    assert.equal(run('activeRoute.destination.unit_id'),'unit-b');
    assert.match(get('#current-instruction').textContent,/Keep this route/);
    assert.match(get('#route-request-status').textContent,/failed.*AQ1001.*AQ3001/i);
  }
 },
 async qualified_success_replaces_committed_route(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const original=preview();
  await tick();
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Old route instruction')]));
  await original;
  await tick();
  await chooseDestination('unit-c');
  for (const status of ['limited','unavailable']) {
    const replacement=preview();
    await tick();
    const qualified=routeResult('unit-a','unit-c');
    Object.assign(qualified.guidance,{status,distance_m:null,warnings:[`Guidance ${status} in fixture`]});
    routeRequests().at(-1).resolve(qualified);
    await replacement;
    assert.match(get('#map-route-identity').textContent,/AQ1001.*AQ3001/);
    assert.match(get('#route-status').textContent,new RegExp(`Guidance ${status} in fixture`));
    assert.doesNotMatch(text(get('#route-steps')),/Old route instruction/);
    assert.doesNotMatch(get('#current-instruction').textContent,/Old route instruction/);
  }
 },
 async availability_newer_room(){
  await openDraft();
  const selection=chooseDestination('unit-b');
  const inspection=run("selectUnit('newer',true)");
  run("pending.find(x=>x.path.endsWith('/newer')).resolve({unit_id:'newer',room_id:'NEWER'})");await inspection;
  await resolveOptions();
  await selection;
  assert.equal(requests('/demo/v1/units/unit-b').length,0,'waiting destination must not repeat room inspection');
  assert.match(text(get('#unit-details')),/NEWER/,'waiting destination must not replace newer same-floor room details');
  assert.equal(routeRequests().length,0);
 },
 async unsupported_after_wait(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const valid=preview();
  await tick();
  run('void refreshRouteOptions()');
  const unsupported=chooseDestination('unit-c');
  await resolveOptions({'unit-c':'disconnected'});
  await unsupported;
  assert.equal(get('#route-destination').value,'unit-b','availability-rejected map action preserves the selected destination');
  assert.equal(routeRequests().length,1,'rejected map action must not submit another request');
  routeRequests()[0].resolve(routeResult('unit-a','unit-b'));
  await valid;
  assert.equal(run('activeRoute.destination.unit_id'),'unit-b','availability-rejected action must preserve the earlier pending preview');
 },
 async unsupported_during_route(){
  await openDraft();
  await resolveOptions({'unit-c':'disconnected'});
  await chooseDestination('unit-b');
  const valid=preview();
  await tick();
  await chooseDestination('unit-c');
  assert.equal(get('#route-destination').value,'unit-b','known unsupported map action must leave the draft intact');
  assert.equal(routeRequests().length,1);
  routeRequests()[0].resolve(routeResult('unit-a','unit-b'));
  await valid;
  assert.equal(run('activeRoute.destination.unit_id'),'unit-b','unsupported action must not strand an accepted request in pending state');
 },
 async route_cancels_old_step(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-c');
  run(`navigationState.pendingStep={stepId:'old'};`);
  const replacement=preview();
  await tick();
  routeRequests()[0].resolve(routeResult('unit-a','unit-c','default',[step('AQ0','New route')]));
  await replacement;await tick();
  assert.equal(run('manualPreview'),false,'request-owned cancellation must not turn the new route into exploration');
  assert.equal(get('#return-to-route').hidden,true,'current route should follow without unnecessary Return');
 },
 async availability_clear_reselect(){
  await openDraft();
  const selection=chooseDestination('unit-b');
  const original=optionsRequests()[0];
  get('#route-clear').handlers.click();
  editDraft({origin:'unit-a'});
  assert.equal(optionsRequests().length,2);
  await resolveOptions({},original);
  await resolveOptions({'unit-b':'disconnected'});
  await selection;
  assert.equal(get('#route-destination').value,'','Clear must cancel a waiting action even if the same origin is selected again');
  assert.equal(run("currentRouteAvailability()?.get('unit-b')"),'disconnected','obsolete choices must not replace the latest options');
  assert.equal(routeRequests().length,0);
 },
 async availability_latest_destination(){
  await openDraft();
  const older=chooseDestination('unit-b');
  const newer=chooseDestination('unit-c');
  await resolveOptions();
  await older;await newer;
  assert.equal(routeRequests().length,0,'neither destination action may submit');
  assert.equal(get('#route-destination').value,'unit-c','only the newest waiting action can edit the draft');
 },
 async delayed_availability(){await delayedAvailability();},
 async delayed_availability_failure(){await delayedAvailability(true);},
 async floors(){
  assert.deepEqual(get('#level-select').children.map(n=>n.value),['AQ0','AQ2','AQ5'],'Floor choices must be exact IDs scoped to AQ');
  assert.deepEqual(get('#facility-select').children.map(n=>n.value),['AQ','ECC','SH'],'all buildings remain discoverable');
  await open('AQ5');
  assert.equal(get('#facility-select').value,'AQ');
  run("selectCampusBuilding('ECC')");
  assert.equal(get('#level-select').value,'ECC0','first visit uses own order-zero floor');
  await open('ECC2');run("selectCampusBuilding('AQ')");
  assert.equal(get('#level-select').value,'AQ5','return remembers exact AQ floor');
  run("selectCampusBuilding('SH')");
  assert.equal(get('#level-select').disabled,true);
  assert.equal(get('#open-floor').disabled,true);
  assert.deepEqual(get('#facility-select').children.map(n=>n.value),['AQ','ECC','SH']);
 },
 async open(){
  assert.equal(typeof get('#open-floor').handlers.click,'function','already-selected floor needs explicit Open floor');
  get('#open-floor').handlers.click();await resolveScene('AQ0');
  assert.equal(get('#floor-view').hidden,false);
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
 },
 async retry(){
  await open('AQ0');const p=run("previewFloor('AQ2')");
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0','loading label must retain displayed floor');
  assert.match(get('#map-status').textContent,/AQ 3/);
  run("pending.find(x=>x.path.endsWith('/AQ2/scene')).reject(new Error('test outage'))");await p;
  assert.equal(get('#level-select').value,'AQ2','failed requested floor remains selected for retry');
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  assert.match(get('#map-status').textContent,/AQ 3.*AQ 1/);
  assert.equal(get('#retry-scene').hidden,false);
  assert.equal(typeof get('#retry-scene').handlers.click,'function','scene error exposes Retry');
  get('#retry-scene').handlers.click();
  run("pending.filter(x=>x.path.endsWith('/AQ2/scene')).at(-1).resolve(scene('AQ2'))");await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ2');
  assert.equal(get('#retry-scene').hidden,true);
 },
 async scenes(){
  await open('AQ0');const older=run("previewFloor('AQ2')");const newer=run("previewFloor('AQ5')");
  await resolveScene('AQ5');await newer;
  await resolveScene('AQ2');await older;
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ5','late scene cannot replace newer scene');
  assert.equal(get('#level-select').value,'AQ5');
  assert.equal(get('#facility-select').value,'AQ');
 },
 async rooms(){
  await open('AQ0');const old=run("selectUnit('old',true)");const latest=run("selectUnit('latest',true)");
  run("pending.find(x=>x.path.endsWith('/latest')).resolve({unit_id:'latest',room_id:'LATEST'})");await latest;
  assert.equal(focusedElement,get('[data-unit-id="latest"]'));
  run("pending.find(x=>x.path.endsWith('/old')).resolve({unit_id:'old',room_id:'OLD'})");await old;
  assert.match(text(get('#unit-details')),/LATEST/,'late room response cannot replace newer room');
  assert.doesNotMatch(text(get('#unit-details')),/OLD/);
  assert.equal(focusedElement,get('[data-unit-id="latest"]'),'late room response cannot steal focus');
  const moving=run("selectUnit('moving',true)");await open('AQ2');const status=get('#map-status').textContent;
  run("pending.find(x=>x.path.endsWith('/moving')).resolve({unit_id:'moving',room_id:'MOVING'})");await moving;
  assert.equal(get('#map-status').textContent,status,'room response from another floor cannot overwrite floor status');
 },
 async room_accessibility_true(){
  await roomAccessibility({ unit_id: 'tagged', room_id: 'AQ1001', category: 'washroom',
    use_type: 'Washroom, single-stall, accessible', accessible: true,
    verified_by: 'source_gdb_use_type', verified_date: '2026-08-30' });
 },
 async room_accessibility_false(){
  await roomAccessibility({ unit_id: 'defaulted', room_id: 'AQ1002', category: 'washroom',
    use_type: 'Washroom, single-stall', accessible: false,
    verified_by: 'source_gdb_use_type', verified_date: '2026-08-30' });
 },
 async room_accessibility_unknown(){
  await roomAccessibility({ unit_id: 'unknown', room_id: 'AQ1003', category: 'office',
    use_type: 'Office', accessible: null, verified_by: null, verified_date: null });
 },
 async clear_room(){
  await open('AQ0');const lookup=run("selectUnit('cleared',true)");run('clearRoute()');
  run("pending.find(x=>x.path.endsWith('/cleared')).resolve({unit_id:'cleared',room_id:'CLEARED'})");await lookup;
  assert.match(get('#map-status').textContent,/CLEARED/,'Clear retains the selected room when its details are still loading');
  assert.match(text(get('#unit-details')),/CLEARED/);
  assert.equal(get('[data-unit-id="cleared"]').focused,true);
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0','Clear preserves displayed floor');
 },
 async assistant_floor(){
  await open('AQ0');get('#assistant-input').value='Find old room';
  const lookup=get('#assistant-form').handlers.submit({preventDefault(){}});await open('AQ2');
  const status=get('#map-status').textContent;
  run("pending.find(x=>x.path==='/demo/v1/assistant').resolve({text:'OLD ANSWER',entities:[{type:'unit',unit_id:'old',level_id:'AQ0'}]})");await lookup;
  assert.notEqual(get('#assistant-response').textContent,'OLD ANSWER','old-floor assistant response must not replace current context');
  assert.equal(get('#map-status').textContent,status);
  assert.equal(run("calls.includes('/demo/v1/units/old')"),false,'late assistant must not start obsolete unit lookup');
 },
 async assistant_latest(){
  await open('AQ0');get('#assistant-input').value='Find old room';
  const old=get('#assistant-form').handlers.submit({preventDefault(){}});
  get('#assistant-input').value='Find latest room';
  const latest=get('#assistant-form').handlers.submit({preventDefault(){}});
  run("pending.filter(x=>x.path==='/demo/v1/assistant')[1].resolve({text:'LATEST ANSWER',entities:[]})");await latest;
  run("pending.filter(x=>x.path==='/demo/v1/assistant')[0].resolve({text:'OLD ANSWER',entities:[{type:'unit',unit_id:'old',level_id:'AQ0'}]})");await tick();
  assert.equal(get('#assistant-response').textContent,'LATEST ANSWER','older assistant lookup cannot overwrite newer result');
  assert.equal(run("calls.includes('/demo/v1/units/old')"),false,'older assistant cannot inspect obsolete room');
  await old;
 },
 async replacement_pending_step(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const original=preview();
  await tick();
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[
    step('AQ0','Start on AQ 1'),step('AQ2','Finish on AQ 3'),
  ]));
  await original;
  await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  const oldStep=run("selectGuidanceStep('step-AQ2')");
  await chooseDestination('unit-c');
  const replacement=preview();
  await tick();
  assert.equal(get('#level-select').value,'AQ2','pending replacement preserves the previous route step target');
  routeRequests()[1].resolve(routeResult('unit-a','unit-c','default',[step('AQ0','New route on AQ 1')]));
  await replacement;
  await resolveScene('AQ2');await oldStep;
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0','obsolete route-owned scene must not render after successful replacement');
  assert.equal(get('#level-select').value,'AQ0','replacement controls identify the new route scene');
  assert.equal(get('#facility-select').value,'AQ');
  assert.equal(run('navigationState.pendingStep'),null,'replaced route cannot retain a pending instruction');
  assert.equal(get('#floor-map').getAttribute('aria-busy'),'false');
  assert.equal(get('#current-instruction').textContent,'New route on AQ 1');
 },
 async journey_retry_and_cameras(){
  await open('AQ0');
  const route=routeResult('unit-a','unit-c','default',[step('AQ0','Start here'),step('AQ2','Finish here')]);
  run(`renderRoute(${JSON.stringify(route)})`);
  await tick();
  const box=()=>get('#floor-map').getAttribute('viewBox');
  run('zoomMap(0.5)');
  const routeBox=box();
  await open('AQ2');
  run('zoomMap(0.25)');
  const exploredBox=box();
  const returning=get('#return-to-route').handlers.click();
  await resolveScene('AQ0');
  await returning;
  assert.equal(box(),routeBox);
  await open('AQ2');
  assert.equal(box(),exploredBox);
  const again=get('#return-to-route').handlers.click();
  await resolveScene('AQ0');
  await again;
  const next=get('#step-next').handlers.click();
  requests('/demo/v1/levels/AQ2/scene').at(-1).reject(new Error('test scene outage'));
  await next;
  assert.equal(get('#retry-scene').hidden,false);
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  const retry=get('#retry-scene').handlers.click();
  await resolveScene('AQ2');
  await retry;
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ2');
  assert.equal(get('#current-instruction').textContent,'Finish here');
  assert.equal(get('#return-to-route').hidden,true);
 },
 async retained_room_loading(){
  await open('AQ0');const loading=run("previewFloor('AQ2')");
  const status=get('#map-status').textContent;
  const inspection=run("activateRouteEndpoint('retained',true)");
  run("pending.find(x=>x.path.endsWith('/retained')).resolve({unit_id:'retained',room_id:'RETAINED'})");await inspection;
  assert.equal(get('#map-status').textContent,status,'retained-map room inspection must preserve requested/displayed loading status');
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  assert.equal(get('#level-select').value,'AQ2');
  await resolveScene('AQ2');await loading;
 },
 async retained_landmark_loading(){
  await open('AQ0');const loading=run("previewFloor('AQ2')");
  const status=get('#map-status').textContent;
  run("selectLandmark({landmark_id:'old-landmark',category:'Lift',level_id:'AQ0'},document.createElement('circle'))");
  assert.equal(get('#map-status').textContent,status,'retained-map landmark inspection must preserve requested/displayed loading status');
  await resolveScene('AQ2');await loading;
 },
 async clear_scene_error(){
  await open('AQ0');const loading=run("previewFloor('AQ2')");
  run("pending.find(x=>x.path.endsWith('/AQ2/scene')).reject(new Error('floor outage'))");await loading;
  const status=get('#map-status').textContent;
  assert.match(status,/Could not load.*AQ 3.*AQ 1/);
  run('clearRoute()');
  assert.equal(get('#map-status').textContent,status,'Clear must preserve outstanding floor error and retained-scene identity');
  assert.equal(get('#retry-scene').hidden,false,'Clear must leave failed floor Retry available');
  assert.equal(get('#level-select').value,'AQ2');
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
 },
 async initial_route_pending(){
  await open('AQ0');
  run(`renderRoute({status:200,profile:'default',origin:{unit_id:'a'},destination:{unit_id:'b'},levels:[],guidance:{version:'dt018-guidance-v1',status:'available',distance_m:1,warnings:[],transitions:[],geometries:[],markers:[],visits:[{visit_id:'v2',level_id:'AQ2',label:'AQ 3'}],steps:[{step_id:'s2',visit_id:'v2',level_id:'AQ2',instruction:'NEW INSTRUCTION ON AQ3',geometry_ids:[],marker_ids:[]}]}})`);
  await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  assert.doesNotMatch(get('#current-instruction').textContent,/NEW INSTRUCTION ON AQ3/,'initial route instruction cannot appear mapped before its scene loads');
  assert.match(get('#current-instruction').textContent,/loading/i,'pending instruction area explains requested scene loading');
  assert.equal(get('#step-next').disabled,true);
  run("pending.find(x=>x.path.endsWith('/AQ2/scene')).reject(new Error('scene failed'))");await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  assert.match(get('#current-instruction').textContent,/unavailable|not.*(?:display|mapped|loaded)|could not|preview/i,'failed initial scene leaves an explicitly unmapped instruction state');
  assert.notEqual(get('#current-instruction').textContent,'NEW INSTRUCTION ON AQ3');
  assert.equal(get('#retry-scene').hidden,false);
 },
 async route(){
  await openDraft();
  await resolveOptions();
  await chooseDestination('unit-b');
  const p=preview();
  await tick();
  await open('AQ2');
  routeRequests()[0].resolve(routeResult('unit-a','unit-b','default',[step('AQ0','Start on AQ 1')]));
  await p;await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ2','late route must not steal newer floor');
  assert.equal(get('#level-select').value,'AQ2','late route must not reset requested floor');
  assert.equal(get('#facility-select').value,'AQ');
  assert.equal(run('activeRoute.destination.unit_id'),'unit-b','late valid result remains available');
  assert.equal(get('#return-to-route').hidden,false,'late result offers deliberate Return to route');
 }
};
(async()=>{assert.ok(cases[process.argv[2]],'named case required');await cases[process.argv[2]]();console.log(`PASS DT024 ${process.argv[2]}`);})().catch(e=>{console.error(e);process.exitCode=1;});
