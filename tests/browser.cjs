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
   const points=Array.from({length:216},(_,i)=>({time:new Date(now-54*3600000+i*900000).toISOString(),power_w:4500+3000*Math.sin(i/12)}));
   const hass={states:{'sensor.total_dc_power':{attributes:{unit_of_measurement:'W'}},'sensor.solar_yield_forecast_today':{attributes:{daily_forecast:Array.from({length:8},(_,i)=>({date:'2026-10-'+(22+i),kwh:100+i}))}},'sensor.solar_yield_forecast_power_profile_today':{attributes:{points:[{time:'invalid',power_w:null},...points]}}},callApi:async()=>[rows]};
   window.fixture=hass;card.hass=hass;
 });
 for(const width of [360,850,1400]){
   await page.setViewportSize({width,height:900});await page.waitForTimeout(150);
   const svg=page.locator('solar-comparison-card').locator('svg');
   const box=await svg.boundingBox();assert.ok(box.width<=width);
   const metrics=await page.locator('solar-comparison-card').evaluate(card=>{
     const root=card.shadowRoot,svg=root.querySelector('svg'),dates=[...root.querySelectorAll('.day>span')];
     return {font:getComputedStyle(root.querySelector('.legend')).fontSize,family:getComputedStyle(root.querySelector('ha-card')).fontFamily,
       labelScale:svg.getBoundingClientRect().width/svg.viewBox.baseVal.width,
       curve:root.querySelector('.series-line').getAttribute('d'),
       datesFit:dates.every(el=>el.scrollWidth<=el.clientWidth+1),
       rows:new Set(dates.map(el=>Math.round(el.getBoundingClientRect().top))).size};
   });
   assert.equal(metrics.font,'14px');assert.match(metrics.family,/Roboto|system-ui/);
   assert.ok(metrics.labelScale>=.98);assert.match(metrics.curve,/C/);assert.ok(metrics.datesFit);
   assert.equal(metrics.rows,width<580?2:1);
   assert.equal(await page.locator('.day').count(),8);
   assert.equal(await page.locator('.today-area').count(),1);
   assert.equal(await page.locator('[data-series="yesterday"]').getAttribute('stroke'),'#3478f6');
   assert.equal(await page.locator('[data-series="today"]').getAttribute('stroke'),'#ff9e3d');
   assert.equal(await page.locator('[data-series="forecast"]').getAttribute('stroke'),'#16a06a');
   await svg.dispatchEvent('pointermove',{clientX:box.x+box.width/2,clientY:box.y+60});
   await page.waitForFunction(()=>document.querySelector('solar-comparison-card').shadowRoot.querySelector('.chart-tooltip').style.display==='block');
   const text=await page.locator('.chart-tooltip').innerText();assert.match(text,/4.00/);
   await page.evaluate(()=>document.querySelector('solar-comparison-card').hass={...window.fixture});
   assert.equal(await page.locator('.chart-tooltip').evaluate(e=>e.style.display),'block');
 }
 await page.evaluate(()=>document.querySelector('solar-comparison-card').setConfig({size:'compact'}));
 await page.waitForTimeout(100);
 assert.equal(await page.locator('svg').evaluate(e=>e.viewBox.baseVal.height),260);
 await page.evaluate(()=>document.querySelector('solar-comparison-card').hass=window.fixture);
 await page.waitForFunction(()=>document.querySelector('solar-comparison-card').shadowRoot.querySelectorAll('.series-line').length===3);
 await page.evaluate(async()=>{
   const card=document.querySelector('solar-comparison-card');
   card.hass={...window.fixture,callApi:async()=>{throw {message:'History refresh failed'};}};
   await card._fetch();
 });
 assert.match(await page.locator('.small').allTextContents().then(x=>x.join(' ')),/History refresh failed/);
 assert.equal(await page.locator('.series-line').count(),3);
 await page.evaluate(()=>{const c=document.querySelector('solar-comparison-card');c.hass=window.fixture;});
 await page.locator('[data-period="week"]').click();
 assert.match(await page.locator('.summary').innerText(), / — /);
 await page.locator('[data-step="-1"]').click();
 const selected=await page.locator('input[type=date]').inputValue();
 await page.locator('[data-step="1"]').click();
 assert.notEqual(await page.locator('input[type=date]').inputValue(),selected);
 await page.locator('[data-period="day"]').click();
 await page.locator('.now').click();
 await page.waitForTimeout(100);
 await page.locator('[data-toggle="0"]').click();
 assert.equal(await page.locator('[data-series="yesterday"]').count(),0);
 await page.locator('[data-toggle="0"]').click();
 const wrap=page.locator('.chart-wrap');const rect=await wrap.boundingBox();
 await wrap.dispatchEvent('touchstart',{touches:[{identifier:1,clientX:rect.x+100,clientY:rect.y+100},{identifier:2,clientX:rect.x+200,clientY:rect.y+100}]});
 await wrap.dispatchEvent('touchmove',{touches:[{identifier:1,clientX:rect.x+50,clientY:rect.y+100},{identifier:2,clientX:rect.x+250,clientY:rect.y+100}]});
 await wrap.dispatchEvent('touchend',{touches:[]});
 const span=await page.locator('solar-comparison-card').evaluate(c=>c._view[1]-c._view[0]);
 assert.equal(span,12);
 await page.locator('.reset').click();
 assert.equal(await page.locator('solar-comparison-card').evaluate(c=>c._view[1]-c._view[0]),24);
 await page.locator('.expand').click();assert.equal(await page.locator('solar-comparison-card').getAttribute('expanded'),'');
 await page.locator('.expand').click();
 await page.locator('.expand').click();
 await page.setViewportSize({width:390,height:500});
 await page.waitForTimeout(100);
 const before=await page.locator('solar-comparison-card').evaluate(c=>{c.scrollTop=180;window.savedCard=c.shadowRoot.querySelector('ha-card');window.savedButton=c.shadowRoot.querySelector('[data-toggle="2"]');return c.scrollTop;});
 assert.ok(before>0);
 await page.locator('solar-comparison-card').evaluate(c=>c.shadowRoot.querySelector('[data-toggle="2"]').click());
 assert.equal(await page.locator('solar-comparison-card').evaluate(c=>c.scrollTop),before);
 assert.ok(await page.locator('solar-comparison-card').evaluate(c=>c.shadowRoot.querySelector('ha-card')===window.savedCard&&c.shadowRoot.querySelector('[data-toggle="2"]')===window.savedButton));
 await page.locator('solar-comparison-card').evaluate(c=>{c._view=[8.389241211,17.6205801];c._render();});
 const labels=await page.locator('svg text').allTextContents();
 assert.ok(labels.filter(t=>t.includes(':')).every(t=>/^\d{2}:\d{2}$/.test(t)));
 assert.deepEqual(errors,[]);await browser.close();console.log('Browser: curves, readable fonts, responsive bars, hover, compact, invalid timestamps, refresh failure passed');
})().catch(e=>{console.error(e);process.exit(1)});
