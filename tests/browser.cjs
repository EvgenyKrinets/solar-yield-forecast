const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
 const page=await browser.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.setContent('<body style="margin:0"><solar-comparison-card></solar-comparison-card></body>');
 await page.addScriptTag({path:'custom_components/solar_yield_forecast/frontend/solar-comparison-card.js'});
 await page.evaluate(()=>{
   const card=document.querySelector('solar-comparison-card');card.setConfig({});
   const now=Date.now(), rows=[];
   for(let t=now-54*3600000;t<now;t+=60000)rows.push({last_changed:new Date(t).toISOString(),state:'4000'});
   const hass={states:{'sensor.total_dc_power':{attributes:{unit_of_measurement:'W'}},'sensor.solar_yield_forecast_today':{attributes:{daily_forecast:Array.from({length:8},(_,i)=>({date:'2026-10-'+(22+i),kwh:100+i}))}},'sensor.solar_yield_forecast_power_profile_today':{attributes:{points:[{time:'invalid',power_w:null}]}}},callApi:async()=>[rows]};
   window.fixture=hass;card.hass=hass;
 });
 for(const width of [360,850,1400]){
   await page.setViewportSize({width,height:900});await page.waitForTimeout(150);
   const svg=page.locator('solar-comparison-card').locator('svg');
   const box=await svg.boundingBox();assert.ok(box.width<=width);
   await svg.dispatchEvent('pointermove',{clientX:box.x+box.width/2,clientY:box.y+60});
   await page.waitForFunction(()=>document.querySelector('solar-comparison-card').shadowRoot.querySelector('.chart-tooltip').style.display==='block');
   const text=await page.locator('.chart-tooltip').innerText();assert.match(text,/4.00/);
   await page.evaluate(()=>document.querySelector('solar-comparison-card').hass={...window.fixture});
   assert.equal(await page.locator('.chart-tooltip').evaluate(e=>e.style.display),'block');
 }
 await page.evaluate(()=>document.querySelector('solar-comparison-card').setConfig({size:'compact'}));
 await page.waitForTimeout(100);
 assert.equal(await page.locator('svg').evaluate(e=>e.viewBox.baseVal.height),260);
 assert.deepEqual(errors,[]);await browser.close();console.log('Browser: hover, resize, compact, invalid timestamps, unrelated HA updates passed');
})().catch(e=>{console.error(e);process.exit(1)});
