// Execute the actual client with a small DOM boundary; browser layout remains a separate gate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
assert.ok(fs.existsSync('/.dockerenv'), 'Run through Docker.');

function routeResponse({origin, destination, profile}) {
  return {
    status: 200, profile, origin, destination,
    guidance: {version: 'dt018-guidance-v1', status: 'unavailable', distance_m: null,
      warnings: [], steps: [], geometries: [], markers: [], visits: [], transitions: []},
  };
}

function client() {
  const nodes = new Map();
  const context = vm.createContext({
    ...require('../client/browser-timers.cjs'),
    console,
    fetch: () => new Promise(() => {}), // Leave bootstrap pending; isolate route interactions.
    document: {
      querySelector(selector) {
        if (!nodes.has(selector)) nodes.set(selector, {
          value: '', hidden: false, textContent: '', handlers: {},
          dataset: {}, attributes: {}, children: [],
          addEventListener(name, callback) { this.handlers[name] = callback; },
          replaceChildren(...children) { this.children = children; },
          append(...children) { this.children.push(...children); },
          setAttribute(key, value) { this.attributes[key] = String(value); },
          removeAttribute(key) { delete this.attributes[key]; },
          querySelectorAll() { return []; },
        });
        return nodes.get(selector);
      },
      querySelectorAll: () => [],
      createElement: () => ({value: '', textContent: '', dataset: {}, attributes: {}, handlers: {},
        setAttribute(key, value) { this.attributes[key] = String(value); },
        addEventListener(name, callback) { this.handlers[name] = callback; },
      }),
    },
  });
  vm.runInContext(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js', 'utf8'), context);
  vm.runInContext(`
    renderRouteOverlay = () => {};
    updateEndpointStates = () => {};
    globalThis.requests = [];
    globalThis.rendered = [];
    globalThis.renderOptions = [];
    request = (path, options) => new Promise(resolve => requests.push({
      payload: JSON.parse(options.body), resolve,
    }));
    renderRoute = (body, options) => { rendered.push(body); renderOptions.push(options); };
    editRouteDraft({origin: 'A', destination: 'B'});
  `, context);
  return {context, nodes, run: code => vm.runInContext(code, context)};
}

(async () => {
  const first = client();
  const pending = first.run('submitSelectedRoute()');
  first.nodes.get('#route-profile').value = 'elevator_only';
  first.nodes.get('#route-profile').handlers.change();
  assert.equal(first.context.requests.length, 1, 'profile edit must not submit a replacement');
  const changed = first.run('submitSelectedRoute()');
  assert.equal(first.context.requests.length, 2, 'explicit Preview submits the edited profile');
  assert.equal(first.context.requests[1].payload.profile, 'elevator_only');
  first.context.requests[1].resolve(routeResponse(first.context.requests[1].payload));
  await changed;
  first.context.requests[0].resolve(routeResponse(first.context.requests[0].payload));
  await pending;
  assert.deepEqual(Array.from(first.context.rendered, value => value.profile), ['elevator_only']);

  const second = client();
  second.run(`
    editRouteDraft({destination: ''});
    selectUnit = () => new Promise(resolve => { globalThis.inspected = resolve; });
  `);
  const selection = second.run("activateRouteEndpoint('B')");
  second.run('clearRoute()');
  second.context.inspected();
  await selection;
  assert.equal(second.context.requests.length, 0, 'clear during room inspection must cancel routing');
  const failures = [];
  async function check(name, test) {
    try { await test(); } catch (error) { failures.push(`${name}: ${error.message}`); }
  }
  await check('manual incomplete pair retains origin', async () => {
    const manual = client();
    manual.run("editRouteDraft({destination: ''}); selectUnit = async () => true;");
    await manual.run('submitSelectedRoute()');
    await manual.run("activateRouteEndpoint('C')");
    assert.equal(manual.run('routeDestination.value'), '', 'inspection alone cannot fill To');
    await manual.run("activateRouteDestination('C')");
    assert.equal(manual.run('routeOrigin.value'), 'A');
    assert.equal(manual.run('routeDestination.value'), 'C');
    assert.equal(manual.context.requests.length, 0);
    const selected = manual.run('submitSelectedRoute()');
    assert.equal(manual.context.requests.length, 1);
    manual.context.requests[0].resolve(routeResponse(manual.context.requests[0].payload));
    await selected;
  });
  await check('same-room mobility draft preserves the previous route', async () => {
    const chat = client();
    chat.run(`activeRoute = {status: 200, profile: 'default'};
      committedRouteSnapshot = {origin:'A',destination:'B',profile:'default'};
      routeUnits = [{unit_id:'A',room_id:'AQ1001'}, {unit_id:'B',room_id:'AQ1002'}];
      refreshRouteOptions = () => {};`);
    chat.nodes.get('#assistant-input').value = 'wheelchair directions from A to A';
    await chat.nodes.get('#assistant-form').handlers.submit({preventDefault() {}});
    await chat.run('submitSelectedRoute()');
    assert.equal(chat.run('activeRoute.profile'), 'default');
    assert.equal(chat.nodes.get('#route-accessibility').hidden, true);
    assert.equal(chat.nodes.get('#route-profile-help').hidden, false);
    assert.match(chat.nodes.get('#route-request-status').textContent, /distinct/i);
    assert.equal(chat.context.requests.length, 0);
  });
  await check('assistant-confirmed route preserves the previous route while pending', async () => {
    const chat = client();
    chat.run(`activeRoute = {status: 200, profile: 'default'};
      committedRouteSnapshot = {origin:'A',destination:'B',profile:'default'};
      routeUnits = [{unit_id:'A',room_id:'AQ1001'}, {unit_id:'B',room_id:'AQ1002'}];
      refreshRouteOptions = () => {};`);
    chat.nodes.get('#assistant-input').value = 'wheelchair directions from A to B';
    await chat.nodes.get('#assistant-form').handlers.submit({preventDefault() {}});
    assert.equal(chat.context.requests.length, 0);
    const pendingChat = chat.run('submitSelectedRoute()');
    assert.equal(chat.run('activeRoute.profile'), 'default');
    assert.equal(chat.nodes.get('#route-request-status').dataset.state, 'pending');
    chat.context.requests[0].resolve(routeResponse(chat.context.requests[0].payload));
    await pendingChat;
    assert.equal(chat.run('committedRouteSnapshot.profile'), 'elevator_only');
  });
  await check('newest floor owns the scene', async () => {
    const scene = client();
    scene.run(`
      globalThis.scenes = [];
      facilitiesById = new Map([['AQ',{facility_id:'AQ',code:'AQ',name:'Academic Quadrangle'}]]);
      initializeFloorControls([
        {level_id:'L1',facility_id:'AQ',short_name:'1000',vertical_order:-2},
        {level_id:'L2',facility_id:'AQ',short_name:'2000',vertical_order:-1},
      ]);
      selectFloorControls(allLevels[0]);
      request = path => new Promise((resolve, reject) => requests.push({path, resolve, reject}));
      renderScene = body => scenes.push(body.level.level_id);
    `);
    const older = scene.run('loadScene()');
    scene.run("selectFloorControls(allLevels[1])");
    const newer = scene.run('loadScene()');
    scene.context.requests[1].resolve({level: {level_id: 'L2'}});
    await newer;
    scene.context.requests[0].resolve({level: {level_id: 'L1'}});
    await older;
    assert.deepEqual(Array.from(scene.context.scenes), ['L2']);
  });
  await check('current route response is accepted without stealing newer campus exploration', async () => {
    const campus = client();
    const route = campus.run('submitSelectedRoute()');
    campus.run('showCampus()');
    campus.context.requests[0].resolve(routeResponse(campus.context.requests[0].payload));
    await route;
    assert.equal(campus.context.rendered.length, 1, 'latest route result remains available');
    assert.equal(campus.context.renderOptions[0].follow, false, 'acceptance cannot navigate over newer campus intent');
    assert.equal(campus.nodes.get('#campus-view').hidden, false);
    assert.equal(campus.nodes.get('#floor-view').hidden, true);
    assert.equal(campus.nodes.get('#route-request-status').dataset.state, 'success');
  });
  assert.deepEqual(failures, []);
  console.log('Route state regressions passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
