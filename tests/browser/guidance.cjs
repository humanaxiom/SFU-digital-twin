"use strict";

const assert = require('node:assert/strict');
const quote = JSON.stringify;
const line = (geometry, [originX,originY]) => geometry.coordinates.map(([x,y], i) => `${i ? 'L' : 'M'}${x-originX} ${-(y-originY)}`).join(' ');

async function sceneOrigin(cdp) {
  const origin=await cdp.evaluate(`(() => {const map=document.querySelector('#floor-map');if(!map.hasAttribute('data-origin-x')||!map.hasAttribute('data-origin-y'))throw new Error('Scene origin is missing');return [Number(map.getAttribute('data-origin-x')),Number(map.getAttribute('data-origin-y'))];})()`);
  assert.ok(origin.every(Number.isFinite),'scene origin must be finite');
  return origin;
}

function nativeLine(d,[originX,originY]) {
  return d.split(/[ML]/).filter(Boolean).map(point=>{
    const [x,y]=point.trim().split(/\s+/).map(Number);
    return [x+originX,originY-y];
  });
}

function verifyGuidance(body) {
  const g = body.guidance;
  assert.equal(g?.version, 'dt018-guidance-v1');
  assert.ok(['available', 'limited', 'unavailable'].includes(g.status));
  for (const [collection, key] of [['steps','step_id'],['visits','visit_id'],['geometries','geometry_id'],['markers','marker_id'],['transitions','transition_id']]) {
    assert.equal(new Set(g[collection].map(item => item[key])).size, g[collection].length, `duplicate ${key}`);
  }
  if (g.status === 'unavailable') {
    assert.ok(g.warnings.length > 0);
    assert.equal(g.steps.length, 0);
    assert.equal(g.distance_m, null);
    return;
  }
  assert.equal(g.steps[0].kind, 'depart');
  assert.equal(g.steps.at(-1).kind, 'arrive');
  const geometries = new Map(g.geometries.map(item => [item.geometry_id,item]));
  const markers = new Map(g.markers.map(item => [item.marker_id,item]));
  const visitedSpans = new Map();
  for (const step of g.steps) {
    assert.ok(g.visits.some(v => v.visit_id === step.visit_id && v.step_ids.includes(step.step_id)));
    assert.ok(!/SFU_|measured pathway|approximate anchor|\btransition\b/i.test(step.instruction), `technical primary instruction: ${step.instruction}`);
    for (const id of step.geometry_ids) {
      const item = geometries.get(id);
      assert.ok(item, `unknown geometry ${id}`);
      assert.equal(item.level_id, step.level_id);
      assert.equal(item.geometry.type, 'LineString');
      const edge = body.edges[item.edge_occurrence];
      assert.equal(edge.mode, 'pathway');
      const originals = body.geometries.filter(original => original.edge_id === edge.edge_id && original.level_id === item.level_id);
      assert.ok(originals.some(original => JSON.stringify(original.geometry.coordinates.slice(item.start_segment, item.end_segment + 1)) === JSON.stringify(item.geometry.coordinates)), 'highlight differs from original route coordinates');
      assert.ok(step.spans.some(span => span.edge_occurrence === item.edge_occurrence && span.start_segment === item.start_segment && span.end_segment === item.end_segment));
    }
    for (const id of step.marker_ids) assert.ok(markers.has(id), `unknown marker ${id}`);
    for (const span of step.spans) {
      const used = visitedSpans.get(span.edge_occurrence) || new Set();
      for (let i=span.start_segment; i<span.end_segment; i++) {
        assert.ok(!used.has(i), 'walking segment belongs to two instructions');
        used.add(i);
      }
      visitedSpans.set(span.edge_occurrence,used);
    }
  }
  for (let i=0; i<body.edges.length; i++) {
    const edge=body.edges[i];
    if(edge.mode !== 'pathway') continue;
    const original=body.geometries.find(item=>item.edge_id===edge.edge_id && item.level_id===edge.level_id);
    assert.ok(original);
    assert.equal(visitedSpans.get(i)?.size,original.geometry.coordinates.length-1,'walking coverage has a gap');
  }
  for(const event of g.transitions){
    const phases=g.steps.filter(step=>step.transition_id===event.transition_id);
    assert.deepEqual(phases.map(step=>step.phase),['departure','arrival']);
    assert.ok(phases.every(step=>step.distance_m===null));
    assert.equal(markers.get(event.departure_marker_id).level_id,event.from_level_id);
    assert.equal(markers.get(event.arrival_marker_id).level_id,event.to_level_id);
  }
  if(g.status==='available'){
    assert.ok(Math.abs(g.distance_m-body.network_distance_m)<1e-6);
    const accounted=g.steps.filter(step=>step.kind==='walk').reduce((n,step)=>n+step.distance_m,0)+g.transitions.reduce((n,event)=>n+event.distance_m,0);
    assert.ok(Math.abs(accounted-body.network_distance_m)<1e-6,'guidance double counts or loses distance');
  } else {
    assert.equal(g.distance_m,null);
    assert.ok(g.warnings.length>0);
    assert.ok(g.steps.filter(step=>step.kind==='walk').every(step=>step.distance_m===null));
  }
}

async function activateButton(cdp,selector,key=null){
  const point=await cdp.evaluate(`(() => {
    const button=document.querySelector(${quote(selector)});
    if(!button)throw new Error('Missing control '+${quote(selector)});
    for(let p=button.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
    button.scrollIntoView({block:'center',inline:'nearest'});
    if(${quote(key)}!==null){button.focus();return null;}
    const r=button.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};
  })()`);
  if(key){
    const props={key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32};
    assert.ok(await cdp.evaluate(`document.activeElement.matches(${quote(selector)})`),'control did not receive keyboard focus');
    await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',text:key==='Enter'?'\r':' ',unmodifiedText:key==='Enter'?'\r':' ',...props});
    await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',...props});
  } else {
    for(const type of ['mousePressed','mouseReleased'])await cdp.call('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1});
  }
}

async function assertSelected(cdp,body,step){
  try {
    await cdp.wait(`document.querySelector('button[data-step-id="${step.step_id}"]')?.getAttribute('aria-current')==='step'`);
  } catch (error) {
    const state=await cdp.evaluate(`(() => ({
      requested:${quote(step.step_id)},
      selected:[...document.querySelectorAll('button[data-step-id][aria-current="step"]')].map(node=>node.dataset.stepId),
      viewing:document.querySelector('#viewing-floor')?.dataset.levelId,
      mapStatus:document.querySelector('#map-status')?.textContent,
      instruction:document.querySelector('#current-instruction')?.textContent,
      routeState:document.querySelector('#route-status')?.dataset.state,
      errors:window.__errors,
    }))()`);
    throw new Error(`${error.message}; state=${JSON.stringify(state)}`);
  }
  await cdp.wait(`document.querySelector('#viewing-floor')?.dataset.levelId===${quote(step.level_id)} && !document.querySelector('#map-status').textContent.includes('Loading')`);
  assert.equal(await cdp.evaluate(`document.querySelectorAll('button[data-step-id][aria-current="step"]').length`),1);
  const origin=await sceneOrigin(cdp);
  const pieces=step.geometry_ids.map(id=>body.guidance.geometries.find(g=>g.geometry_id===id)).filter(g=>g.level_id===step.level_id);
  const expected=pieces.map(g=>({id:g.geometry_id,d:line(g.geometry,origin),transform:null}));
  const actual=await cdp.evaluate(`[...document.querySelectorAll('.route-selected[data-geometry-id]')].map(p=>({id:p.dataset.geometryId,d:p.getAttribute('d'),transform:p.getAttribute('transform')}))`);
  assert.deepEqual(actual,expected,'selected instruction does not match painted span');
  for(let i=0;i<actual.length;i++)assert.deepEqual(nativeLine(actual[i].d,origin),pieces[i].geometry.coordinates.map(p=>p.slice(0,2)),'scene-local path does not reconstruct exact native coordinates');
  if(expected.length){
    const style=await cdp.evaluate(`(() => {
      const selected=getComputedStyle(document.querySelector('.route-selected'));
      const base=getComputedStyle(document.querySelector('#route-overlay .route-segment'));
      return {selected:selected.stroke,base:base.stroke,selectedWidth:parseFloat(selected.strokeWidth),baseWidth:parseFloat(base.strokeWidth)};
    })()`);
    assert.notEqual(style.selected,style.base,'selection requires a different path color');
    assert.ok(style.selectedWidth>style.baseWidth,'selection must also differ without color');
  }
  for(const id of step.marker_ids){
    const marker=body.guidance.markers.find(m=>m.marker_id===id);
    if(marker.level_id!==step.level_id)continue;
    assert.ok(await cdp.evaluate(`!!document.querySelector('.route-marker[data-marker-id="${id}"]')`),'selected endpoint or landing absent');
    const point=await cdp.evaluate(`(() => {const m=document.querySelector('.route-marker[data-marker-id="${id}"]');return [Number(m.dataset.x),Number(m.dataset.y)];})()`);
    assert.deepEqual(point,marker.coordinates,'landing marker moved away from its actual endpoint');
    assert.equal(await cdp.evaluate(`document.querySelector('.route-marker[data-marker-id="${id}"]').getAttribute('transform')`),`translate(${point[0]-origin[0]} ${-(point[1]-origin[1])})`,'landing marker uses a different scene origin');
  }
  assert.ok((await cdp.evaluate(`document.querySelector('#current-instruction').textContent`)).includes(step.instruction));
}

async function exerciseGuidance(cdp,body,record){
  verifyGuidance(body);
  const g=body.guidance;
  if(g.status==='unavailable')return;
  const walks=g.steps.filter(step=>step.kind==='walk');
  const chosen=[...new Set([walks[0],walks[Math.floor(walks.length/2)],walks.at(-1)].filter(Boolean))];
  for(let i=0;i<chosen.length;i++){
    await activateButton(cdp,`button[data-step-id="${chosen[i].step_id}"]`,[null,'Enter',' '][i]);
    await assertSelected(cdp,body,chosen[i]);
  }
  for(const event of g.transitions){
    const departure=g.steps.find(step=>step.transition_id===event.transition_id&&step.phase==='departure');
    const arrival=g.steps.find(step=>step.transition_id===event.transition_id&&step.phase==='arrival');
    await activateButton(cdp,`button[data-step-id="${departure.step_id}"]`);
    await assertSelected(cdp,body,departure);
    await activateButton(cdp,'#transition-arrival');
    await assertSelected(cdp,body,arrival);
    const landingPoints=g.markers.filter(m=>m.level_id===arrival.level_id).map(m=>m.coordinates);
    if (!g.geometries.some(item=>item.level_id===arrival.level_id) && landingPoints.length
      && landingPoints.every(p=>p[0]===landingPoints[0][0]&&p[1]===landingPoints[0][1])) {
      const contextBox=await cdp.evaluate("document.querySelector('#floor-map').getAttribute('viewBox')");
      await activateButton(cdp,'#fit-floor');
      assert.equal(await cdp.evaluate("document.querySelector('#floor-map').getAttribute('viewBox')"),contextBox,
        'point-only landing must initially show floor context');
    }
    const text=await cdp.evaluate(`document.querySelector('#transition-views').textContent`);
    assert.ok(text.includes(event.from_label)&&text.includes(event.to_label),'transition omits its named floors');
    await activateButton(cdp,'#transition-departure');
    await assertSelected(cdp,body,departure);
  }
  const middle=g.steps[Math.min(2,g.steps.length-2)];
  await activateButton(cdp,`button[data-step-id="${middle.step_id}"]`);
  await assertSelected(cdp,body,middle);
  await activateButton(cdp,'#step-next','Enter');
  await assertSelected(cdp,body,g.steps[g.steps.indexOf(middle)+1]);
  await activateButton(cdp,'#step-previous',' ');
  await assertSelected(cdp,body,middle);
  const otherVisit=g.visits.find(v=>v.level_id!==middle.level_id);
  if(otherVisit){
    await activateButton(cdp,`#floor-journey [data-visit-id="${otherVisit.visit_id}"]`);
    const firstOnVisit=g.steps.find(step=>step.visit_id===otherVisit.visit_id);
    await assertSelected(cdp,body,firstOnVisit);
  }
  record.guidance={status:g.status,steps:g.steps.length,visits:g.visits.map(v=>v.label),transitions:g.transitions.length,selectedStepIds:chosen.map(s=>s.step_id)};
  await activateButton(cdp,`button[data-step-id="${g.steps[0].step_id}"]`);
  await assertSelected(cdp,body,g.steps[0]);
}

module.exports={verifyGuidance,activateButton,assertSelected,exerciseGuidance,sceneOrigin};
