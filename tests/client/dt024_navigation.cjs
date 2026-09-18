const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Docker required');
const nodes = new Map();
class Node {
  constructor(tagName='div') { Object.assign(this,{tagName,value:'',dataset:{},attributes:{},children:[],handlers:{},hidden:false,textContent:''});this.classList={toggle(){}}; }
  addEventListener(k,v){this.handlers[k]=v;}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k];}
  removeAttribute(k){delete this.attributes[k];}
  append(...v){this.children.push(...v);v.forEach(n=>n.parent=this);}
  replaceChildren(...v){this.children=[];this.append(...v);if(this.tagName==='select')this.value=v[0]?.value||'';}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
  focus(){this.focused=true;}
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
 request=(path,options)=>{calls.push(path);return new Promise((resolve,reject)=>pending.push({path,resolve,reject}));};
 refreshRouteOptions=()=>{};
 globalThis.scene=id=>({level:{...allLevels.find(x=>x.level_id===id),geometry:{type:'Polygon',coordinates:[[[0,0],[20,0],[20,20],[0,0]]]}},details:[],units:[],landmarks:[]});
`);
const get=id=>document.querySelector(id);
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const resolveScene=async(id)=>{run(`pending.find(x=>x.path.endsWith('/${id}/scene')).resolve(scene('${id}'))`);await tick();};
const text=n=>[n.textContent,...n.children.map(text)].join(' ');
async function open(id){const p=run(`previewFloor('${id}')`);await resolveScene(id);await p;}
const cases={
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
  run("pending.find(x=>x.path.endsWith('/old')).resolve({unit_id:'old',room_id:'OLD'})");await old;
  assert.match(text(get('#unit-details')),/LATEST/,'late room response cannot replace newer room');
  assert.doesNotMatch(text(get('#unit-details')),/OLD/);
  assert.equal(get('[data-unit-id="old"]').focused,undefined,'late room response cannot steal focus');
  const moving=run("selectUnit('moving',true)");await open('AQ2');const status=get('#map-status').textContent;
  run("pending.find(x=>x.path.endsWith('/moving')).resolve({unit_id:'moving',room_id:'MOVING'})");await moving;
  assert.equal(get('#map-status').textContent,status,'room response from another floor cannot overwrite floor status');
 },
 async clear_room(){
  await open('AQ0');const lookup=run("selectUnit('cleared',true)");run('clearRoute()');
  const status=get('#map-status').textContent;const details=text(get('#unit-details'));
  run("pending.find(x=>x.path.endsWith('/cleared')).resolve({unit_id:'cleared',room_id:'CLEARED'})");await lookup;
  assert.equal(get('#map-status').textContent,status,'Clear suppresses pending room status');
  assert.equal(text(get('#unit-details')),details,'Clear suppresses pending room details');
  assert.equal(get('[data-unit-id="cleared"]').focused,undefined);
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
  await open('AQ0');
  run(`renderRoute({status:200,profile:'default',origin:{unit_id:'a'},destination:{unit_id:'b'},levels:[],guidance:{version:'dt018-guidance-v1',status:'available',distance_m:1,warnings:[],transitions:[],geometries:[],markers:[],visits:[{visit_id:'v0',level_id:'AQ0',label:'AQ 1'},{visit_id:'v2',level_id:'AQ2',label:'AQ 3'}],steps:[{step_id:'s0',visit_id:'v0',level_id:'AQ0',instruction:'Start on AQ 1',geometry_ids:[],marker_ids:[]},{step_id:'s2',visit_id:'v2',level_id:'AQ2',instruction:'Finish on AQ 3',geometry_ids:[],marker_ids:[]}]}})`);
  await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0');
  const oldStep=run("selectGuidanceStep('s2')");
  const replacement=run("requestRoute('a','c','default',++requestGeneration)");
  run("pending.find(x=>x.path==='/demo/v1/route').reject(new Error('replacement unavailable'))");await replacement;
  await resolveScene('AQ2');await oldStep;
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ0','obsolete route-owned scene must not render after replacement failure');
  assert.equal(get('#level-select').value,'AQ0','replacement failure controls identify retained scene');
  assert.equal(get('#facility-select').value,'AQ');
  assert.equal(run('navigationState.pendingStep'),null,'replaced route cannot retain a pending instruction');
  assert.equal(get('#floor-map').getAttribute('aria-busy'),'false');
  assert.doesNotMatch(get('#current-instruction').textContent,/Finish on AQ 3/);
 },
 async retained_room_loading(){
  await open('AQ0');const loading=run("previewFloor('AQ2')");
  const status=get('#map-status').textContent;
  const inspection=run("selectUnit('retained',true)");
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
  await open('AQ0');const p=run("requestRoute('a','b','default',++requestGeneration)");await open('AQ2');
  run(`pending.find(x=>x.path==='/demo/v1/route').resolve({status:200,profile:'default',origin:{unit_id:'a'},destination:{unit_id:'b'},levels:[],guidance:{version:'dt018-guidance-v1',status:'available',distance_m:1,warnings:[],transitions:[],geometries:[],markers:[],visits:[{visit_id:'v0',level_id:'AQ0',label:'AQ 1'}],steps:[{step_id:'s0',visit_id:'v0',level_id:'AQ0',instruction:'Start on AQ 1',geometry_ids:[],marker_ids:[]}]}})`);
  await p;await tick();
  run("pending.filter(x=>x.path.endsWith('/AQ0/scene')).at(-1)?.resolve(scene('AQ0'))");await tick();
  assert.equal(get('#viewing-floor').dataset.levelId,'AQ2','late route must not steal newer floor');
  assert.equal(get('#level-select').value,'AQ2','late route must not reset requested floor');
  assert.equal(get('#facility-select').value,'AQ');
 }
};
(async()=>{assert.ok(cases[process.argv[2]],'named case required');await cases[process.argv[2]]();console.log(`PASS DT024 ${process.argv[2]}`);})().catch(e=>{console.error(e);process.exitCode=1;});
