// Actual client behavior at its DOM/network boundary. Run only inside Docker.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Run this test in Docker.');

function client() {
  const nodes = new Map();
  class Node {
    constructor(tag = 'div') {
      this.tagName = tag; this.children = []; this.attributes = {}; this.dataset = {};
      this.value = ''; this.hidden = false; this.textContent = ''; this.handlers = {};
      this.classList = {
        toggle: (name, force) => {
          const names = new Set((this.attributes.class || '').split(' ').filter(Boolean));
          if (force) names.add(name); else names.delete(name);
          this.attributes.class = [...names].join(' ');
        },
      };
    }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key]; }
    removeAttribute(key) { delete this.attributes[key]; }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    append(...items) { this.children.push(...items); }
    replaceChildren(...items) { this.children = items; }
    querySelectorAll(selector) {
      const all = this.children.flatMap(n => [n, ...n.querySelectorAll('*')]);
      return all.filter(n => selector === '*' || n.tagName === selector
        || (selector.startsWith('.') && (n.attributes.class || '').split(' ').includes(selector.slice(1))));
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    focus() { document.activeElement = this; }
    scrollIntoView() {}
    remove() {}
  }
  const document = {
    createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag),
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, new Node());
      return nodes.get(selector);
    },
    querySelectorAll: () => [],
  };
  const context = vm.createContext({document, console, fetch: () => new Promise(() => {}), CSS: {escape: value => value}});
  vm.runInContext(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js', 'utf8'), context);
  const run = code => vm.runInContext(code, context);
  run(`
    facilitiesById = new Map([['AQ',{facility_id:'AQ',code:'AQ',name:'Academic Quadrangle'}]]);
    allLevels = [
      {level_id:'L1',facility_id:'AQ',short_name:'1000',vertical_order:-2},
      {level_id:'L2',facility_id:'AQ',short_name:'2000',vertical_order:-1},
    ];
    initializeFloorControls(allLevels);
    facilitySelect.value='AQ'; levelSelect.value='-2';
  `);
  const fixture = {
    status: 200, profile: 'default', origin: {unit_id: 'A'}, destination: {unit_id: 'B'}, network_distance_m: 12345,
    guidance: {
      version: 'dt018-guidance-v1', status: 'available', warnings: [], distance_m: 12,
      visits: [
        {visit_id: 'v0', level_id: 'L1', label: 'AQ 1000', step_ids: ['s0','s1','s2']},
        {visit_id: 'v1', level_id: 'L2', label: 'AQ 2000', step_ids: ['s3','s4']},
        {visit_id: 'v2', level_id: 'L1', label: 'AQ 1000', step_ids: ['s5']},
      ],
      steps: [
        {step_id:'s0',kind:'depart',instruction:'Start near AQ1003.',level_id:'L1',visit_id:'v0',geometry_ids:[],marker_ids:['a']},
        {step_id:'s1',kind:'walk',instruction:'Turn left, then continue for about 5 m.',level_id:'L1',visit_id:'v0',geometry_ids:['g1','g2'],marker_ids:[]},
        {step_id:'s2',kind:'transition',instruction:'Take the stairs up to AQ 2000.',level_id:'L1',visit_id:'v0',geometry_ids:[],marker_ids:['td'],transition_id:'t',phase:'departure'},
        {step_id:'s3',kind:'transition',instruction:'On AQ 2000, follow the highlighted route.',level_id:'L2',visit_id:'v1',geometry_ids:[],marker_ids:['ta'],transition_id:'t',phase:'arrival'},
        {step_id:'s4',kind:'walk',instruction:'Continue for about 5 m.',level_id:'L2',visit_id:'v1',geometry_ids:['g3'],marker_ids:[]},
        {step_id:'s5',kind:'arrive',instruction:'The mapped route ends near AQ1004.',level_id:'L1',visit_id:'v2',geometry_ids:[],marker_ids:['b']},
      ],
      geometries: [
        {geometry_id:'g0',level_id:'L1',geometry:{type:'LineString',coordinates:[[0,0],[1,0]]}},
        {geometry_id:'g1',level_id:'L1',geometry:{type:'LineString',coordinates:[[1,0],[1,2]]}},
        {geometry_id:'g2',level_id:'L1',geometry:{type:'LineString',coordinates:[[1,2],[1,5]]}},
        {geometry_id:'g3',level_id:'L2',geometry:{type:'LineString',coordinates:[[1,5],[6,5]]}},
      ],
      markers: [
        {marker_id:'a',level_id:'L1',coordinates:[0,0],kind:'origin',label:'Start near AQ1003'},
        {marker_id:'b',level_id:'L1',coordinates:[0,0],kind:'destination',label:'Mapped route ends near AQ1004'},
        {marker_id:'td',level_id:'L1',coordinates:[1,5],kind:'stairs',label:'Stairs to AQ 2000'},
        {marker_id:'ta',level_id:'L2',coordinates:[1,5],kind:'stairs',label:'Stairs from AQ 1000'},
      ],
      transitions: [{transition_id:'t',mode:'stairs',from_level_id:'L1',to_level_id:'L2',from_label:'AQ 1000',to_label:'AQ 2000',from_visit_id:'v0',to_visit_id:'v1',departure_marker_id:'td',arrival_marker_id:'ta'}],
    },
  };
  context.fixture = fixture;
  run(`routeUnits=[{unit_id:'A',room_id:'AQ1003'},{unit_id:'B',room_id:'AQ1004'}];
    currentScene={level:{level_id:'L1',geometry:{type:'LineString',coordinates:[[0,0],[20,20]]}}};
    floorMap.setAttribute('viewBox','-4 -24 28 28');
    request=async path=>({level:{level_id:path.includes('L2')?'L2':'L1',geometry:{type:'LineString',coordinates:[[0,0],[20,20]]}},units:[],details:[],landmarks:[]});`);
  return {run, context, nodes};
}

(async () => {
  const failures = [];
  async function check(name, task) {
    try { await task(); console.log(`PASS ${name}`); }
    catch (error) { failures.push(`${name}: ${error.stack}`); }
  }
  await check('new route and point-only steps show the complete current-floor route', async () => {
    const c = client();
    c.run("fixture.guidance.geometries[2].geometry.coordinates=[[1,2],[200,5]];renderRoute(fixture)");
    const svg = c.nodes.get('#floor-map');
    const initial = svg.attributes.viewBox;
    const box = initial.split(' ').map(Number);
    assert.ok(box[0] <= 0 && box[0]+box[2] >= 200 && box[1] <= -5 && box[1]+box[3] >= 0);
    assert.equal(c.run('guidanceStep().step_id'), 's0');
    await c.run("selectGuidanceStep('s2')");
    assert.equal(svg.attributes.viewBox, initial);
    assert.equal(c.run('guidanceStep().step_id'), 's2');
  });
  await check('long mobile route fits marker circles with a visible screen margin', async () => {
    const c = client();
    const svg = c.nodes.get('#floor-map'); svg.clientWidth=296; svg.clientHeight=260;
    c.run("fixture.guidance.geometries[2].geometry.coordinates=[[1,2],[1000,5]];fixture.guidance.markers[2].coordinates=[1000,5];renderRoute(fixture)");
    const [x,y,width,height] = svg.attributes.viewBox.split(' ').map(Number);
    const scale = Math.min(svg.clientWidth/width, svg.clientHeight/height);
    const letterboxX = (svg.clientWidth-width*scale)/2;
    const letterboxY = (svg.clientHeight-height*scale)/2;
    for (const [px,py] of [[0,0],[1000,-5]]) {
      const screenX = letterboxX+(px-x)*scale, screenY=letterboxY+(py-y)*scale;
      assert.ok(screenX>=14 && screenX<=svg.clientWidth-14, '11px circle and stroke need margin at either end');
      assert.ok(screenY>=14 && screenY<=svg.clientHeight-14);
    }
  });
  await check('coincident route markers use whole-floor context for same-anchor and express landings', async () => {
    const c = client();
    c.run("fixture.guidance.geometries=[];fixture.guidance.markers.forEach(m=>m.coordinates=[0,0]);renderRoute(fixture)");
    const svg = c.nodes.get('#floor-map');
    assert.equal(svg.attributes.viewBox, '-4 -24 28 28');
    assert.ok(c.nodes.get('#route-overlay').querySelectorAll('.route-marker').length);
    await c.run("selectGuidanceStep('s3')");
    assert.equal(svg.attributes.viewBox, '-4 -24 28 28');
    assert.equal(c.run('guidanceStep().step_id'), 's3');
  });
  await check('zoom buttons change camera only and route reset restores exact frame', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    const svg = c.nodes.get('#floor-map');
    const initial = svg.attributes.viewBox;
    const geometry = c.run('JSON.stringify(fixture.guidance.geometries)');
    c.nodes.get('#zoom-out').handlers.click();
    const before = initial.split(' ').map(Number), after = svg.attributes.viewBox.split(' ').map(Number);
    assert.equal(after[2], before[2]*1.5);
    assert.equal(after[0]+after[2]/2, before[0]+before[2]/2);
    assert.equal(after[1]+after[3]/2, before[1]+before[3]/2);
    assert.equal(svg.dataset.cameraMode, 'manual');
    assert.equal(c.run('guidanceStep().step_id'), 's0');
    assert.equal(c.run('JSON.stringify(fixture.guidance.geometries)'), geometry);
    c.nodes.get('#zoom-in').handlers.click();
    assert.equal(svg.attributes.viewBox, initial);
    c.nodes.get('#zoom-out').handlers.click();
    c.nodes.get('#fit-route').handlers.click();
    assert.equal(svg.attributes.viewBox, initial);
    assert.equal(svg.dataset.cameraMode, 'route');
  });
  await check('manual camera survives same-floor redraw and resets on different scene origin', async () => {
    const c = client(); c.run('renderRoute(fixture);zoomMap(1.5)');
    const svg = c.nodes.get('#floor-map'), manual = svg.attributes.viewBox;
    await c.run("selectLevel('L1')");
    assert.equal(svg.attributes.viewBox, manual);
    c.run('renderScene({...currentScene,units:[],details:[],landmarks:[]})');
    assert.equal(svg.attributes.viewBox, manual);
    c.run("renderScene({level:{level_id:'L2',geometry:{type:'LineString',coordinates:[[100,200],[120,220]]}},units:[],details:[],landmarks:[]})");
    assert.equal(svg.dataset.cameraMode, 'route');
    assert.equal(svg.attributes.viewBox, '-103 191 13 8');
  });
  await check('repeated zoom stays finite and bounded, including after reset', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    for (const factor of [1.5, 1/1.5]) {
      c.run(`for(let i=0;i<150;i++) zoomMap(${factor})`);
      const values = c.nodes.get('#floor-map').attributes.viewBox.split(' ').map(Number);
      assert.ok(values.every(Number.isFinite));
      assert.ok(Math.max(values[2],values[3])>=2 && Math.max(values[2],values[3])<=10000);
      assert.ok(values[2]>0 && values[3]>0);
    }
    c.nodes.get('#fit-floor').handlers.click();
    assert.equal(c.nodes.get('#floor-map').attributes.viewBox, '-4 -24 28 28');
  });
  await check('floor names expose source labels without order jargon', async () => {
    const c = client();
    assert.deepEqual(c.nodes.get('#level-select').children.map(n => n.textContent), ['AQ 1000','AQ 2000']);
  });
  await check('clear invalidates pending floor response', async () => {
    const c = client();
    c.run(`globalThis.scenes=[]; activeLevel=()=>({level_id:'L1'});
      renderRouteOverlay=()=>{}; updateEndpointStates=()=>{};
      renderScene=body=>scenes.push(body); request=()=>new Promise(resolve=>globalThis.finishScene=resolve);`);
    const pending = c.run('loadScene()');
    c.run('clearRoute()'); c.context.finishScene({level: {level_id:'L1'}}); await pending;
    assert.equal(c.context.scenes.length, 0, 'a cleared route must not restore a requested route scene');
  });
  await check('walking selection paints exact spans and retains base route', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    await c.run("selectGuidanceStep('s1')");
    const overlay = c.nodes.get('#route-overlay');
    assert.deepEqual(overlay.querySelectorAll('.route-selected').map(n => n.attributes.d), ['M1 0 L1 -2','M1 -2 L1 -5']);
    assert.deepEqual(overlay.querySelectorAll('.route-selected').map(n => n.dataset.geometryId), ['g1','g2']);
    assert.equal(overlay.querySelectorAll('.route-segment').length, 3);
    assert.equal(overlay.querySelectorAll('.route-halo').length, 2);
    const paintOrder=overlay.children.map(n=>n.attributes.class);
    assert.ok(paintOrder.lastIndexOf('route-halo') < paintOrder.indexOf('route-selected'), 'all halos must paint below every selected span');
    assert.equal(overlay.querySelectorAll('.route-marker').at(-1).dataset.markerId, 'step-s1', 'selected step number must remain above unselected endpoint markers');
    assert.equal(c.nodes.get('#step-position').textContent, 'Step 2 of 6 · AQ 1000');
    const selected = c.nodes.get('#route-steps').querySelectorAll('button').filter(n => n.attributes['aria-current'] === 'step');
    assert.equal(selected.length, 1); assert.equal(selected[0].dataset.stepId, 's1');
  });
  await check('transition phase switches floor and exact endpoint without projected transition paths', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    await c.run("selectGuidanceStep('s2')");
    await c.nodes.get('#transition-arrival').handlers.click();
    assert.equal(c.nodes.get('#viewing-floor').dataset.levelId, 'L2');
    assert.equal(c.run('guidanceStep().step_id'), 's3');
    const selected = c.nodes.get('#route-overlay').querySelectorAll('.route-marker').filter(n => n.attributes.class.includes('selected'));
    assert.deepEqual(selected.map(n => n.dataset.markerId), ['ta']);
    assert.equal(selected[0].attributes.transform, 'translate(1 -5)');
    assert.equal(selected[0].querySelector('text').textContent, '3', 'both transition endpoints use departure step number');
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-selected').length, 0);
  });
  await check('repeated floor visits stay ordered and preview preserves selected step', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    assert.deepEqual(c.nodes.get('#floor-journey').querySelectorAll('button').map(n => n.dataset.visitId), ['v0','v1','v2']);
    await c.run("selectGuidanceStep('s1')");
    await c.run("previewFloor('L1','v2')");
    assert.equal(c.run('guidanceStep().step_id'), 's1');
    assert.equal(c.nodes.get('#floor-preview').hidden, false);
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-selected').length, 0);
    await c.nodes.get('#show-selected-step').handlers.click();
    assert.equal(c.nodes.get('#floor-preview').hidden, true);
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-selected').length, 2);
  });
  await check('previous next and endpoint selection preserve matching numbered cues', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    let selected = c.nodes.get('#route-overlay').querySelectorAll('.route-marker').filter(n => n.attributes.class.includes('selected'));
    assert.deepEqual(selected.map(n => n.dataset.markerId), ['a']);
    assert.equal(c.nodes.get('#step-previous').disabled, true);
    await c.nodes.get('#step-next').handlers.click();
    assert.equal(c.run('guidanceStep().step_id'), 's1');
    await c.nodes.get('#step-previous').handlers.click();
    assert.equal(c.run('guidanceStep().step_id'), 's0');
    const markers = c.nodes.get('#route-overlay').querySelectorAll('.route-marker');
    assert.equal(markers.at(-1).dataset.markerId, 'a', 'overlapping inactive endpoint must not cover selected endpoint');
  });
  await check('limited guidance cannot resurrect legacy numeric distance', async () => {
    const c = client();
    c.run("fixture.guidance.status='limited';fixture.guidance.distance_m=null;fixture.guidance.warnings=['Geometry needs review.'];renderRoute(fixture)");
    assert.doesNotMatch(c.nodes.get('#route-status').textContent, /12345|About/);
    assert.match(c.nodes.get('#route-status').textContent, /geometry needs review/i);
  });
  await check('clear and replacement remove all selected content', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    await c.run("selectGuidanceStep('s1')"); c.run('clearRoute()');
    assert.equal(c.nodes.get('#route-overlay').children.length, 0);
    assert.equal(c.nodes.get('#floor-journey').children.length, 0);
    assert.equal(c.nodes.get('#route-steps').children.length, 0);
    assert.equal(c.nodes.get('#step-next').disabled, true);
    assert.equal(c.nodes.get('#route-status').attributes['data-state'], 'empty');
  });
  await check('rapid step changes remove the old highlight while loading and settle on latest scene', async () => {
    const c = client(); c.run('renderRoute(fixture)'); await c.run("selectGuidanceStep('s1')");
    c.run('globalThis.pendingScenes=[]; request=path=>new Promise(resolve=>pendingScenes.push({path,resolve}));');
    const slow = c.run("selectGuidanceStep('s4')");
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-selected').length, 0, 'old step highlight must disappear immediately');
    await c.run("selectGuidanceStep('s1')");
    c.context.pendingScenes[0].resolve({level:{level_id:'L2',geometry:{type:'LineString',coordinates:[[0,0],[20,20]]}},units:[],details:[],landmarks:[]});
    await slow;
    assert.equal(c.run('currentScene.level.level_id'), 'L1');
    assert.equal(c.run('guidanceStep().step_id'), 's1');
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-selected').length, 2);
    assert.doesNotMatch(c.nodes.get('#map-status').textContent, /Loading/);
    assert.match(c.nodes.get('#map-status').textContent, /AQ 1000/);
  });
  await check('clear during floor loading restores visible floor controls status and full extent', async () => {
    const c = client(); c.run('renderRoute(fixture)'); await c.run("selectGuidanceStep('s1')");
    c.run('globalThis.pendingScenes=[]; request=path=>new Promise(resolve=>pendingScenes.push({path,resolve}));');
    const pending = c.run("selectGuidanceStep('s4')");
    c.run('clearRoute()');
    assert.equal(c.nodes.get('#level-select').value, '-2');
    assert.equal(c.nodes.get('#facility-select').value, 'AQ');
    assert.equal(c.nodes.get('#viewing-floor').dataset.levelId, 'L1');
    assert.match(c.nodes.get('#map-status').textContent, /AQ 1000/);
    assert.doesNotMatch(c.nodes.get('#map-status').textContent, /Loading/);
    assert.equal(c.nodes.get('#floor-map').attributes.viewBox, '-4 -24 28 28');
    c.context.pendingScenes[0].resolve({level:{level_id:'L2',geometry:{type:'LineString',coordinates:[[0,0],[20,20]]}},units:[],details:[],landmarks:[]});
    await pending;
    assert.equal(c.run('currentScene.level.level_id'), 'L1');
    assert.equal(c.nodes.get('#route-overlay').children.length, 0);
  });
  await check('unknown-floor step cancels pending floor and restores actual map context', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    c.run("fixture.guidance.steps[5].level_id=null;globalThis.pendingScenes=[];request=path=>new Promise(resolve=>pendingScenes.push({path,resolve}));");
    const pending = c.run("selectGuidanceStep('s4')");
    await c.run("selectGuidanceStep('s5')");
    assert.equal(c.nodes.get('#level-select').value, '-2');
    assert.equal(c.nodes.get('#viewing-floor').dataset.levelId, 'L1');
    assert.doesNotMatch(c.nodes.get('#map-status').textContent, /Loading/);
    assert.match(c.nodes.get('#step-position').textContent, /Floor not recorded/);
    c.context.pendingScenes[0].resolve({level:{level_id:'L2',geometry:{type:'LineString',coordinates:[[0,0],[20,20]]}},units:[],details:[],landmarks:[]});
    await pending;
    assert.equal(c.run('currentScene.level.level_id'), 'L1');
    assert.equal(c.run('guidanceStep().step_id'), 's5');
  });
  await check('scene failure restores actual floor and retains a useful load error', async () => {
    const c = client(); c.run('renderRoute(fixture)');
    c.run("request=async()=>{throw new Error('Scene unavailable');};");
    await c.run("selectGuidanceStep('s4')");
    assert.equal(c.nodes.get('#level-select').value, '-2');
    assert.equal(c.nodes.get('#viewing-floor').dataset.levelId, 'L1');
    assert.match(c.nodes.get('#map-status').textContent, /Scene unavailable/);
    assert.match(c.nodes.get('#map-status').textContent, /AQ 2000/);
    assert.doesNotMatch(c.nodes.get('#map-status').textContent, /Loading/);
    assert.equal(c.run('guidanceStep().step_id'), 's4');
    assert.equal(c.nodes.get('#floor-preview').hidden, false);
  });
  await check('route decorations cannot intercept room activation', async () => {
    const c = client(); c.run('renderRoute(fixture)'); await c.run("selectGuidanceStep('s1')");
    const markers = c.nodes.get('#route-overlay').querySelectorAll('.route-marker');
    assert.ok(markers.length);
    assert.ok(markers.every(n => n.attributes['pointer-events'] === 'none'));
    assert.equal(c.nodes.get('#route-overlay').querySelectorAll('.route-direction')[0].attributes['pointer-events'], 'none');
  });
  await check('native projected coordinates round trip through a shared small scene origin', async () => {
    const c = client();
    c.run(`
      const ox=506192.4151,oy=5458478.3907;
      fixture.guidance.geometries.forEach(g=>g.geometry.coordinates.forEach(p=>{p[0]+=ox;p[1]+=oy;}));
      fixture.guidance.markers.forEach(m=>{m.coordinates[0]+=ox;m.coordinates[1]+=oy;});
      renderScene({level:{level_id:'L1',geometry:{type:'LineString',coordinates:[[ox,oy],[ox+20,oy+20]]}},units:[],details:[],landmarks:[]});
      renderRoute(fixture);
    `);
    await c.run("selectGuidanceStep('s1')");
    const svg = c.nodes.get('#floor-map');
    assert.equal(Number(svg.dataset.originX), 506192.4151);
    assert.equal(Number(svg.dataset.originY), 5458478.3907);
    const paths = c.nodes.get('#route-overlay').querySelectorAll('.route-selected');
    const native = c.context.fixture.guidance.geometries.filter(g=>['g1','g2'].includes(g.geometry_id));
    paths.forEach((path,index)=>{
      const values=path.attributes.d.match(/[-+]?\d*\.?\d+(?:e[-+]?\d+)?/ig).map(Number);
      assert.ok(values.every(v=>Math.abs(v)<100));
      for(let i=0;i<values.length;i+=2){
        assert.equal(values[i]+Number(svg.dataset.originX),native[index].geometry.coordinates[i/2][0]);
        assert.equal(Number(svg.dataset.originY)-values[i+1],native[index].geometry.coordinates[i/2][1]);
      }
    });
    const marker=c.nodes.get('#route-overlay').querySelectorAll('.route-marker').find(n=>n.dataset.markerId==='step-s1');
    assert.equal(marker.attributes.transform,'translate(1 0)');
    assert.equal(Number(marker.dataset.x),506193.4151);
    assert.ok(svg.attributes.viewBox.split(' ').map(Number).every(v=>Math.abs(v)<100));
  });
  assert.deepEqual(failures, []);
})().catch(error => { console.error(error); process.exitCode = 1; });
