const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Docker required');
const nodes = new Map();
class Node {
  constructor(tagName='div') { this.tagName=tagName;this.value='';this.dataset={};this.attributes={};this.children=[];this.handlers={};this.classList={toggle(){}}; }
  addEventListener(k,v){this.handlers[k]=v;}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k];}
  removeAttribute(k){delete this.attributes[k];}
  append(...v){this.children.push(...v);}
  replaceChildren(...v){this.children=v;if(this.tagName==='select')this.value=v[0]?.value||'';}
  querySelectorAll(selector){
    const found=[];
    const visit=(node)=>{ for (const child of node.children) {
      const matches = selector.startsWith('.') ? child.attributes.class?.split(' ').includes(selector.slice(1))
        : selector === child.tagName?.toLowerCase();
      if (matches) found.push(child);
      visit(child);
    }};
    visit(this); return found;
  }
}
const document={querySelector(s){if(!nodes.has(s))nodes.set(s,new Node(s.startsWith('#')&&s.includes('select')?'select':'div'));return nodes.get(s);},querySelectorAll(){return [];},createElement(name){return new Node(name);},createElementNS(_ns,name){return new Node(name);}};
const context=vm.createContext({document,console,fetch:()=>new Promise(()=>{})});
const run=s=>vm.runInContext(s,context);
run(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js','utf8'));
run(`campusData={bounds:[500000,5400000,500300,5400200],facilities:[
 {facility_id:'AQ',code:'AQ',name:'Academic Quadrangle',geometry_status:'available',bounds:[500000,5400000,500100,5400100],geometry:{type:'Polygon',coordinates:[[[500000,5400000],[500100,5400000],[500100,5400100],[500000,5400000]]]},levels:[{level_id:'AQ0',short_name:'1',vertical_order:0,facility_id:'AQ'},{level_id:'AQ2',short_name:'3',vertical_order:2,facility_id:'AQ'},{level_id:'AQ5',short_name:'5',vertical_order:5,facility_id:'AQ'}]},
 {facility_id:'ECC',code:'ECC',name:'Education Centre',geometry:null,levels:[{level_id:'ECC0',short_name:'G',vertical_order:0,facility_id:'ECC'},{level_id:'ECC2',short_name:'2',vertical_order:2,facility_id:'ECC'}]},
 {facility_id:'LIB',code:'LIB',name:'Library',geometry:null,levels:[{level_id:'LIB7',short_name:'7',vertical_order:7,facility_id:'LIB'},{level_id:'LIB8',short_name:'8',vertical_order:8,facility_id:'LIB'}]},
 {facility_id:'SH',code:'SH',name:'Strand Hall',geometry:null,levels:[],coverage:'overview_only'}]};
facilitiesById = new Map(campusData.facilities.map(item => [item.facility_id, item]));
initializeFloorControls(campusData.facilities.flatMap(item => item.levels));
levelSelect.value='2'; updateFacilities(); facilitySelect.value='AQ';
activeRoute={fixture:'retained'};routeOrigin.value='roomA';routeDestination.value='roomB';
routeProfile.value='elevator_only';
renderCampus();showCampus();`);
assert.equal(nodes.get('#campus-view').hidden,false);
assert.equal(nodes.get('#floor-view').hidden,true);
run('zoomCampus(0.5)');
const zoomed=nodes.get('#campus-map').getAttribute('viewBox');
run("campusSearch.value='strand';renderCampusBuildings()");
assert.equal(nodes.get('#campus-buildings').children.length,1);
assert.equal(nodes.get('#campus-buildings').children[0].dataset.campusFacilityId,'SH');
assert.equal(nodes.get('#campus-map').getAttribute('viewBox'),zoomed);
const footprint=nodes.get('#campus-map').children[0].children[0];
footprint.handlers.keydown({key:'Enter',preventDefault(){}});
assert.equal(nodes.get('#facility-select').value,'AQ');
// A campus list activation must synchronize both controls without loading a scene.
run("selectCampusBuilding('SH')");
assert.match(nodes.get('#campus-details').children.map(n=>n.textContent||'').join(' '),/No indoor floors/);
assert.equal(nodes.get('#facility-select').value,'SH');
assert.equal(nodes.get('#level-select').value,'');
assert.equal(nodes.get('#level-select').disabled,true);
assert.equal(run('activeRoute.fixture'),'retained');
assert.equal(run('routeOrigin.value'),'roomA');
assert.equal(run('routeDestination.value'),'roomB');
assert.equal(run('routeProfile.value'),'elevator_only');
// Shared global vertical order is retained when the destination building has it.
run("selectCampusBuilding('AQ'); levelSelect.value='2'; facilitySelect.value='AQ'; selectCampusBuilding('ECC')");
assert.equal(nodes.get('#facility-select').value,'ECC');
assert.equal(nodes.get('#level-select').value,'2');
assert.equal(nodes.get('#level-select').disabled,false);
// An AQ-only order falls back to recorded order 0 in ECC, then to first deterministic level.
run("selectCampusBuilding('AQ'); levelSelect.value='5'; facilitySelect.value='AQ'; selectCampusBuilding('ECC')");
assert.equal(nodes.get('#facility-select').value,'ECC');
assert.equal(nodes.get('#level-select').value,'0');
run("selectCampusBuilding('AQ'); levelSelect.value='5'; facilitySelect.value='AQ'; selectCampusBuilding('LIB')");
assert.equal(nodes.get('#facility-select').value,'LIB');
assert.equal(nodes.get('#level-select').value,'7');
run("selectCampusBuilding('SH');selectCampusBuilding('LIB')");
assert.equal(nodes.get('#level-select').value,'7','no-level selection has no retained global order');
// The rendered search/list control follows the same path as a footprint click.
run("campusSearch.value='ecc';renderCampusBuildings()");
nodes.get('#campus-buildings').children[0].handlers.click();
assert.equal(nodes.get('#facility-select').value,'ECC');
run('showCampus();resetCampusCamera()');
const box=nodes.get('#campus-map').getAttribute('viewBox').split(' ').map(Number);
assert.ok(box.every(Number.isFinite)&&box[2]>=300&&box[3]>=200);
(async()=>{
 run(`currentScene={level:{level_id:'AQ0'},units:[]};fitMap=()=>{};
   refreshRouteOptions=()=>{};updateGuidanceControls=()=>{};renderRouteOverlay=()=>{};
   selectCampusBuilding('ECC');clearRoute(false);`);
 assert.equal(nodes.get('#facility-select').value,'ECC','Clear must retain the inspected building');
 assert.equal(nodes.get('#map-context').textContent,'Building');
 run("selectCampusBuilding('SH');restoreRenderedFloor()");
 assert.equal(nodes.get('#facility-select').value,'SH','hidden floor cleanup retains overview-only selection');
 assert.equal(nodes.get('#level-select').disabled,true);
 run("globalThis.pendingScene=null;request=()=>new Promise(resolve=>pendingScene=resolve);globalThis.rendered=0;renderScene=()=>rendered++");
 run("selectCampusBuilding('AQ')");
 const pending=run('loadScene()');
 run("selectCampusBuilding('LIB');selectCampusBuilding('AQ');selectCampusBuilding('ECC');pendingScene({level:{level_id:'AQ0'}})");
 await pending;
 assert.equal(run('rendered'),0,'late scene must not paint over campus');
 assert.equal(nodes.get('#campus-view').hidden,false);
 assert.equal(nodes.get('#facility-select').value,'ECC','late scene must not restore an older building');
 assert.equal(nodes.get('#level-select').value,'0','late scene must not restore an older floor');
 run("selectCampusBuilding('SH');request=async()=>({level:{level_id:'AQ0'},units:[]});renderScene=()=>{};");
 await run("selectLevel('AQ0')");
 assert.equal(nodes.get('#facility-select').value,'AQ');
 assert.equal(nodes.get('#level-select').value,'0');
 assert.equal(nodes.get('#level-select').disabled,false,'explicit floor navigation restores Floor control');
 assert.ok(nodes.get('#level-select').children.some(n=>n.value==='5'),'normal global floor options restored');
 run("levelSelect.value='5';restoreRenderedFloor()");
 assert.equal(nodes.get('#level-select').value,'0','visible Floor failure cleanup restores rendered floor');
 run(`selectCampusBuilding('ECC');
   globalThis.pendingRoute=null;globalThis.routeRendered=0;
   request=()=>new Promise(resolve=>pendingRoute=resolve);renderRoute=()=>routeRendered++`);
 await run("requestRoute('roomA','','default',++requestGeneration)");
 assert.equal(nodes.get('#campus-view').hidden,false,'incomplete endpoints must not show a blank floor');
 const route=run("requestRoute('roomA','roomB','default',++requestGeneration)");
 assert.equal(nodes.get('#campus-view').hidden,false,'wait for actual route floor before leaving campus');
 assert.equal(run('routeUiState'),'pending');
 assert.equal(nodes.get('#facility-select').value,'ECC','pending route must not restore hidden AQ controls');
 run("selectCampusBuilding('AQ');selectCampusBuilding('LIB');selectCampusBuilding('ECC');pendingRoute({status:200})");
 await route;
 assert.equal(run('routeUiState'),'empty','cancelled route must not leave pending UI');
 assert.equal(run('routeRendered'),0,'late route must not return to floor context');
 assert.equal(nodes.get('#campus-view').hidden,false);
 assert.equal(nodes.get('#facility-select').value,'ECC');
 assert.equal(nodes.get('#level-select').value,'0');
 assert.equal(nodes.get('#map-context').textContent,'Building');
 assert.equal(run('routeOrigin.value'),'roomA');
 assert.equal(run('routeDestination.value'),'roomB');
 assert.equal(run('routeProfile.value'),'elevator_only');
 console.log('PASS campus search, camera, no-level coverage, retained route and stale scene/route');
})().catch(error=>{console.error(error);process.exitCode=1;});
