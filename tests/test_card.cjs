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
