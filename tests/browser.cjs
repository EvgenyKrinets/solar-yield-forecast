const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const frontend=fs.readFileSync('custom_components/solar_yield_forecast/frontend/solar-comparison-card.js','utf8');
 const panelTag=frontend.match(/const SOLAR_PANEL_TAG='([^']+)'/)[1];
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
 const page=await browser.newPage();
 // Fixtures require completed quarters in the current day. Pin the clock so
 // a release crossing local midnight does not erase today's sample series.
 await page.clock.install({time:new Date('2026-10-24T12:00:00Z')});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.setContent('<body style="margin:0"><solar-comparison-card></solar-comparison-card></body>');
 await page.addScriptTag({path:'custom_components/solar_yield_forecast/frontend/solar-comparison-card.js'});
 await page.evaluate(()=>{
   const card=document.querySelector('solar-comparison-card');card.setConfig({});
   const now=Date.now(), rows=[];
   for(let t=now-54*3600000;t<now;t+=60000)rows.push({last_changed:new Date(t).toISOString(),state:'4000'});
   const points=Array.from({length:216},(_,i)=>({time:new Date(now-54*3600000+i*900000).toISOString(),power_w:4500+3000*Math.sin(i/12)}));
   const hass={states:{'sensor.total_dc_power':{attributes:{unit_of_measurement:'W'}},'sensor.solar_yield_forecast_today':{attributes:{daily_forecast:Array.from({length:30},(_,i)=>({date:new Date(Date.UTC(2026,9,22+i)).toISOString().slice(0,10),kwh:100+i,source:i>=16?'ensemble':'weather'}))}},'sensor.solar_yield_forecast_power_profile_today':{attributes:{points:[{time:'invalid',power_w:null},...points]}}},callApi:async(method,url)=>url.startsWith('solar_yield_forecast/profile/')?{points}:[rows]};
   hass.language='ru';window.fixture=hass;card.hass=hass;
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
 await page.locator('.language-picker').selectOption('en');
 assert.equal(await page.locator('ha-card').getAttribute('lang'),'en');
 assert.match(await page.locator('.legend').innerText(),/Fixed forecast/);
 const englishText=await page.locator('ha-card').evaluate(el=>{const copy=el.cloneNode(true);copy.querySelector('.language-bar')?.remove();return copy.textContent;});
 assert.doesNotMatch(englishText,/[А-Яа-яЁё]/);
 assert.equal(await page.locator('.accuracy-empty table').count(),0);
 await page.locator('.language-picker').selectOption('he');
 assert.equal(await page.locator('ha-card').getAttribute('dir'),'rtl');
 assert.match(await page.locator('.legend').innerText(),/תחזית/);
 const hebrewText=await page.locator('ha-card').evaluate(el=>{const copy=el.cloneNode(true);copy.querySelector('.language-bar')?.remove();return copy.textContent;});
 assert.doesNotMatch(hebrewText,/[А-Яа-яЁё]/);
 await page.locator('[data-period="range"]').click();
 assert.ok(await page.locator('.range-start').count());
 await page.locator('.language-picker').selectOption('auto');
 await page.evaluate(()=>{const c=document.querySelector('solar-comparison-card');c.hass={...window.fixture,locale:{language:'en'}};});
 assert.equal(await page.locator('ha-card').getAttribute('lang'),'en');
 await page.evaluate(()=>{const c=document.querySelector('solar-comparison-card');c.hass={...window.fixture,locale:{language:'he'}};});
 assert.equal(await page.locator('ha-card').getAttribute('dir'),'rtl');
 await page.evaluate(()=>{document.querySelector('solar-comparison-card').hass=window.fixture;});
 await page.locator('[data-period="day"]').click();
 await page.evaluate(()=>{
   const c=document.querySelector('solar-comparison-card');
   const a=window.fixture.states['sensor.solar_yield_forecast_today'].attributes;
   const date=c._selected;
   a.forecast_ledger_history=[{date:'2026-10-23',kind:'day_ahead',kwh:100,actual_kwh:90,deviation_kwh:-10,deviation_percent:-11.11,version:'1.6.0',completed:true}];
   a.forecast_ledger_summary={day_ahead_30:{samples:1,wape_percent:11.11,bias_percent:11.11}};
   c._original={kind:'day_ahead',kwh:100,recorded_at:'2026-10-23T20:00:00+03:00',version:'1.6.0',points:c._hass.states[c.config.forecast_entity].attributes.points.filter(p=>Number.isFinite(Date.parse(p.time))&&solarDay(new Date(p.time),c._timeZone())===date)};
   c._render();
 });
 assert.equal(await page.locator('.original-line').count(),1);
 assert.equal(await page.locator('.original-toggle .toggle').count(),1);
 assert.match(await page.locator('section').innerText(),/2026-10-23/);
 assert.match(await page.locator('.summary').innerText(),/100.0/);
 await page.locator('.original-toggle').click();
 assert.equal(await page.locator('.original-line').count(),0);
 assert.equal(await page.locator('.original-toggle').getAttribute('aria-pressed'),'false');
 await page.evaluate(()=>document.querySelector('solar-comparison-card').hass={...window.fixture});
 assert.equal(await page.locator('.original-line').count(),0);
 await page.locator('[data-cohort="morning"]').click();
 assert.equal(await page.locator('section tbody').count(),0);
 await page.locator('[data-cohort="day_ahead"]').click();
 await page.evaluate(()=>{
   const fixture=window.fixture;
   const today=fixture.states['sensor.solar_yield_forecast_today'];
   document.querySelector('solar-comparison-card').hass={...fixture,states:{...fixture.states,
     'sensor.solar_yield_forecast_today':{...today,attributes:{...today.attributes,
       weather_status:'stale',forecast_updated_at:'2026-10-25T12:00:00Z',last_refresh_error:{message:'HTTP 429 Too Many Requests'}}}}};
 });
 assert.match(await page.locator('.weather-warning').innerText(),/HTTP 429/);
 await page.evaluate(()=>document.querySelector('solar-comparison-card').hass=window.fixture);
 assert.equal(await page.locator('.weather-warning').count(),0);
 await page.evaluate(()=>document.querySelector('solar-comparison-card').setConfig({size:'compact'}));
 await page.waitForTimeout(100);
 assert.equal(await page.locator('svg').evaluate(e=>e.viewBox.baseVal.height),260);
 await page.locator('[data-forecast-range="30"]').click();
 assert.equal(await page.locator('.day').count(),30);
 assert.equal(await page.locator('.day.ensemble').count(),14);
 await page.locator('[data-forecast-range="8"]').click();
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
 await page.evaluate(()=>{document.querySelector('solar-comparison-card')._hideOriginal=false;});
 await page.locator('[data-period="week"]').click();
 assert.match(await page.locator('.summary').innerText(), / — /);
 assert.equal(await page.locator('.history-mode option[value="legacy"]').count(),0);
 assert.equal(await page.locator('.original-toggle .toggle').count(),1);
 assert.ok(await page.locator('[data-historical="true"]').count()>0);
 await page.locator('.original-toggle').click();
 assert.equal(await page.locator('[data-historical="true"]').count(),0);
 await page.locator('.original-toggle').click();
 await page.locator('[data-period="range"]').click();
 await page.locator('.range-start').fill('2026-10-01');
 await page.locator('.range-start').dispatchEvent('change');
 await page.locator('.range-end').fill('2026-10-24');
 await page.locator('.range-end').dispatchEvent('change');
 assert.match(await page.locator('.summary').innerText(),/2026-10-01 — 2026-10-24/);
 assert.ok(await page.locator('[data-historical="true"]').count()>0);
 await page.setViewportSize({width:360,height:900});await page.waitForTimeout(100);
 assert.ok(await page.locator('solar-comparison-card').evaluate(c=>{const card=c.shadowRoot.querySelector('ha-card');return card.scrollWidth<=card.clientWidth+1;}));
 await page.setViewportSize({width:1400,height:900});await page.waitForTimeout(100);
 await page.locator('.history-mode').selectOption('morning');
 assert.equal(await page.locator('[data-historical="true"]').count(),0);
 await page.locator('.history-mode').selectOption('best');
 await page.locator('[data-period="year"]').click();
 assert.ok(await page.locator('[data-historical="true"]').count()>0);
 await page.locator('[data-period="week"]').click();
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
 await page.locator('svg').evaluate(el=>window.gestureSvg=el);
 await wrap.dispatchEvent('touchmove',{touches:[{identifier:1,clientX:rect.x+50,clientY:rect.y+100},{identifier:2,clientX:rect.x+250,clientY:rect.y+100}]});
 assert.ok(await page.locator('svg').evaluate(el=>el===window.gestureSvg&&el.isConnected));
 await wrap.dispatchEvent('touchend',{touches:[{identifier:1,clientX:rect.x+50,clientY:rect.y+100}]});
 const rebased=await page.locator('solar-comparison-card').evaluate(c=>[...c._view]);
 await wrap.dispatchEvent('touchmove',{touches:[{identifier:1,clientX:rect.x+50,clientY:rect.y+100}]});
 assert.deepEqual(await page.locator('solar-comparison-card').evaluate(c=>c._view),rebased);
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
 await page.evaluate(panelTag=>{
   window.panelMessages=[];
   const panel=document.createElement(panelTag);
   panel.panel={config:{title:'Configured roof',pv_entity:'sensor.real_pv',energy_entity:'sensor.real_energy',forecast_entity:'sensor.real_profile',day_forecast_entity:'sensor.real_today',recalculate_entity:'button.recalculate_model',time_zone:'Asia/Jerusalem'}};
   panel.hass={...window.fixture,user:{is_admin:true},states:{...window.fixture.states,
     'sensor.real_pv':window.fixture.states['sensor.total_dc_power'],
     'sensor.real_profile':window.fixture.states['sensor.solar_yield_forecast_power_profile_today'],
     'sensor.real_today':window.fixture.states['sensor.solar_yield_forecast_today']},
     callService:async(domain,service,data)=>{window.recalculateCall={domain,service,data};},
     connection:{sendMessagePromise:async message=>{window.panelMessages.push(message);return message.type==='lovelace/dashboards/list'?[]:{}}}};
   document.body.append(panel);window.panelFixture=panel;
 },panelTag);
 await page.waitForFunction(()=>window.panelMessages.some(message=>message.type==='lovelace/config/save'));
 const managed=await page.evaluate(()=>{
   const card=window.panelFixture.shadowRoot.querySelector('solar-comparison-card');
   const saved=window.panelMessages.find(message=>message.type==='lovelace/config/save');
   const settings=window.panelFixture.shadowRoot.querySelector('.settings');
   return {pv:card.config.pv_entity,energy:card.config.energy_entity,views:saved.config.views,created:window.panelMessages.some(message=>message.type==='lovelace/dashboards/create'),settingsHidden:settings.hidden,settingsTitle:settings.title};
 });
 assert.equal(managed.pv,'sensor.real_pv');assert.equal(managed.energy,'sensor.real_energy');
 assert.equal(managed.settingsHidden,false);assert.equal(managed.settingsTitle,'Настройки');
 await page.evaluate(()=>{const panel=window.panelFixture;panel.hass={...panel.hass,language:'en'};});
 assert.equal(await page.locator(panelTag).locator('.settings').getAttribute('title'),'Settings');
 assert.equal(await page.locator(panelTag).locator('.recalculate').count(),0);
 assert.ok(managed.created);assert.ok(Array.isArray(managed.views));assert.equal(managed.views[0].cards.length,1);
 assert.deepEqual(errors,[]);await browser.close();console.log('Browser: curves, readable fonts, responsive bars, hover, compact, invalid timestamps, refresh failure passed');
})().catch(e=>{console.error(e);process.exit(1)});
