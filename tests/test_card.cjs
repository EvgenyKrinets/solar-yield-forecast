const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source=fs.readFileSync('custom_components/solar_yield_forecast/frontend/solar-comparison-card.js','utf8');
const ctx={HTMLElement:class{},customElements:{get(){},define(){}},window:{}};
vm.createContext(ctx);vm.runInContext(source,ctx);
const row=(minutes,state)=>({last_updated:new Date(minutes*60000).toISOString(),state:String(state)});
test('time weighting rather than sample count; energy units',()=>{
 const result=ctx.solarQuarterHours([row(0,1000),row(1,3000),row(2,3000)],'W',900000);
 assert.equal(result.length,1);assert.equal(result[0].power_w,43000/15);
 assert.ok(Math.abs(result[0].energy_kwh-43/60)<1e-9);
});
test('unavailable breaks interval coverage',()=>{
 assert.equal(ctx.solarQuarterHours([row(0,1000),row(5,'unavailable'),row(10,1000)],'W',900000).length,0);
});
test('kW and partial intervals',()=>{
 assert.equal(ctx.solarQuarterHours([row(0,4)],'kW',900000)[0].energy_kwh,1);
 assert.equal(ctx.solarQuarterHours([row(0,4)],'kW',899999).length,0);
});
test('bundled and manual cards are identical',()=>assert.equal(source,fs.readFileSync('solar-comparison-card.js','utf8')));

test('smooth curves preserve knots, bounds and input measurements',()=>{
 const points=[[0,0],[.25,1000],[.5,9000],[.75,9100],[1,200],[1.25,0],[1.5,0]];
 const original=JSON.stringify(points), identity=x=>x;
 const path=ctx.solarSmoothPath(points,identity,identity);
 const curves=[...path.matchAll(/C([\d., -]+)/g)].map(m=>m[1].trim().split(/[ ,]+/).map(Number));
 assert.equal(curves.length,points.length-1);
 for(let i=0;i<curves.length;i++){
   const [x1,y1,x2,y2,x3,y3]=curves[i], [x0,y0]=points[i];
   assert.equal(x3,points[i+1][0]); assert.equal(y3,points[i+1][1]);
   let previous=y0;
   for(let j=0;j<=100;j++){
     const t=j/100,u=1-t,y=u*u*u*y0+3*u*u*t*y1+3*u*t*t*y2+t*t*t*y3;
     assert.ok(y>=Math.min(y0,y3)-.01 && y<=Math.max(y0,y3)+.01);
     assert.ok(y3>=y0 ? y>=previous-.01 : y<=previous+.01);previous=y;
   }
   assert.ok(x1>=x0 && x2<=x3);
 }
 assert.equal(JSON.stringify(points),original);
});

test('smoothing never joins gaps; linear opt-out and isolated points work',()=>{
 const points=[[0,0],[.25,200],[1,300],[1.25,0],[2,0]],id=x=>x;
 const path=ctx.solarSmoothPath(points,id,id);
 assert.equal((path.match(/M/g)||[]).length,3);
 assert.equal((path.match(/C/g)||[]).length,2);
 const linear=ctx.solarSmoothPath(points,id,id,false);
 assert.ok(!linear.includes('C'));assert.equal((linear.match(/L/g)||[]).length,2);
 assert.equal(ctx.solarSmoothPath([],id,id),'');
});

test('today fill closes each observed section without filling gaps or future time',()=>{
 const points=[[8,1000],[8.25,2000],[9,3000],[9.25,1000]],id=x=>x;
 const area=ctx.solarSmoothPath(points,id,id,true,0);
 assert.equal((area.match(/M/g)||[]).length,2);
 assert.equal((area.match(/Z/g)||[]).length,2);
 assert.match(area,/L8.25,0.00 L8.00,0.00 Z M9.00/);
 assert.ok(area.endsWith('L9.25,0.00 L9.00,0.00 Z'));
 assert.equal(ctx.solarSmoothPath([],id,id,true,0),'');
});
