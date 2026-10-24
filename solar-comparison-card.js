/* Solar Comparison Card: day-aligned Sungrow power and 30-day forecast. */
// Integrate recorder states as a step function, splitting at UTC quarter hours.
// Unknown/unavailable gaps up to ten minutes are linearly bridged; longer
// gaps break coverage so missing measurements are never hidden.
function solarQuarterHours(rows, unit, now = Date.now()) {
  const step = 900000, maxInterpolatedGap = 600000, bins = new Map();
  const samples = rows.map(s => ({time: Date.parse(s.last_updated || s.last_changed),
    value: s.state === null || s.state === '' ? NaN : Number(s.state),
    unit: String(s.attributes?.unit_of_measurement || unit).toLowerCase()}))
    .filter(s => Number.isFinite(s.time)).sort((a,b) => a.time-b.time);
  const watts = s => Number.isFinite(s?.value) && s.value >= 0 && ['kw','w'].includes(s.unit)
    ? s.value * (s.unit === 'kw' ? 1000 : 1) : NaN;
  const addSegment = (segmentStart, end, fromWatts, toWatts=fromWatts) => {
    const duration=end-segmentStart;
    for (let t=segmentStart; t<end;) {
      const binStart = Math.floor(t/step)*step, stop = Math.min(end,binStart+step);
      const bin = bins.get(binStart) || {energy:0, covered:0};
      // Integrate the linear bridge exactly over this part of the quarter.
      const a=duration ? (t-segmentStart)/duration : 0;
      const b=duration ? (stop-segmentStart)/duration : 0;
      bin.energy += ((fromWatts+(toWatts-fromWatts)*a)+(fromWatts+(toWatts-fromWatts)*b))/2*(stop-t);
      bin.covered += stop-t;
      bins.set(binStart,bin); t=stop;
    }
  };
  for (let i=0;i<samples.length;i++) {
    const currentWatts=watts(samples[i]);
    if (Number.isFinite(currentWatts)) {
      addSegment(samples[i].time,Math.min(samples[i+1]?.time ?? now,now),currentWatts);
      continue;
    }
    const gapStart=samples[i].time;
    let lastInvalid=i;
    while (lastInvalid+1<samples.length && !Number.isFinite(watts(samples[lastInvalid+1]))) lastInvalid++;
    const previous=samples[i-1], next=samples[lastInvalid+1];
    const previousWatts=watts(previous), nextWatts=watts(next);
    if (Number.isFinite(previousWatts) && Number.isFinite(nextWatts) &&
        next.time-gapStart<=maxInterpolatedGap) {
      addSegment(gapStart,Math.min(next.time,now),previousWatts,nextWatts);
    }
    i=lastInvalid;
  }
  return [...bins].filter(([t,b]) => t+step<=now && b.covered===step)
    .map(([t,b]) => ({time:t+step/2, power_w:b.energy/step, energy_kwh:b.energy/3600000000}));
}
// Shape-preserving cubic curves pass through every measured point. Limiting
// tangents avoids invented peaks/negative power; missing quarters stay gaps.
// This changes only SVG geometry, never the interval values or energy totals.
function solarSmoothPath(points, x, y, smooth = true, baseline = null) {
  const groups = [];
  for (const point of points) {
    const group = groups[groups.length - 1], previous = group?.[group.length - 1];
    if (!previous || point[0] <= previous[0] || point[0] - previous[0] > .26) groups.push([point]);
    else group.push(point);
  }
  const xy = p => `${x(p[0]).toFixed(2)},${y(p[1]).toFixed(2)}`;
  return groups.map(group => {
    let path = 'M' + xy(group[0]);
    const slopes = group.slice(1).map((p, i) => (p[1] - group[i][1]) / (p[0] - group[i][0]));
    const tangent = group.map((p, i) => {
      if (i === 0) return slopes[0] || 0;
      if (i === group.length - 1) return slopes[i - 1] || 0;
      const a = slopes[i - 1], b = slopes[i];
      return a * b > 0 ? 2 * a * b / (a + b) : 0;
    });
    for (let i = 1; i < group.length; i++) {
      const a = group[i - 1], b = group[i], dx = (b[0] - a[0]) / 3;
      path += smooth ? ` C${xy([a[0] + dx, a[1] + dx * tangent[i - 1]])} ${xy([b[0] - dx, b[1] - dx * tangent[i]])} ${xy(b)}` : ' L' + xy(b);
    }
    // Close each contiguous section separately so the fill cannot bridge gaps
    // or extend today's observations into the forecast part of the day.
    if (baseline !== null) path += ` L${xy([group[group.length - 1][0], baseline])} L${xy([group[0][0], baseline])} Z`;
    return path;
  }).join(' ');
}
function solarTimeLabel(hour) {
  const minutes=Math.max(0,Math.min(1440,Math.round(hour*60)));
  return String(Math.floor(minutes/60)).padStart(2,'0')+':'+String(minutes%60).padStart(2,'0');
}
// Preserve the card and controls: replacing the entire shadow tree resets
// scrolling/focus in the HA mobile webview, especially in expanded mode.
function solarPatch(parent, template) {
  [...template.childNodes].forEach((next,i)=>{
    const old=parent.childNodes[i];
    if(!old){parent.append(next.cloneNode(true));return;}
    if(old.nodeType!==next.nodeType||old.nodeName!==next.nodeName||next.classList?.contains('chart-wrap')){
      old.replaceWith(next.cloneNode(true));return;
    }
    if(next.nodeType===3){if(old.textContent!==next.textContent)old.textContent=next.textContent;return;}
    if(next.nodeType!==1)return;
    for(const attr of [...old.attributes])if(!next.hasAttribute(attr.name))old.removeAttribute(attr.name);
    for(const attr of [...next.attributes])if(old.getAttribute(attr.name)!==attr.value)old.setAttribute(attr.name,attr.value);
    if(next.tagName==='INPUT'&&old.value!==next.value)old.value=next.value;
    solarPatch(old,next);
  });
  while(parent.childNodes.length>template.childNodes.length)parent.lastChild.remove();
}
const solarDay = (date,timeZone='Asia/Jerusalem') => new Intl.DateTimeFormat('en-CA', {timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
function solarShift(day, amount, unit='day') {
  const d=new Date(day+'T12:00:00Z');
  if(unit==='month'){d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+amount);}
  else if(unit==='year'){d.setUTCMonth(0,1);d.setUTCFullYear(d.getUTCFullYear()+amount);}
  else d.setUTCDate(d.getUTCDate()+amount);
  return d.toISOString().slice(0,10);
}
// Convert a local calendar midnight with the offset at that date (including DST).
function solarMidnight(day,timeZone='Asia/Jerusalem') {
  let t=Date.parse(day+'T00:00:00Z');
  for(let i=0;i<3;i++){
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(t));
    const v=Object.fromEntries(parts.map(p=>[p.type,p.value]));
    t+=Date.parse(day+'T00:00:00Z')-Date.parse(`${v.year}-${v.month}-${v.day}T${v.hour}:${v.minute}:${v.second}Z`);
  }
  return t;
}
class SolarComparisonCard extends HTMLElement {
  connectedCallback() {
    this._resizeObserver = new ResizeObserver(() => this._render());
    this._resizeObserver.observe(this);
  }
  disconnectedCallback() { this._resizeObserver?.disconnect(); }
  static getStubConfig() { return {size:'wide'}; }

  setConfig(config) {
    this.config = {
      title: 'Солнечные панели',
      pv_entity: 'sensor.total_dc_power',
      forecast_entity: 'sensor.solar_yield_forecast_power_profile_today',
      day_forecast_entity: 'sensor.solar_yield_forecast_today',
      energy_entity: 'sensor.daily_pv_generation',
      size: 'wide',
      smooth: true,
      ...config
    };
    this._root = this.shadowRoot || this.attachShadow({mode: 'open'});
    this._history = null;
    this._compact = this.config.size === 'compact';
    this._date = '';
    this._selected=solarDay(new Date());this._period='day';this._view=[0,24];this._visible=[true,true,true];this._forecastRange=8;
    this._render();
  }
  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (!this._root) return;
    const today=solarDay(new Date(),this._timeZone());
    if(!previous)this._selected=today;
    if (this._date !== today || (!this._loading && (!this._lastFetch || Date.now() - this._lastFetch > 300000))) {
      this._date = today;
      this._fetch();
    }
    if (!previous || [this.config.forecast_entity, this.config.day_forecast_entity].some(id => previous.states[id] !== hass.states[id])) this._render();
  }
  _timeZone(){
    return this.config?.time_zone||this._hass?.states?.[this.config?.day_forecast_entity]?.attributes?.site_configuration?.time_zone||this._hass?.config?.time_zone||Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
  }
  async _fetch() {
    if (!this._hass || this._period!=='day') return;
    const request=(this._request||0)+1;this._request=request;
    this._loading = true;
    this._lastFetch = Date.now();
    try {
      const state = this._hass.states[this.config.pv_entity];
      const tz=this._timeZone();
      const end = new Date(Math.min(Date.now(),solarMidnight(solarShift(this._selected,1),tz)));
      const start = new Date(solarMidnight(solarShift(this._selected,-1),tz));
      this._historyEnd=end.getTime();
      if(start>=end){this._history=[];this._loading=false;this._render();return;}
      const url = 'history/period/' + encodeURIComponent(start.toISOString()) +
        '?filter_entity_id=' + encodeURIComponent(this.config.pv_entity) +
        '&end_time=' + encodeURIComponent(end.toISOString()) + '&minimal_response';
      const rows = await this._hass.callApi('GET', url);
      if(request!==this._request)return;
      this._error = null;
      this._history = Array.isArray(rows) ? (rows[0] || []) : [];
    } catch (e) {
      if(request!==this._request)return;
      this._error = e?.message || e?.body?.message || (typeof e === 'string' ? e : 'Не удалось обновить историю. Повторная попытка через 5 минут.');
      this._history = this._history || [];
    }
    this._loading = false;
    this._render();
  }
  _svg() {
    const tz=this._timeZone();
    const f=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
    const dayFmt=new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'});
    const today=this._selected;
    const yesterday=solarShift(today,-1);
    const actual=[[],[]];
    const unit=(this._hass?.states?.[this.config.pv_entity]?.attributes?.unit_of_measurement||'W').toLowerCase();
    for(const point of solarQuarterHours(this._history||[], unit, this._historyEnd||Date.now())) {
      const d=new Date(point.time), day=dayFmt.format(d);
      const idx=day===today?1:(day===yesterday?0:-1);
      if(idx<0)continue;
      const parts=f.format(d).split(':').map(Number);
      actual[idx].push([parts[0]+parts[1]/60+d.getSeconds()/3600,point.power_w]);
    }
    const points=[...(this._hass?.states?.[this.config.forecast_entity]?.attributes?.points||[]),...(this._hass?.states?.[this.config.forecast_entity.replace(/today$/, 'tomorrow')]?.attributes?.points||[])];
    const forecast=points.filter(p=>Number.isFinite(Date.parse(p.time)) && dayFmt.format(new Date(p.time))===today && p.power_w!==null).map(p=>{
      const d=new Date(p.time);
      const a=f.format(d).split(':').map(Number);
      return [a[0]+a[1]/60+d.getSeconds()/3600,Number(p.power_w)];
    }).filter(x=>Number.isFinite(x[0])&&Number.isFinite(x[1]));
    const series=[actual[0],actual[1],forecast].map((line,i)=>this._visible[i]?line:[]);
    this._series=series;
    const max=Math.max(1000,...series.flat().map(p=>p[1]))*1.08;
    const W=Math.max(240,Math.round(this.getBoundingClientRect().width||850)-32),H=this.config?.size==='compact'?260:350,l=52,r=26,t=28,b=40;
    this._plotGeometry={W,H,l,r,t,b};
    const [lo,hi]=this._view;
    const xx=x=>l+(W-l-r)*(x-lo)/(hi-lo);
    const yy=y=>t+(H-t-b)*(1-y/max);
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Мощность вчера, сегодня и прогноз">';
    for(let i=0;i<=4;i++){
      const y=max*i/4,py=yy(y);
      svg+='<line x1="'+l+'" x2="'+(W-r)+'" y1="'+py+'" y2="'+py+'" stroke="#88929a" opacity=".20"/>';
      svg+='<text x="'+(l-8)+'" y="'+(py+4)+'" text-anchor="end" fill="currentColor" font-size="13">'+(y/1000).toFixed(1)+'</text>';
    }
    svg+='<text x="'+l+'" y="14" fill="currentColor" font-size="12">кВт</text>';
    for(let h=lo;h<=hi+.001;h+=(hi-lo)/(W<540?4:8))svg+='<text x="'+xx(h)+'" y="'+(H-14)+'" text-anchor="middle" fill="currentColor" font-size="13">'+solarTimeLabel(h)+'</text>';
    svg+='<defs><clipPath id="plot-clip"><rect x="'+l+'" y="'+t+'" width="'+(W-l-r)+'" height="'+(H-t-b)+'"/></clipPath></defs><g clip-path="url(#plot-clip)">';
    const colors=['#3478f6','#ff9e3d','#16a06a'];
    series.forEach(line=>line.sort((a,b)=>a[0]-b[0]));
    if(this._visible[1] && actual[1].length)svg+='<path class="today-area" d="'+solarSmoothPath(actual[1],xx,yy,this.config.smooth!==false,0)+'" fill="'+colors[1]+'" fill-opacity="0.22" stroke="none"/>';
    series.forEach((line,i)=>{
      if(!line.length)return;
      if(i<2)for(let j=1;j<line.length;j++){
        const a=line[j-1],b=line[j],gap=b[0]-a[0];
        if(gap>.26&&gap<=1)svg+='<path class="history-gap" d="M'+xx(a[0])+','+yy(a[1])+' L'+xx(b[0])+','+yy(b[1])+'" fill="none" stroke="'+colors[i]+'" stroke-width="2" stroke-dasharray="4 5" opacity=".65"><title>Пропуск измерений — соединение для ориентира</title></path>';
      }
      const d=solarSmoothPath(line,xx,yy,this.config.smooth!==false);
      svg+='<path class="series-line" data-series="'+['yesterday','today','forecast'][i]+'" d="'+d+'" fill="none" stroke="'+colors[i]+'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
    });
    svg+='</g>';
    svg+='<line class="cursorline" x1="0" y1="'+t+'" x2="0" y2="'+(H-b)+'" stroke="currentColor" stroke-dasharray="4 4" opacity="0"/>';
    svg+='</svg>';
    return svg;
  }
  _render(){
    if(!this._root||!this._hass||this._touching)return;
    const todayForecast=this._hass.states[this.config.day_forecast_entity];
    const allDays=todayForecast?.attributes?.daily_forecast||[];
    const days=allDays.slice(0,this._forecastRange||8);
    const max=Math.max(1,...days.map(d=>Number(d.kwh)||0));
    const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
    const scroll=[];
    for(let el=this;el;el=el.parentElement||el.getRootNode()?.host){scroll.push([el,el.scrollLeft,el.scrollTop]);}
    const template=document.createElement('template');
    template.innerHTML=`
      <style>
      :host{display:block;color:var(--primary-text-color,#263238);font-family:var(--ha-font-family-body,Roboto,system-ui,-apple-system,"Segoe UI",sans-serif);font-size:14px;line-height:1.5;font-variant-numeric:tabular-nums}
      ha-card{display:block;box-sizing:border-box;padding:16px;overflow:hidden;container-type:inline-size}
      :host{width:100%;min-width:0}
      .bars{min-width:0}
      h3{margin:0 0 12px;font-size:20px;line-height:1.35;font-weight:600;letter-spacing:-.2px}
      .legend{display:flex;gap:20px;flex-wrap:wrap;font-size:14px;color:var(--secondary-text-color,#59656e);margin-bottom:12px}
      .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
      .chart-wrap{position:relative;max-width:100%;width:100%;overflow:visible}
      svg{width:100%;height:auto;display:block;color:var(--secondary-text-color,#59656e)}
      .chart-tooltip{position:absolute;z-index:10;pointer-events:none;background:var(--card-background-color,#fff);color:var(--primary-text-color,#263238);box-shadow:0 4px 18px #0002;border:1px solid var(--divider-color,#dde2e5);border-radius:10px;padding:12px 16px;font-size:14px;line-height:1.6;display:none;white-space:nowrap;max-width:100%;box-sizing:border-box}
      .chart-tooltip>b{display:block;margin-bottom:4px;font-weight:600}
      .bars{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:12px;align-items:end;height:160px;margin-top:16px}
      .bars.month{height:auto;row-gap:20px}.bars.month .day{height:150px}
      .day{display:flex;flex-direction:column;align-items:center;justify-content:end;height:100%;gap:8px;font-size:12px}
      .day>b{font-size:14px;font-weight:600}
      .day>span{color:var(--secondary-text-color,#59656e)}
      .bar{width:100%;max-width:54px;background:#18a58c;border-radius:5px 5px 0 0;min-height:2px}.day.ensemble .bar{opacity:.68;background:repeating-linear-gradient(135deg,#18a58c 0 6px,#50b9a7 6px 10px)}
      .small{font-size:12px;line-height:1.6;color:var(--secondary-text-color,#59656e);margin:20px 0 0}
      .more{margin-top:20px;font-size:18px}
      .forecast-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:20px}.forecast-head .more{margin:0}
      .forecast-range{display:flex;gap:4px;background:var(--secondary-background-color,#f6f6f6);border-radius:22px;padding:2px;flex:none}.forecast-range button{min-height:36px;padding:5px 10px;font-size:12px}.forecast-range button[aria-pressed=true]{background:var(--card-background-color,#fff);box-shadow:0 1px 4px #0002;font-weight:600}
      .unit{font-size:13px;font-weight:400;color:var(--secondary-text-color,#59656e);white-space:nowrap}
      @container(max-width:540px){h3{font-size:18px}.bars{gap:8px;grid-template-columns:repeat(4,minmax(0,1fr));height:auto;row-gap:20px}.day{height:150px}.chart-tooltip{white-space:normal}}
      button{font:inherit;cursor:pointer;color:inherit;border:0;background:transparent;min-height:44px;border-radius:24px;padding:8px 14px}
      button:focus-visible,input:focus-visible{outline:2px solid #ff8800;outline-offset:2px}
      .periods{display:flex;gap:6px;overflow:auto;margin:12px 0;border-bottom:1px solid var(--divider-color,#eee);padding-bottom:12px}
      .periods button{white-space:nowrap;background:var(--secondary-background-color,#f6f6f6)}
      .periods button[aria-pressed=true]{background:#ff880018;color:#f58200;font-weight:600}
      .date-nav{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0}
      .date-nav input{font:inherit;color:inherit;background:transparent;border:0;max-width:65%;text-align:center}
      .tools{display:flex;justify-content:flex-end;gap:4px}.tools button{font-size:13px}
      .chart-wrap{touch-action:pan-y}.chart-wrap.zoomed{touch-action:none}
      .legend{margin:16px 0;gap:8px}.legend button[hidden]{display:none}.legend button{display:flex;align-items:center;gap:8px;padding:6px}
      .toggle{width:34px;height:20px;border-radius:12px;background:var(--series);position:relative}.toggle:after{content:'';position:absolute;width:16px;height:16px;top:2px;right:2px;background:white;border-radius:50%}
      [aria-pressed=false] .toggle{background:#aaa}[aria-pressed=false] .toggle:after{right:16px}
      :host([expanded]){position:fixed;inset:0;z-index:1000;background:var(--card-background-color,white);overflow:auto}
      .summary{display:flex;flex-wrap:wrap;gap:16px;font-size:16px;margin:12px 0}.empty{text-align:center;padding:20px;color:var(--secondary-text-color,#777)}
      </style><ha-card><h3>${esc(this.config.title)}</h3>
      <div class="periods">${[['day','День'],['week','Неделя'],['month','Месяц'],['year','Год'],['all','Всё время']].map(([key,label])=>`<button data-period="${key}" aria-pressed="${this._period===key}">${label}</button>`).join('')}</div>
      <div class="date-nav"><button data-step="-1" aria-label="Предыдущий период" ${this._period==='all'?'disabled':''}>❮</button><input aria-label="Выбрать дату" type="date" value="${this._selected}"><button data-step="1" aria-label="Следующий период" ${this._period==='all'?'disabled':''}>❯</button></div>
      <div class="tools"><button class="now">Сегодня</button><button class="reset">Сбросить Zoom</button><button class="expand" aria-label="Развернуть график">${this.hasAttribute('expanded')?'Свернуть':'⛶'}</button></div>
      <div class="chart-wrap ${this._view[1]-this._view[0]<24?'zoomed':''}">${this._period==='day'?this._svg():this._energySvg()}<div class="chart-tooltip"></div></div>
      <div class="legend">${['Предыдущий день','PV · факт','Прогноз'].map((label,i)=>`<button ${i===0&&this._period!=='day'?'hidden':''} data-toggle="${i}" aria-pressed="${this._visible[i]}" style="--series:${['#3478f6','#ff9e3d','#16a06a'][i]}"><span class="toggle"></span>${label}</button>`).join('')}</div>
      ${this._period==='day'&&!this._series.some(x=>x.length)?'<div class="empty">Нет данных за выбранную дату</div>':''}
      ${this._loading?'<div class="small">Загрузка истории…</div>':''}
      <div class="forecast-head"><h3 class="more">Прогноз выработки на ${this._forecastRange===30?'30':'8'} дней <span class="unit">· кВт·ч</span></h3><div class="forecast-range"><button data-forecast-range="8" aria-pressed="${this._forecastRange!==30}">8 дней</button><button data-forecast-range="30" aria-pressed="${this._forecastRange===30}">Месяц</button></div></div>
      <div class="bars ${this._forecastRange===30?'month':''}">${days.map(d=>`<div class="day ${d.source==='ensemble'?'ensemble':''}" title="${d.source==='ensemble'?'Дальний ансамблевый прогноз — точность ниже':'Основной прогноз погоды'}"><b>${esc(d.kwh)} </b><div class="bar" style="height:${Math.max(2,100*(Number(d.kwh)||0)/max)}px"></div><span>${esc((d.date||'').slice(5))}</span></div>`).join('')}</div>
      <p class="small">Разведите два пальца для увеличения графика дня; после увеличения перемещайте его пальцем. Двойное нажатие сбрасывает масштаб. Мощность усреднена за 15 минут. ${this.config.smooth!==false?'Линии сглажены; значения в подсказках и энергия рассчитаны по исходным точкам. ':''}Технические пропуски до 10 минут линейно восстанавливаются между соседними измерениями; более длинные пропуски остаются пустыми. Полосатые столбцы после основного горизонта — менее точный ансамблевый прогноз GFS.</p>
      ${this._error?'<p class="small">История: '+esc(this._error)+'</p>':''}
      </ha-card>`;
    solarPatch(this._root,template.content);
    for(const [el,x,y] of scroll){el.scrollLeft=x;el.scrollTop=y;}
    this._bindControls();
    const wrapper=this._root.querySelector('.chart-wrap'), svg=wrapper?.querySelector('svg');
    const tip=wrapper?.querySelector('.chart-tooltip'), guide=wrapper?.querySelector('.cursorline');
    if(svg && tip && this._period==='day'){
      this._bindZoom(wrapper);
      const move=ev=>{
        if(this._touching)return;
        const rect=svg.getBoundingClientRect();
        const g=this._plotGeometry||{W:850,l:55,r:16};
        const px=Math.max(g.l,Math.min(g.W-g.r,(ev.clientX-rect.left)*g.W/rect.width));
        const hour=Math.min(23.875,Math.floor((this._view[0]+(px-g.l)/(g.W-g.l-g.r)*(this._view[1]-this._view[0]))*4)/4+0.125);
        const near=(line)=>{
          if(!line?.length)return null;
          let p=line.reduce((a,b)=>Math.abs(a[0]-hour)<Math.abs(b[0]-hour)?a:b);
          return Math.abs(p[0]-hour)<=0.126?p[1]:null;
        };
        const values=(this._series||[]).map(near);
        if(values.every(v=>v===null)){tip.style.display='none';if(guide)guide.setAttribute('opacity','0');return;}
        const timeHour=Math.floor(hour),timeMin=Math.floor((hour-timeHour)*4)*15;
        tip.innerHTML='<b>'+String((timeHour+Math.floor(timeMin/60))%24).padStart(2,'0')+':'+String(timeMin%60).padStart(2,'0')+'</b><div><span aria-hidden="true" style="color:#3478f6">●</span> Предыдущий день: '+(values[0]===null?'—':(values[0]/1000).toFixed(2)+' кВт')+'</div><div><span aria-hidden="true" style="color:#e0aa12">●</span> PV (факт): '+(values[1]===null?'—':(values[1]/1000).toFixed(2)+' кВт')+'</div><div><span aria-hidden="true" style="color:#16a06a">●</span> Прогноз: '+(values[2]===null?'—':(values[2]/1000).toFixed(2)+' кВт')+'</div>';
        if(values[1]!==null) tip.innerHTML+='<div>Энергия за 15 мин: '+(values[1]/4000).toFixed(3)+' кВт·ч</div>';
        if(values[1]!==null && values[2]>0) tip.innerHTML+='<div>Отклонение: '+(100*(values[1]-values[2])/values[2]).toFixed(1)+'%</div>';
        tip.style.display='block';
        tip.style.left=Math.max(0,Math.min(rect.width-tip.offsetWidth,(ev.clientX-rect.left)+12))+'px';
        tip.style.top='8px';
        if(guide){guide.setAttribute('x1',px);guide.setAttribute('x2',px);guide.setAttribute('opacity','0.5');}
      };
      svg.addEventListener('pointermove',move);
      svg.addEventListener('pointerdown',move);
      svg.addEventListener('pointerleave',()=>{tip.style.display='none';if(guide)guide.setAttribute('opacity','0');});
    }
  }
  _select(day, period=this._period){
    if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isFinite(Date.parse(day)))return;
    this._selected=day;this._period=period;this._view=[0,24];this._history=[];this._error=null;
    this._request=(this._request||0)+1;this._loading=false;
    this._fetch();this._render();
  }
  _bindControls(){
    this._root.querySelectorAll('[data-period]').forEach(el=>el.onclick=()=>this._select(this._selected,el.dataset.period));
    this._root.querySelectorAll('[data-step]').forEach(el=>el.onclick=()=>this._select(solarShift(this._selected,Number(el.dataset.step)*(this._period==='week'?7:1),this._period)));
    this._root.querySelector('input[type=date]').onchange=ev=>this._select(ev.target.value);
    this._root.querySelector('.now').onclick=()=>this._select(solarDay(new Date(),this._timeZone()));
    this._root.querySelector('.reset').onclick=()=>{this._view=[0,24];this._render();};
    this._root.querySelector('.expand').onclick=()=>{this.toggleAttribute('expanded');this._render();};
    this._root.querySelectorAll('[data-toggle]').forEach(el=>el.onclick=()=>{const i=Number(el.dataset.toggle);this._visible[i]=!this._visible[i];this._render();});
    this._root.querySelectorAll('[data-forecast-range]').forEach(el=>el.onclick=()=>{this._forecastRange=Number(el.dataset.forecastRange);this._render();});
    this._root.querySelectorAll('[data-date]').forEach(el=>{
      const open=()=>this._select(el.dataset.date,this._period==='year'||this._period==='all'?'month':'day');
      el.onclick=open;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};
    });
  }
  _energySvg(){
    const attrs=this._hass.states[this.config.day_forecast_entity]?.attributes||{};
    const actual=attrs.daily_actuals||{}, forecast=Object.fromEntries((attrs.daily_forecast||[]).map(d=>[d.date,d.kwh]));
    let start=this._selected,end;
    if(this._period==='week'){
      const weekday=new Date(start+'T12:00:00Z').getUTCDay();start=solarShift(start,-((weekday+6)%7));end=solarShift(start,7);
    }else if(this._period==='month'){start=start.slice(0,7)+'-01';end=solarShift(start,1,'month');}
    else if(this._period==='year'){start=start.slice(0,4)+'-01-01';end=solarShift(start,1,'year');}
    else{start=Object.keys({...actual,...forecast}).sort()[0]||start;end=solarShift(Object.keys({...actual,...forecast}).sort().at(-1)||start,1);}
    const groups=new Map(),monthly=['year','all'].includes(this._period);
    for(let day=start;day<end;day=solarShift(day,1)){
      const key=monthly?day.slice(0,7)+'-01':day;
      const g=groups.get(key)||{date:key,a:null,f:null,count:0};
      if(actual[day]!=null&&Number.isFinite(Number(actual[day]))){g.a=(g.a??0)+Number(actual[day]);g.count++;}
      if(forecast[day]!=null&&Number.isFinite(Number(forecast[day])))g.f=(g.f??0)+Number(forecast[day]);
      groups.set(key,g);
    }
    const rows=[...groups.values()],W=Math.max(240,Math.round(this.getBoundingClientRect().width||850)-32),H=300,l=46,r=12,b=50,t=26;
    const max=Math.max(1,...rows.flatMap(d=>[this._visible[1]?d.a:0,this._visible[2]?d.f:0]))*1.1;
    const x=i=>l+(W-l-r)*(i+.5)/Math.max(1,rows.length),y=v=>H-b-(H-t-b)*v/max;
    const bw=Math.max(1,Math.min(28,(W-l-r)/Math.max(1,rows.length)*.35));
    let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Выработка за выбранный период"><text x="${l}" y="16" fill="currentColor" font-size="12">кВт·ч</text>`;
    for(let i=0;i<=4;i++)svg+=`<line x1="${l}" x2="${W-r}" y1="${y(max*i/4)}" y2="${y(max*i/4)}" stroke="currentColor" opacity=".12"/><text x="${l-6}" y="${y(max*i/4)+4}" text-anchor="end" fill="currentColor" font-size="11">${(max*i/4).toFixed(0)}</text>`;
    rows.forEach((d,i)=>{
      const label=`${d.date}: факт ${d.a===null?'нет данных':d.a.toFixed(1)+' кВт·ч'}, прогноз ${d.f===null?'нет данных':d.f.toFixed(1)+' кВт·ч'}${monthly?', дней с данными: '+d.count:''}`;
      svg+=`<g data-date="${d.date}" tabindex="0" role="button" aria-label="${label}"><title>${label}</title><rect x="${x(i)-bw}" y="${t}" width="${bw*2}" height="${H-b-t}" fill="transparent"/>`;
      if(d.a!==null&&this._visible[1])svg+=`<rect x="${x(i)-bw}" y="${y(d.a)}" width="${bw}" height="${Math.max(1,H-b-y(d.a))}" rx="2" fill="#ff9e3d"/>`;
      if(d.f!==null&&this._visible[2])svg+=`<rect x="${x(i)}" y="${y(d.f)}" width="${bw}" height="${Math.max(1,H-b-y(d.f))}" rx="2" fill="#16a06a"/>`;
      if(i%Math.max(1,Math.ceil(rows.length/(W<540?7:14)))===0)svg+=`<text x="${x(i)}" y="${H-24}" text-anchor="middle" font-size="11" fill="currentColor">${monthly?d.date.slice(2,7):d.date.slice(8)}</text>`;
      svg+='</g>';
    });
    svg+='</svg>';
    return `<div class="summary">${start} — ${solarShift(end,-1)}</div>${svg}<div class="small">Факт: ${rows.some(d=>d.a!==null)?rows.reduce((sum,d)=>sum+(d.a||0),0).toFixed(1)+' кВт·ч':'нет данных'}. Показаны только сохранённые дни; неполные периоды не являются полным итогом. Нажмите столбец, чтобы открыть период.</div>`;
  }
  _bindZoom(wrapper){
    const fraction=clientX=>{
      const rect=wrapper.getBoundingClientRect(),g=this._plotGeometry;
      return Math.max(0,Math.min(1,((clientX-rect.left)*g.W/rect.width-g.l)/(g.W-g.l-g.r)));
    };
    const redraw=(lo,span)=>{
      span=Math.max(1,Math.min(24,span));lo=Math.max(0,Math.min(24-span,lo));this._view=[lo,lo+span];
      wrapper.classList.toggle('zoomed',span<24);
      // Keep the touch target and its listeners mounted for the entire gesture.
      const old=wrapper.querySelector('svg');
      const doc=new DOMParser().parseFromString(this._svg(),'image/svg+xml');
      // Patch descendants in place; Safari keeps delivering to the original target.
      solarPatch(old,doc.documentElement);
      wrapper.querySelector('.chart-tooltip').style.display='none';
    };
    let gesture;
    wrapper.addEventListener('touchstart',e=>{
      this._touching=true;
      const touches=[...e.touches];
      gesture={view:[...this._view],x:touches[0].clientX};
      if(touches.length===2){
        gesture.distance=Math.max(1,Math.hypot(touches[1].clientX-touches[0].clientX,touches[1].clientY-touches[0].clientY));
        gesture.center=fraction((touches[0].clientX+touches[1].clientX)/2);e.preventDefault();
      }
    },{passive:false});
    wrapper.addEventListener('touchmove',e=>{
      if(!gesture)return;
      const span=gesture.view[1]-gesture.view[0];
      if(e.touches.length===2&&gesture.distance){
        e.preventDefault();
        const next=Math.max(1,Math.min(24,span*gesture.distance/Math.max(1,Math.hypot(e.touches[1].clientX-e.touches[0].clientX,e.touches[1].clientY-e.touches[0].clientY))));
        redraw(gesture.view[0]+gesture.center*span-fraction((e.touches[0].clientX+e.touches[1].clientX)/2)*next,next);
      }else if(e.touches.length===1&&span<24){e.preventDefault();redraw(gesture.view[0]+(fraction(gesture.x)-fraction(e.touches[0].clientX))*span,span);}
    },{passive:false});
    const finish=e=>{
      if(!e.touches.length){gesture=null;this._touching=false;this._render();}
      else if(e.touches.length===1){gesture={view:[...this._view],x:e.touches[0].clientX};}
    };
    wrapper.addEventListener('touchend',finish);wrapper.addEventListener('touchcancel',()=>{gesture=null;this._touching=false;this._render();});
    wrapper.ondblclick=()=>{this._view=[0,24];this._render();};
    wrapper.addEventListener('wheel',e=>{
      if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();
      const span=this._view[1]-this._view[0],next=Math.max(1,Math.min(24,span*Math.exp(e.deltaY*.005))),f=fraction(e.clientX);
      redraw(this._view[0]+f*(span-next),next);
      clearTimeout(this._zoomTimer);this._zoomTimer=setTimeout(()=>this._render(),150);
    },{passive:false});
  }
  getGridOptions(){return this.config?.size === 'compact' ? {columns:6,rows:6,min_rows:4} : {columns:'full',rows:8,min_rows:5};}
  getCardSize(){return this.config?.size === 'compact' ? 5 : 8;}
}
if(!customElements.get('solar-comparison-card'))customElements.define('solar-comparison-card',SolarComparisonCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(card=>card.type==='solar-comparison-card'))window.customCards.push({type:'solar-comparison-card',name:'Solar Comparison — широкий',description:'На всю ширину секции, три кривые и прогноз до 30 дней',preview:true,documentationURL:'https://github.com/EvgenyKrinets/solar-yield-forecast'});
if(!window.customCards.some(card=>card.type==='solar-comparison-compact'))window.customCards.push({type:'solar-comparison-compact',name:'Solar Comparison — компактный',description:'Компактный график для обычной колонки',preview:true});

class SolarComparisonCompactCard extends SolarComparisonCard {
  static getStubConfig() { return {size:'compact'}; }
  setConfig(config) {
    super.setConfig({ ...config, size: 'compact' });
  }
}
if(!customElements.get('solar-comparison-compact')) customElements.define('solar-comparison-compact', SolarComparisonCompactCard);

const SOLAR_PANEL_TAG='solar-yield-forecast-panel-v1-2-0';
const SOLAR_MANAGED_DASHBOARD='solar-yield-forecast-dashboard';

function solarPanelCardConfig(config={}) {
  return {
    type:'custom:solar-comparison-card',
    title:config.title||'Solar Yield Forecast',
    pv_entity:config.pv_entity||'sensor.total_dc_power',
    forecast_entity:config.forecast_entity||'sensor.solar_yield_forecast_power_profile_today',
    day_forecast_entity:config.day_forecast_entity||'sensor.solar_yield_forecast_today',
    energy_entity:config.energy_entity||'sensor.daily_pv_generation',
    time_zone:config.time_zone,
    size:'wide',
    smooth:true,
    solar_yield_forecast_managed:true
  };
}

function solarManagedDashboardConfig(config={}) {
  return {
    title:'Solar Yield Forecast',
    views:[{
      title:'Solar Yield Forecast',
      path:'overview',
      icon:'mdi:solar-power-variant',
      type:'panel',
      cards:[solarPanelCardConfig(config)]
    }]
  };
}

class SolarYieldForecastPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:'open'});
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;min-height:100%;box-sizing:border-box;background:var(--primary-background-color,#fafafa);color:var(--primary-text-color,#212121)}
      main{max-width:1280px;margin:0 auto;padding:20px;box-sizing:border-box}
      @media(max-width:600px){main{padding:8px}}
    </style><main></main>`;
  }
  set panel(value){this._panel=value;this._sync();}
  get panel(){return this._panel;}
  set hass(value){this._hass=value;this._sync();}
  get hass(){return this._hass;}
  _config(){return this._panel?.config||{};}
  _sync(){
    if(!this._hass)return;
    const config=solarPanelCardConfig(this._config());
    const signature=JSON.stringify(config);
    if(!this._card){
      this._card=document.createElement('solar-comparison-card');
      this._card.setConfig(config);
      this.shadowRoot.querySelector('main').append(this._card);
      this._signature=signature;
    }else if(this._signature!==signature){
      this._card.setConfig(config);this._signature=signature;
    }
    this._card.hass=this._hass;
    if(!this._dashboardStarted){
      this._dashboardStarted=true;
      this._ensureManagedDashboard().catch(error=>console.warn('Solar Yield Forecast: dashboard setup failed',error));
    }
  }
  async _ensureManagedDashboard(){
    if(!this._hass?.user?.is_admin)return;
    const raw=await this._hass.connection.sendMessagePromise({type:'lovelace/dashboards/list'});
    const dashboards=Array.isArray(raw)?raw:(raw?.dashboards||[]);
    const managed=solarManagedDashboardConfig(this._config());
    const existing=dashboards.find(item=>item.url_path===SOLAR_MANAGED_DASHBOARD);
    if(!existing){
      await this._hass.connection.sendMessagePromise({
        type:'lovelace/dashboards/create',
        url_path:SOLAR_MANAGED_DASHBOARD,
        title:'Solar Yield Forecast',
        icon:'mdi:solar-power-variant',
        show_in_sidebar:false,
        require_admin:false
      });
      await this._hass.connection.sendMessagePromise({
        type:'lovelace/config/save',url_path:SOLAR_MANAGED_DASHBOARD,config:managed
      });
      return;
    }
    try{
      const current=await this._hass.connection.sendMessagePromise({
        type:'lovelace/config',url_path:SOLAR_MANAGED_DASHBOARD
      });
      const card=current?.views?.[0]?.cards?.[0];
      if(!Array.isArray(current?.views)||card?.solar_yield_forecast_managed===true){
        await this._hass.connection.sendMessagePromise({
          type:'lovelace/config/save',url_path:SOLAR_MANAGED_DASHBOARD,config:managed
        });
      }
    }catch(_){
      await this._hass.connection.sendMessagePromise({
        type:'lovelace/config/save',url_path:SOLAR_MANAGED_DASHBOARD,config:managed
      });
    }
  }
}
if(!customElements.get(SOLAR_PANEL_TAG))customElements.define(SOLAR_PANEL_TAG,SolarYieldForecastPanel);
