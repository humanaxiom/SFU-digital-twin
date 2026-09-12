// Docker Chromium A/B/C evidence: identical native route, three SVG representations.
const fs = require('node:fs');
const vm = require('node:vm');
const {spawn} = require('node:child_process');
const assert = require('node:assert/strict');
assert.ok(fs.existsSync('/.dockerenv'));
const source = fs.readFileSync('tests/browser/demo.cjs','utf8');
const context = vm.createContext({setTimeout,clearTimeout});
vm.runInContext(source.slice(source.indexOf('class Cdp {'), source.indexOf('const quote = JSON.stringify'))+';globalThis.Cdp=Cdp;',context);
const fixtures = JSON.parse(fs.readFileSync('docs/reports/DT-015-demo-routes.json')).fixtures;
const fixture = fixtures.strand_corridor;
(async()=>{
  const route = await (await fetch('http://demo:8080/demo/v1/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:{unit_id:fixture.origin.unit_id},destination:{unit_id:fixture.destination.unit_id},profile:'default'})})).json();
  const proc = spawn('/ms-playwright/chromium-1140/chrome-linux/chrome',['--headless','--no-sandbox','--disable-gpu','--remote-debugging-pipe'],{stdio:['ignore','ignore','ignore','pipe','pipe']});
  try {
    const cdp=new context.Cdp(proc);
    const {targetId}=await cdp.call('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await cdp.call('Target.attachToTarget',{targetId,flatten:true});cdp.sessionId=sessionId;
    await cdp.call('Page.enable');
    await cdp.call('Emulation.setDeviceMetricsOverride',{width:1500,height:700,deviceScaleFactor:1,mobile:false});
    const facts = await cdp.evaluate(`(async()=>{
      const route=${JSON.stringify(route)};
      const lines=route.guidance.geometries.map(g=>g.geometry.coordinates);
      const points=lines.flat();const minX=Math.min(...points.map(p=>p[0])),minY=Math.min(...points.map(p=>p[1]));
      const maxX=Math.max(...points.map(p=>p[0])),maxY=Math.max(...points.map(p=>p[1]));
      const width=maxX-minX+4,height=maxY-minY+4;
      document.body.style='margin:0;font:18px sans-serif;display:flex';
      const counts=[];
      for(const mode of ['native','per-path','scene-local']){
        const origin=mode==='scene-local'?[minX,minY]:[0,0];
        const paths=lines.map(line=>{
          const p=mode==='per-path'?line[0]:origin;
          const d=line.map((v,i)=>(i?'L':'M')+(v[0]-p[0])+' '+(-(v[1]-p[1]))).join(' ');
          const transform=mode==='per-path'?' transform="translate('+p[0]+' '+(-p[1])+')"':'';
          return '<path d="'+d+'"'+transform+' fill="none" stroke="#005fcc" stroke-width="6" vector-effect="non-scaling-stroke"/>';
        }).join('');
        const svg='<svg xmlns="http://www.w3.org/2000/svg" width="500" height="640" viewBox="'+(minX-origin[0]-2)+' '+(-maxY+origin[1]-2)+' '+width+' '+height+'">'+paths+'</svg>';
        const section=document.createElement('section');section.innerHTML='<h2>'+mode+'</h2>'+svg;document.body.append(section);
        const image=new Image();image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);await image.decode();
        const canvas=document.createElement('canvas');canvas.width=500;canvas.height=640;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
        const pixels=ctx.getImageData(0,0,500,640).data;let painted=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i]>100)painted++;
        counts.push({mode,painted});
      }
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      return {counts,origin:[minX,minY],pieces:lines.length};
    })()`);
    fs.mkdirSync('build/takeover-browser/svg-precision',{recursive:true});
    const {data}=await cdp.call('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync('build/takeover-browser/svg-precision/abc.png',Buffer.from(data,'base64'));
    fs.writeFileSync('build/takeover-browser/svg-precision/results.json',JSON.stringify(facts,null,2));
    console.log(JSON.stringify(facts));
    await cdp.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await cdp.call('Page.navigate',{url:'http://demo:8080/'});
    await cdp.wait('typeof routeUnits !== "undefined" && routeUnits.length > 0 && currentScene !== null');
    await cdp.evaluate(`(async()=>{routeOrigin.value=${JSON.stringify(fixture.origin.unit_id)};routeDestination.value=${JSON.stringify(fixture.destination.unit_id)};await submitSelectedRoute();})()`);
    await cdp.wait('activeRoute?.guidance && currentScene?.level.level_id === activeRoute.guidance.steps[0].level_id');
    await cdp.evaluate("selectGuidanceStep(activeRoute.guidance.steps.find(s=>s.kind==='walk').step_id)");
    await cdp.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    const actual=await cdp.call('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync('build/takeover-browser/svg-precision/actual-strand-walk.png',Buffer.from(actual.data,'base64'));
  } finally {proc.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
