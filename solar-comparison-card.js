/* Solar Comparison Card: day-aligned Sungrow power and 8-day forecast. */
// Integrate recorder states as a step function, splitting at UTC quarter hours.
// Unknown/unavailable states break coverage; incomplete intervals are not invented.
function solarQuarterHours(rows, unit, now = Date.now()) {
  const step = 900000, bins = new Map();
  const samples = rows.map(s => ({time: Date.parse(s.last_updated || s.last_changed),
    value: s.state === null || s.state === '' ? NaN : Number(s.state),
    unit: String(s.attributes?.unit_of_measurement || unit).toLowerCase()}))
    .filter(s => Number.isFinite(s.time)).sort((a,b) => a.time-b.time);
  samples.forEach((s,i) => {
    if (!Number.isFinite(s.value) || s.value < 0 || !['kw','w'].includes(s.unit)) return;
    const watts = s.value * (s.unit === 'kw' ? 1000 : 1);
    const end = Math.min(samples[i+1]?.time ?? now, now);
    for (let t=s.time; t<end;) {
      const start = Math.floor(t/step)*step, stop = Math.min(end,start+step);
      const bin = bins.get(start) || {energy:0, covered:0};
      bin.energy += watts*(stop-t); bin.covered += stop-t;
      bins.set(start,bin); t=stop;
    }
  });
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
class SolarComparisonCard extends HTMLElement {
  connectedCallback() {
    this._resizeObserver = new ResizeObserver(() => this._render());
    this._resizeObserver.observe(this);
  }
  disconnectedCallback() { this._resizeObserver?.disconnect(); }
  static getStubConfig() { return {size:'wide'}; }

  setConfig(config) {
    this.config = {
      title: 'Солнечные панели — вчера / сегодня / прогноз',
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
    this._render();
  }
  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (!this._root) return;
    const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Jerusalem', year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    if (this._date !== today || (!this._loading && (!this._lastFetch || Date.now() - this._lastFetch > 300000))) {
      this._date = today;
      this._fetch();
    }
    if (!previous || [this.config.forecast_entity, this.config.day_forecast_entity].some(id => previous.states[id] !== hass.states[id])) this._render();
  }
  async _fetch() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._lastFetch = Date.now();
    try {
      const state = this._hass.states[this.config.pv_entity];
      const end = new Date();
      const start = new Date(end.getTime() - 60*60*1000*54);
      const url = 'history/period/' + encodeURIComponent(start.toISOString()) +
        '?filter_entity_id=' + encodeURIComponent(this.config.pv_entity) +
        '&end_time=' + encodeURIComponent(end.toISOString()) + '&minimal_response';
      const rows = await this._hass.callApi('GET', url);
      this._error = null;
      this._history = Array.isArray(rows) ? (rows[0] || []) : [];
    } catch (e) {
      this._error = e?.message || e?.body?.message || (typeof e === 'string' ? e : 'Не удалось обновить историю. Повторная попытка через 5 минут.');
      this._history = this._history || [];
    }
    this._loading = false;
    this._render();
  }
  _svg() {
    const tz='Asia/Jerusalem';
    const f=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
    const dayFmt=new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'});
    const today=dayFmt.format(new Date());
    const yesterday=dayFmt.format(new Date(Date.now()-86400000));
    const actual=[[],[]];
    const unit=(this._hass?.states?.[this.config.pv_entity]?.attributes?.unit_of_measurement||'W').toLowerCase();
    for(const point of solarQuarterHours(this._history||[], unit)) {
      const d=new Date(point.time), day=dayFmt.format(d);
      const idx=day===today?1:(day===yesterday?0:-1);
      if(idx<0)continue;
      const parts=f.format(d).split(':').map(Number);
      actual[idx].push([parts[0]+parts[1]/60+d.getSeconds()/3600,point.power_w]);
    }
    const points=this._hass?.states?.[this.config.forecast_entity]?.attributes?.points||[];
    const forecast=points.filter(p=>Number.isFinite(Date.parse(p.time)) && dayFmt.format(new Date(p.time))===today && p.power_w!==null).map(p=>{
      const d=new Date(p.time);
      const a=f.format(d).split(':').map(Number);
      return [a[0]+a[1]/60+d.getSeconds()/3600,Number(p.power_w)];
    }).filter(x=>Number.isFinite(x[0])&&Number.isFinite(x[1]));
    const series=[actual[0],actual[1],forecast];
    this._series=series;
    const max=Math.max(1000,...series.flat().map(p=>p[1]))*1.08;
    const W=Math.max(240,Math.round(this.getBoundingClientRect().width||850)-32),H=this.config?.size==='compact'?260:350,l=52,r=26,t=28,b=40;
    this._plotGeometry={W,H,l,r,t,b};
    const xx=x=>l+(W-l-r)*x/24;
    const yy=y=>t+(H-t-b)*(1-y/max);
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Мощность вчера, сегодня и прогноз">';
    for(let i=0;i<=4;i++){
      const y=max*i/4,py=yy(y);
      svg+='<line x1="'+l+'" x2="'+(W-r)+'" y1="'+py+'" y2="'+py+'" stroke="#88929a" opacity=".20"/>';
      svg+='<text x="'+(l-8)+'" y="'+(py+4)+'" text-anchor="end" fill="currentColor" font-size="13">'+(y/1000).toFixed(1)+'</text>';
    }
    svg+='<text x="'+l+'" y="14" fill="currentColor" font-size="12">кВт</text>';
    for(let h=0;h<=24;h+=W<540?6:3)svg+='<text x="'+xx(h)+'" y="'+(H-14)+'" text-anchor="middle" fill="currentColor" font-size="13">'+String(h).padStart(2,'0')+':00</text>';
    const colors=['#3478f6','#e0aa12','#16a06a'];
    series.forEach(line=>line.sort((a,b)=>a[0]-b[0]));
    if(actual[1].length)svg+='<path class="today-area" d="'+solarSmoothPath(actual[1],xx,yy,this.config.smooth!==false,0)+'" fill="'+colors[1]+'" fill-opacity="0.22" stroke="none"/>';
    series.forEach((line,i)=>{
      if(!line.length)return;
      const d=solarSmoothPath(line,xx,yy,this.config.smooth!==false);
      svg+='<path class="series-line" data-series="'+['yesterday','today','forecast'][i]+'" d="'+d+'" fill="none" stroke="'+colors[i]+'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
    });
    svg+='<line class="cursorline" x1="0" y1="'+t+'" x2="0" y2="'+(H-b)+'" stroke="currentColor" stroke-dasharray="4 4" opacity="0"/>';
    svg+='</svg>';
    return svg;
  }
  _render(){
    if(!this._root||!this._hass)return;
    const todayForecast=this._hass.states[this.config.day_forecast_entity];
    const days=todayForecast?.attributes?.daily_forecast||[];
    const max=Math.max(1,...days.map(d=>Number(d.kwh)||0));
    const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
    this._root.innerHTML=`
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
      .day{display:flex;flex-direction:column;align-items:center;justify-content:end;height:100%;gap:8px;font-size:12px}
      .day>b{font-size:14px;font-weight:600}
      .day>span{color:var(--secondary-text-color,#59656e)}
      .bar{width:100%;max-width:54px;background:#18a58c;border-radius:5px 5px 0 0;min-height:2px}
      .small{font-size:12px;line-height:1.6;color:var(--secondary-text-color,#59656e);margin:20px 0 0}
      .more{margin-top:20px;font-size:18px}
      .unit{font-size:13px;font-weight:400;color:var(--secondary-text-color,#59656e);white-space:nowrap}
      @container(max-width:540px){h3{font-size:18px}.bars{gap:8px;grid-template-columns:repeat(4,minmax(0,1fr));height:auto;row-gap:20px}.day{height:150px}.chart-tooltip{white-space:normal}}
      </style><ha-card><h3>${esc(this.config.title)}</h3>
      <div class="legend"><span><b class="dot" style="background:#3478f6"></b>Вчера</span>
      <span><b class="dot" style="background:#e0aa12"></b>Сегодня · факт</span>
      <span><b class="dot" style="background:#16a06a"></b>Прогноз</span></div>
      <div class="chart-wrap">${this._svg()}<div class="chart-tooltip"></div></div>
      <h3 class="more">Прогноз выработки на 8 дней <span class="unit">· кВт·ч</span></h3>
      <div class="bars">${days.map(d=>`<div class="day"><b>${esc(d.kwh)} </b><div class="bar" style="height:${Math.max(2,100*(Number(d.kwh)||0)/max)}px"></div><span>${esc((d.date||'').slice(5))}</span></div>`).join('')}</div>
      <p class="small">Мощность за 15 минут: вчера, сегодня и прогноз Open-Meteo. ${this.config.smooth!==false?'Линии сглажены; значения в подсказках и энергия рассчитаны по исходным точкам. ':''}Пропуски измерений не заполняются. В Израиле погодные данные интерполируются из часовых.</p>
      ${this._error?'<p class="small">История: '+esc(this._error)+'</p>':''}
      </ha-card>`;
    const wrapper=this._root.querySelector('.chart-wrap'), svg=wrapper?.querySelector('svg');
    const tip=wrapper?.querySelector('.chart-tooltip'), guide=wrapper?.querySelector('.cursorline');
    if(svg && tip){
      const move=ev=>{
        const rect=svg.getBoundingClientRect();
        const g=this._plotGeometry||{W:850,l:55,r:16};
        const px=Math.max(g.l,Math.min(g.W-g.r,(ev.clientX-rect.left)*g.W/rect.width));
        const hour=Math.min(23.875,Math.floor((px-g.l)/(g.W-g.l-g.r)*96)/4+0.125);
        const near=(line)=>{
          if(!line?.length)return null;
          let p=line.reduce((a,b)=>Math.abs(a[0]-hour)<Math.abs(b[0]-hour)?a:b);
          return Math.abs(p[0]-hour)<=0.24?p[1]:null;
        };
        const values=(this._series||[]).map(near);
        if(values.every(v=>v===null)){tip.style.display='none';if(guide)guide.setAttribute('opacity','0');return;}
        const timeHour=Math.floor(hour),timeMin=Math.floor((hour-timeHour)*4)*15;
        tip.innerHTML='<b>'+String((timeHour+Math.floor(timeMin/60))%24).padStart(2,'0')+':'+String(timeMin%60).padStart(2,'0')+'</b><div style="color:#3478f6">Вчера: '+(values[0]===null?'—':(values[0]/1000).toFixed(2)+' кВт')+'</div><div style="color:#e0aa12">Сегодня (факт): '+(values[1]===null?'—':(values[1]/1000).toFixed(2)+' кВт')+'</div><div style="color:#16a06a">Прогноз: '+(values[2]===null?'—':(values[2]/1000).toFixed(2)+' кВт')+'</div>';
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
  getGridOptions(){return this.config?.size === 'compact' ? {columns:6,rows:6,min_rows:4} : {columns:'full',rows:8,min_rows:5};}
  getCardSize(){return this.config?.size === 'compact' ? 5 : 8;}
}
if(!customElements.get('solar-comparison-card'))customElements.define('solar-comparison-card',SolarComparisonCard);
window.customCards=window.customCards||[];
window.customCards.push({type:'solar-comparison-card',name:'Solar Comparison — широкий',description:'На всю ширину секции, три кривые и 8 дней',preview:true,documentationURL:'https://github.com/EvgenyKrinets/solar-yield-forecast'});
window.customCards.push({type:'solar-comparison-compact',name:'Solar Comparison — компактный',description:'Компактный график для обычной колонки',preview:true});

class SolarComparisonCompactCard extends SolarComparisonCard {
  static getStubConfig() { return {size:'compact'}; }
  setConfig(config) {
    super.setConfig({ ...config, size: 'compact' });
  }
}
if(!customElements.get('solar-comparison-compact')) customElements.define('solar-comparison-compact', SolarComparisonCompactCard);
