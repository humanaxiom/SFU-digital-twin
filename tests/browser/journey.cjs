"use strict";

const assert = require("node:assert/strict");
const { activateButton, assertSelected, verifyGuidance, chooseRoomInspection } = require("./guidance.cjs");

const quote = JSON.stringify;
const routePosts = "__requests.filter(request => request.url === '/demo/v1/route' && request.method === 'POST')";
const floorButton = levelId => `#floor-buttons [data-level-id="${levelId}"]`;
const visitButton = visit => `#floor-journey [data-visit-id="${visit.visit_id}"]`;
const ready = levelId => `document.querySelector('#viewing-floor').dataset.levelId === ${quote(levelId)}
  && document.querySelector('#floor-map').getAttribute('aria-busy') === 'false'`;

async function previewElevatorJourney(cdp, fixture, chooseFloor) {
  const before = await cdp.evaluate(`${routePosts}.length`);
  for (const [endpoint, action] of [[fixture.origin, "#room-start-here"], [fixture.destination, "#room-directions-here"]]) {
    await chooseFloor(cdp, endpoint.level_id);
    await cdp.wait(ready(endpoint.level_id));
    await chooseRoomInspection(cdp);
    await activateButton(cdp, `#room-list [data-unit-id="${endpoint.unit_id}"]`);
    await activateButton(cdp, action, "Enter");
  }
  await cdp.wait(`document.querySelector('#route-destination').value === ${quote(fixture.destination.unit_id)}`);
  await cdp.evaluate("document.querySelector('#route-profile').focus()");
  const key = { key: "End", code: "End", windowsVirtualKeyCode: 35 };
  await cdp.call("Input.dispatchKeyEvent", { type: "rawKeyDown", ...key });
  await cdp.call("Input.dispatchKeyEvent", { type: "keyUp", ...key });
  await cdp.wait("document.querySelector('#route-profile').value === 'elevator_only'");
  assert.equal(await cdp.evaluate(`${routePosts}.length`), before);
  await activateButton(cdp, "#route-submit", "Enter");
  await cdp.wait(`${routePosts}[${before}]?.done && document.querySelector('#route-request-status').dataset.state === 'success'`);
  const body = await cdp.evaluate(`${routePosts}[${before}].response`);
  assert.equal(body.origin.unit_id, fixture.origin.unit_id);
  assert.equal(body.destination.unit_id, fixture.destination.unit_id);
  assert.equal(body.profile, "elevator_only");
  if (fixture.edge_ids) assert.deepEqual(body.edge_ids, fixture.edge_ids);
  verifyGuidance(body);
  return body;
}

async function assertJourneyPosition(cdp, body, step) {
  await assertSelected(cdp, body, step);
  assert.equal(await cdp.evaluate("document.querySelector('#floor-journey [aria-current=location]')?.dataset.visitId"), step.visit_id);
}

async function visibleControls(cdp, selectors) {
  return cdp.evaluate(`Object.fromEntries(${quote(selectors)}.map(selector => {
    const node = document.querySelector(selector);
    const rect = node.getBoundingClientRect();
    return [selector, {
      visible: node.checkVisibility() && rect.top >= 0 && rect.bottom <= innerHeight,
      height: rect.height,
      top: rect.top,
      bottom: rect.bottom,
    }];
  }))`);
}

async function touch(cdp, selector) {
  const point = await cdp.evaluate(`(() => {
    const box = document.querySelector(${quote(selector)}).getBoundingClientRect();
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  })()`);
  await cdp.call("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point] });
  await cdp.call("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function exerciseJourney(cdp, fixture, result, { chooseFloor, screenshot }) {
  await cdp.call("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  const body = await previewElevatorJourney(cdp, fixture, chooseFloor);
  const { visits, steps, transitions } = body.guidance;
  result.journey = { visits, transitions, failures: [], mobile: {}, routePosts: 1 };
  const check = async (name, exercise) => {
    try {
      await exercise();
      result.checks.push(name);
    } catch (error) {
      result.journey.failures.push({ name, error: String(error) });
    }
  };

  await check("N07 visit selection synchronizes the first instruction, Next and Previous", async () => {
    const visit = visits[1];
    const index = steps.findIndex(step => step.visit_id === visit.visit_id);
    await activateButton(cdp, visitButton(visit), "Enter");
    await assertJourneyPosition(cdp, body, steps[index]);
    await activateButton(cdp, "#step-next", "Enter");
    await assertJourneyPosition(cdp, body, steps[index + 1]);
    await activateButton(cdp, "#step-previous", " ");
    await assertJourneyPosition(cdp, body, steps[index]);
  });

  const transition = transitions.at(-1);
  const departure = steps.find(step => step.transition_id === transition.transition_id && step.phase === "departure");
  const arrival = steps.find(step => step.transition_id === transition.transition_id && step.phase === "arrival");
  await check("N08 named elevator phases stay aligned to their exact authored visit and geometry", async () => {
    assert.equal(await cdp.evaluate("document.querySelector('#directions-list').open"), false);
    await activateButton(cdp, "#directions-list > summary", "Enter");
    assert.ok(await cdp.evaluate("document.querySelector('#directions-list').open"));
    assert.deepEqual(await cdp.evaluate("[...document.querySelectorAll('#floor-journey button')].map(node => node.dataset.visitId)"),
      visits.map(visit => visit.visit_id));
    await activateButton(cdp, `#route-steps [data-step-id="${departure.step_id}"]`, "Enter");
    await assertJourneyPosition(cdp, body, departure);
    const names = await cdp.evaluate("document.querySelector('#transition-views').textContent");
    assert.ok(names.includes(transition.from_label) && names.includes(transition.to_label));
    await activateButton(cdp, "#transition-arrival", "Enter");
    await assertJourneyPosition(cdp, body, arrival);
    const skippedLevel = "SFU_BURNABY_QUAD_4000";
    assert.equal(transition.from_level_id, "SFU_BURNABY_QUAD_3000");
    assert.equal(transition.to_level_id, "SFU_BURNABY_QUAD_5000");
    assert.ok(await cdp.evaluate(`document.querySelector(${quote(floorButton(skippedLevel))}).checkVisibility()`));
    assert.equal(visits.some(visit => visit.level_id === skippedLevel), false);
    assert.equal(body.guidance.geometries.some(item => item.level_id === skippedLevel), false);
    await activateButton(cdp, "#transition-departure", " ");
    await assertJourneyPosition(cdp, body, departure);
  });

  await check("N09 manual floor and room exploration replaces Next/Previous with Return to route", async () => {
    const explored = visits[0].level_id;
    const viewBox = () => cdp.evaluate("document.querySelector('#floor-map').getAttribute('viewBox')");
    await activateButton(cdp, "#zoom-out");
    const departureCamera = await viewBox();
    await activateButton(cdp, floorButton(explored));
    await cdp.wait(ready(explored));
    await chooseRoomInspection(cdp);
    await activateButton(cdp, "#room-list button");
    assert.equal(await cdp.evaluate(`${routePosts}.length`), 1);
    assert.match(await cdp.evaluate("document.querySelector('#map-route-identity').textContent"), /AQ2035\.2.*AQ5046/i);
    const navigation = await cdp.evaluate(`({
      previous: document.querySelector('#step-previous').checkVisibility(),
      next: document.querySelector('#step-next').checkVisibility(),
      returnAction: document.querySelector('#return-to-route').checkVisibility(),
      context: document.querySelector('#map-context').textContent
    })`);
    assert.deepEqual(navigation, { previous: false, next: false, returnAction: true, context: `Exploring ${visits[0].label}` });
    await activateButton(cdp, "#zoom-in");
    const exploredCamera = await viewBox();
    await activateButton(cdp, "#return-to-route", "Enter");
    await assertJourneyPosition(cdp, body, departure);
    assert.equal(await viewBox(), departureCamera);
    assert.equal(await cdp.evaluate("document.activeElement.id"), "current-instruction");
    await activateButton(cdp, floorButton(explored));
    await cdp.wait(ready(explored));
    assert.equal(await viewBox(), exploredCamera);
    await activateButton(cdp, "#show-campus");
    assert.equal(await cdp.evaluate("document.querySelector('#return-to-route').checkVisibility()"), true);
    await activateButton(cdp, "#return-to-route", "Enter");
    await assertJourneyPosition(cdp, body, departure);
  });

  await check("N13 mobile instruction, transition and Next are visible with the map", async () => {
    await cdp.call("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
    await cdp.call("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
    for (const width of [390, 320]) {
      await cdp.call("Emulation.setDeviceMetricsOverride", { width, height: 844, deviceScaleFactor: 1, mobile: true });
      await activateButton(cdp, `#route-steps [data-step-id="${departure.step_id}"]`, "Enter");
      await assertJourneyPosition(cdp, body, departure);
      await cdp.evaluate("window.scrollTo(0,0); new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
      const layout = await visibleControls(cdp, ["#current-instruction", "#transition-arrival", "#step-next", "#floor-map"]);
      result.journey.mobile[width] = layout;
      assert.ok(layout["#current-instruction"].visible && layout["#transition-arrival"].visible
        && layout["#step-next"].visible && layout["#floor-map"].bottom > 160
        && layout["#floor-map"].top < 764, JSON.stringify(layout));
      assert.ok(layout["#transition-arrival"].height >= 44 && layout["#step-next"].height >= 44);
      assert.equal(await cdp.evaluate("document.documentElement.scrollWidth <= innerWidth"), true);
      assert.ok(await cdp.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"));
      await screenshot(cdp, `journey-${width}-departure`);
      await cdp.evaluate(`window.scrollBy(0, document.querySelector('.current-step').getBoundingClientRect().top + 24);
        new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
      const scrolled = await visibleControls(cdp, [".current-step", "#transition-arrival", "#floor-map"]);
      result.journey.mobile[width].scrolled = scrolled;
      assert.equal(scrolled[".current-step"].top, 0, "instruction card follows the mobile viewport");
      assert.ok(scrolled["#transition-arrival"].visible && scrolled["#floor-map"].visible
        && scrolled["#floor-map"].bottom - scrolled[".current-step"].bottom >= 160, JSON.stringify(scrolled));
      await touch(cdp, "#transition-arrival");
      await assertJourneyPosition(cdp, body, arrival);
      await activateButton(cdp, "#step-next", "Enter");
      const next = steps[steps.indexOf(arrival) + 1];
      await assertJourneyPosition(cdp, body, next);
      await activateButton(cdp, "#show-campus");
      const recovery = (await visibleControls(cdp, ["#return-to-route"]))["#return-to-route"];
      assert.ok(recovery.visible && recovery.height >= 44);
      result.journey.mobile[width].returnAction = recovery;
      await touch(cdp, "#return-to-route");
      await assertJourneyPosition(cdp, body, next);
    }
    await cdp.call("Emulation.setTouchEmulationEnabled", { enabled: false });
  });

  await check("N08 repeated floor selects its second exact chronological visit", async () => {
    await cdp.call("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
    await activateButton(cdp, "#route-clear", "Enter");
    const repeat = await previewElevatorJourney(cdp, {
      origin: { unit_id: "SFU_BURNABY_QUAD_1000_E2-1", level_id: "SFU_BURNABY_QUAD_1000" },
      destination: { unit_id: "SFU_BURNABY_QUAD_3000_3019", level_id: "SFU_BURNABY_QUAD_3000" },
    }, chooseFloor);
    const { visits: repeatedVisits, steps: repeatedSteps } = repeat.guidance;
    assert.deepEqual(repeatedVisits.map(visit => visit.level_id.split("_").at(-1)),
      ["1000", "2000", "3000", "4000", "5000", "4000", "3000"]);
    const occurrences = repeatedVisits.filter(visit => visit.level_id === repeat.destination.level_id);
    assert.equal(occurrences.length, 2);
    assert.notEqual(occurrences[0].visit_id, occurrences[1].visit_id);
    for (const visit of occurrences) {
      await activateButton(cdp, visitButton(visit), "Enter");
      await assertJourneyPosition(cdp, repeat, repeatedSteps.find(step => step.visit_id === visit.visit_id));
    }
    const second = repeatedSteps.findIndex(step => step.visit_id === occurrences[1].visit_id);
    await activateButton(cdp, "#step-next", "Enter");
    await assertJourneyPosition(cdp, repeat, repeatedSteps[second + 1]);
    await activateButton(cdp, "#step-previous", " ");
    await assertJourneyPosition(cdp, repeat, repeatedSteps[second]);
    result.journey.repeatedRoute = { origin: repeat.origin.unit_id, destination: repeat.destination.unit_id,
      visits: repeatedVisits, distance: repeat.network_distance_m };
  });
  result.journey.routePosts = await cdp.evaluate(`${routePosts}.length`);
  assert.deepEqual(await cdp.evaluate("window.__errors"), []);
  assert.equal(result.journey.failures.length, 0, JSON.stringify(result.journey.failures));
}

module.exports = { exerciseJourney };
