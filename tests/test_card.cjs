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
test('unavailable gaps up to ten minutes are linearly interpolated',()=>{
 const flat=ctx.solarQuarterHours([row(0,1000),row(5,'unavailable'),row(10,1000)],'W',900000);
 assert.equal(flat.length,1);assert.equal(flat[0].power_w,1000);
 const rising=ctx.solarQuarterHours([row(0,1000),row(5,'unknown'),row(15,3000)],'W',900000);
 assert.equal(rising.length,1);assert.ok(Math.abs(rising[0].power_w-1666.6666666666667)<1e-9);
});
test('unavailable gaps longer than ten minutes still break coverage',()=>{
 assert.equal(ctx.solarQuarterHours([row(0,1000),row(2,'unavailable'),row(13,1000)],'W',900000).length,0);
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

test('calendar navigation clamps month/year and handles leap years',()=>{
 assert.equal(ctx.solarShift('2026-01-31',1,'month'),'2026-02-01');
 assert.equal(ctx.solarShift('2024-02-29',1,'year'),'2025-01-01');
 assert.equal(ctx.solarShift('2026-10-23',-7),'2026-10-16');
});
test('Israel calendar midnight respects the DST transition',()=>{
 assert.equal(new Date(ctx.solarMidnight('2026-10-24')).toISOString(),'2026-10-23T21:00:00.000Z');
 assert.equal(new Date(ctx.solarMidnight('2026-10-26')).toISOString(),'2026-10-25T22:00:00.000Z');
 assert.equal(ctx.solarMidnight('2026-10-26')-ctx.solarMidnight('2026-10-25'),25*3600000);
});
test('configured site timezone controls calendar boundaries',()=>{
 assert.equal(new Date(ctx.solarMidnight('2026-03-07','America/New_York')).toISOString(),'2026-03-07T05:00:00.000Z');
 assert.equal(new Date(ctx.solarMidnight('2026-03-09','America/New_York')).toISOString(),'2026-03-09T04:00:00.000Z');
 assert.equal(vm.runInContext("solarDay(new Date('2026-01-01T01:00:00Z'),'America/Los_Angeles')",ctx),'2025-12-31');
});

test('late history response cannot replace a newer selected date',async()=>{
 const Card=vm.runInContext('SolarComparisonCard',ctx),card=new Card();
 card.config={pv_entity:'sensor.pv'};card._period='day';card._selected='2026-10-20';card._render=()=>{};
 const pending=[];card._hass={states:{},callApi:()=>new Promise(resolve=>pending.push(resolve))};
 const first=card._fetch();card._selected='2026-10-21';const second=card._fetch();
 pending[1]([[{state:'2000'}]]);await second;
 pending[0]([[{state:'1000'}]]);await first;
 assert.equal(card._history[0].state,'2000');assert.equal(card._loading,false);
});


test('fractional zoom ticks are short HH:mm labels',()=>{
 for(const hour of [8.389241211,12.99999,23.999999,0,24])assert.match(ctx.solarTimeLabel(hour),/^\d{2}:\d{2}$/);
 assert.equal(ctx.solarTimeLabel(8.5),'08:30');
 assert.equal(ctx.solarTimeLabel(23.999999),'24:00');
});

test('managed dashboard always contains a valid views array and exact entities',()=>{
 const config=ctx.solarManagedDashboardConfig({
   title:'Roof',pv_entity:'sensor.real_pv',energy_entity:'sensor.real_energy',
   forecast_entity:'sensor.profile',day_forecast_entity:'sensor.today',time_zone:'Asia/Jerusalem'
 });
 assert.ok(Array.isArray(config.views));assert.equal(config.views.length,1);
 assert.equal(config.views[0].type,'panel');assert.equal(config.views[0].cards.length,1);
 const card=config.views[0].cards[0];
 assert.equal(card.type,'custom:solar-comparison-card');
 assert.equal(card.pv_entity,'sensor.real_pv');assert.equal(card.energy_entity,'sensor.real_energy');
 assert.equal(card.forecast_entity,'sensor.profile');assert.equal(card.day_forecast_entity,'sensor.today');
 assert.equal(card.solar_yield_forecast_managed,true);
});

test('sidebar application exposes integration settings to administrators',()=>{
 assert.match(source,/class SolarYieldForecastPanel/);
 assert.match(source,/\/config\/integrations\/integration\/solar_yield_forecast/);
 assert.match(source,/class="settings"/);
 assert.match(source,/settings\.hidden=!this\._hass\.user\?\.is_admin/);
});
