// Execute the actual client with a small DOM boundary; browser layout remains a separate gate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function client() {
  const nodes = new Map();
  const context = vm.createContext({
    console,
    fetch: () => new Promise(() => {}), // Leave bootstrap pending; isolate route interactions.
    document: {
      querySelector(selector) {
        if (!nodes.has(selector)) nodes.set(selector, {
          value: '', hidden: false, textContent: '', handlers: {},
          addEventListener(name, callback) { this.handlers[name] = callback; },
          replaceChildren() {},
        });
        return nodes.get(selector);
      },
      querySelectorAll: () => [],
    },
  });
  vm.runInContext(fs.readFileSync('packages/wayfinding/src/wayfinding/demo/static/app.js', 'utf8'), context);
  vm.runInContext(`
    renderRouteOverlay = () => {};
    activeLevel = () => null;
    updateEndpointStates = () => {};
    globalThis.requests = [];
    globalThis.rendered = [];
    request = (path, options) => new Promise(resolve => requests.push({
      payload: JSON.parse(options.body), resolve,
    }));
    renderRoute = body => rendered.push(body);
    routeOrigin.value = 'A'; routeDestination.value = 'B'; routeProfile.value = 'default';
  `, context);
  return {context, nodes, run: code => vm.runInContext(code, context)};
}

(async () => {
  const first = client();
  const pending = first.run('submitSelectedRoute()');
  first.nodes.get('#route-profile').value = 'elevator_only';
  const changed = first.nodes.get('#route-profile').handlers.change();
  assert.equal(first.context.requests.length, 2, 'profile change must recompute the selected pair');
  assert.equal(first.context.requests[1].payload.profile, 'elevator_only');
  first.context.requests[1].resolve({profile: 'elevator_only'});
  await changed;
  first.context.requests[0].resolve({profile: 'default'});
  await pending;
  assert.deepEqual(Array.from(first.context.rendered, value => value.profile), ['elevator_only']);

  const second = client();
  second.run(`
    routeDestination.value = ''; routeSelection = 'origin_selected';
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
    manual.run(`routeSelection = 'complete'; routeDestination.value = ''; selectUnit = async () => {};`);
    await manual.run('submitSelectedRoute()');
    const selected = manual.run("activateRouteEndpoint('C')");
    await Promise.resolve();
    assert.equal(manual.run('routeOrigin.value'), 'A');
    assert.equal(manual.run('routeDestination.value'), 'C');
    assert.equal(manual.context.requests.length, 1);
    manual.context.requests[0].resolve({status: 200});
    await selected;
  });
  await check('invalid mobility chat clears previous route', async () => {
    const chat = client();
    chat.run(`activeRoute = {status: 200, profile: 'default'}; routeSelection = 'complete';`);
    chat.nodes.get('#assistant-input').value = 'wheelchair directions from A to A';
    await chat.nodes.get('#assistant-form').handlers.submit({preventDefault() {}});
    assert.equal(chat.run('activeRoute'), null);
    assert.equal(chat.nodes.get('#route-accessibility').hidden, false);
    assert.match(chat.nodes.get('#route-status').textContent, /distinct/i);
    assert.equal(chat.context.requests.length, 0);
  });
  await check('valid chat clears previous route while pending', async () => {
    const chat = client();
    chat.run(`activeRoute = {status: 200, profile: 'default'}; routeSelection = 'complete';`);
    chat.nodes.get('#assistant-input').value = 'wheelchair directions from A to B';
    const pendingChat = chat.nodes.get('#assistant-form').handlers.submit({preventDefault() {}});
    assert.equal(chat.run('activeRoute'), null);
    assert.equal(chat.run('routeSelection'), 'request_pending');
    chat.context.requests[0].resolve({status: 200, profile: 'elevator_only'});
    await pendingChat;
  });
  await check('newest floor owns the scene', async () => {
    const scene = client();
    scene.run(`
      globalThis.levelId = 'L1'; globalThis.scenes = [];
      activeLevel = () => ({level_id: levelId});
      request = path => new Promise((resolve, reject) => requests.push({path, resolve, reject}));
      renderScene = body => scenes.push(body.level_id);
    `);
    const older = scene.run('loadScene()');
    scene.run("levelId = 'L2'");
    const newer = scene.run('loadScene()');
    scene.context.requests[1].resolve({level_id: 'L2'});
    await newer;
    scene.context.requests[0].resolve({level_id: 'L1'});
    await older;
    assert.deepEqual(Array.from(scene.context.scenes), ['L2']);
  });
  assert.deepEqual(failures, []);
  console.log('Route state regressions passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
