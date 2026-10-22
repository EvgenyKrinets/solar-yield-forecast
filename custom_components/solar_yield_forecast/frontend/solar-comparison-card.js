/* Solar Comparison Card: day-aligned Sungrow power and 8-day forecast. */
class SolarComparisonCard extends HTMLElement {
  setConfig(config) {
    this.config = {
      title: 'Солнечные панели — вчера / сегодня / прогноз',
      pv_entity: 'sensor.total_dc_power',
      forecast_entity: 'sensor.solar_yield_forecast_power_profile_today',
      day_forecast_entity: 'sensor.solar_yield_forecast_today',
      energy_entity: 'sensor.daily_pv_generation',
      size: 'wide',
      ...config
    };
    this._root = this.shadowRoot || this.attachShadow({mode: 'open'});
    this._history = null;
    this._compact = this.config.size === 'compact';
    this._date = '';
    this._render();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this._root) return;
    const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Jerusalem', year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    if (this._date !== today || (!this._loading && (!this._lastFetch || Date.now() - this._lastFetch > 300000))) {
      this._date = today;
      this._fetch();
    }
    this._render();
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
      this._history = Array.isArray(rows) ? (rows[0] || []) : [];
    } catch (e) {
      this._error = String(e);
      this._history = [];
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
    for(const s of (this._history||[])){
      const d=new Date(s.last_changed||s.last_updated);
      if(!Number.isFinite(d.getTime())) continue;
      const day=dayFmt.format(d);
      const idx=day===today?1:(day===yesterday?0:-1);
      if(idx<0)continue;
      let v=Number(s.state);
      if(!Number.isFinite(v)||v<0)continue;
      if(unit==='kw')v*=1000;
      const parts=f.format(d).split(':').map(Number);
      actual[idx].push([parts[0]+parts[1]/60,v]);
    }
    const points=this._hass?.states?.[this.config.forecast_entity]?.attributes?.points||[];
    const forecast=points.map(p=>{
      const d=new Date(p.time);
      const a=f.format(d).split(':').map(Number);
      return [a[0]+a[1]/60,Number(p.power_w)];
    }).filter(x=>Number.isFinite(x[0])&&Number.isFinite(x[1]));
    // Average measured samples into 15-minute buckets to compare like with like.
    const aggregate = samples => {
      const bins = new Map();
      for (const [hour, value] of samples) {
        const bucket = Math.floor(hour * 4) / 4;
        const arr = bins.get(bucket) || [];
        arr.push(value);
        bins.set(bucket, arr);
      }
      return [...bins.entries()].map(([h, a]) => [h + 0.125, a.reduce((x,y)=>x+y,0)/a.length]).sort((a,b)=>a[0]-b[0]);
    };
    const series=[aggregate(actual[0]),aggregate(actual[1]),forecast];
    this._series=series;
    const max=Math.max(1000,...series.flat().map(p=>p[1]))*1.08;
    const W=850,H=315,l=55,r=16,t=20,b=38;
    const xx=x=>l+(W-l-r)*x/24;
    const yy=y=>t+(H-t-b)*(1-y/max);
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Мощность вчера, сегодня и прогноз">';
    for(let i=0;i<=4;i++){
      const y=max*i/4,py=yy(y);
      svg+='<line x1="'+l+'" x2="'+(W-r)+'" y1="'+py+'" y2="'+py+'" stroke="#88929a" opacity=".20"/>';
      svg+='<text x="'+(l-6)+'" y="'+(py+4)+'" text-anchor="end" fill="currentColor" font-size="12">'+(y/1000).toFixed(1)+'</text>';
    }
    for(let h=0;h<=24;h+=3)svg+='<text x="'+xx(h)+'" y="'+(H-14)+'" text-anchor="middle" fill="currentColor" font-size="12">'+String(h).padStart(2,'0')+':00</text>';
    const colors=['#458ee0','#f2a03a','#16a68a'];
    series.forEach((line,i)=>{
      if(!line.length)return;
      line.sort((a,b)=>a[0]-b[0]);
      const d=line.map((p,j)=>(j?'L':'M')+xx(p[0]).toFixed(1)+','+yy(p[1]).toFixed(1)).join(' ');
      svg+='<path d="'+d+'" fill="none" stroke="'+colors[i]+'" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
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
      :host{display:block;color:var(--primary-text-color)}
      ha-card{padding:16px;overflow:hidden}
      :host{width:100%;min-width:0}
      .bars{min-width:0}
      h3{margin:0 0 10px;font-size:17px}
      .legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--secondary-text-color);margin-bottom:8px}
      .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
      .chart-wrap{position:relative;max-width:100%;width:100%;overflow:visible}\n      svg{width:100%;height:auto;max-height:430px;display:block}\n      .chart-tooltip{position:absolute;z-index:10;pointer-events:none;background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 2px 10px #0003;border:1px solid var(--divider-color,#ccc);border-radius:8px;padding:8px 12px;font-size:12px;display:none;white-space:nowrap}\n      @media(max-width:580px){ha-card{padding:10px}.bars{gap:3px}.day{font-size:9px}h3{font-size:14px}}
      .bars{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:7px;align-items:end;height:140px;margin-top:16px}
      .day{display:flex;flex-direction:column;align-items:center;justify-content:end;height:100%;gap:4px;font-size:10px}
      .bar{width:100%;max-width:54px;background:#18a58c;border-radius:5px 5px 0 0;min-height:2px}
      .small{font-size:11px;color:var(--secondary-text-color)}
      .more{margin-top:12px}
      </style><ha-card><h3>${esc(this.config.title)}</h3>
      <div class="legend"><span><b class="dot" style="background:#458ee0"></b>Вчера</span>
      <span><b class="dot" style="background:#f2a03a"></b>Сегодня</span>
      <span><b class="dot" style="background:#16a68a"></b>Прогноз</span></div>
      <div class="chart-wrap">${this._svg()}<div class="chart-tooltip"></div></div>
      <h3 class="more">Прогноз выработки на 8 дней</h3>
      <div class="bars">${days.map(d=>`<div class="day"><b>${esc(d.kwh)} </b><div class="bar" style="height:${Math.max(2,100*(Number(d.kwh)||0)/max)}px"></div><span>${esc((d.date||'').slice(5))}</span></div>`).join('')}</div>
      <p class="small">Оранжевая и синяя: усреднение измерений по 15 минут. Зелёная: часовой погодный прогноз (интерполяция до 15 минут). Мощность в кВт, энергия в кВт·ч.</p>
      ${this._error?'<p class="small">История: '+esc(this._error)+'</p>':''}
      </ha-card>`;
    const wrapper=this._root.querySelector('.chart-wrap'), svg=wrapper?.querySelector('svg');
    const tip=wrapper?.querySelector('.chart-tooltip'), guide=wrapper?.querySelector('.cursorline');
    if(svg && tip){
      const move=ev=>{
        const rect=svg.getBoundingClientRect();
        const px=Math.max(55,Math.min(834,(ev.clientX-rect.left)*850/rect.width));
        const hour=(px-55)/779*24;
        const near=(line)=>{
          if(!line?.length)return null;
          let p=line.reduce((a,b)=>Math.abs(a[0]-hour)<Math.abs(b[0]-hour)?a:b);
          return Math.abs(p[0]-hour)<=0.24?p[1]:null;
        };
        const values=(this._series||[]).map(near);
        if(values.every(v=>v===null)){tip.style.display='none';return;}
        const timeHour=Math.floor(hour),timeMin=Math.round((hour-timeHour)*60/15)*15;
        tip.innerHTML='<b>'+String((timeHour+Math.floor(timeMin/60))%24).padStart(2,'0')+':'+String(timeMin%60).padStart(2,'0')+'</b><div style="color:#458ee0">Вчера: '+(values[0]===null?'—':(values[0]/1000).toFixed(2)+' кВт')+'</div><div style="color:#f2a03a">Сегодня: '+(values[1]===null?'—':(values[1]/1000).toFixed(2)+' кВт')+'</div><div style="color:#16a68a">Прогноз: '+(values[2]===null?'—':(values[2]/1000).toFixed(2)+' кВт')+'</div>';
        tip.style.display='block';
        tip.style.left=Math.min(rect.width-135,Math.max(0,(ev.clientX-rect.left)+12))+'px';
        tip.style.top='8px';
        if(guide){guide.setAttribute('x1',px);guide.setAttribute('x2',px);guide.setAttribute('opacity','0.5');}
      };
      svg.addEventListener('pointermove',move);
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
  setConfig(config) {
    super.setConfig({ ...config, size: 'compact' });
  }
}
if(!customElements.get('solar-comparison-compact')) customElements.define('solar-comparison-compact', SolarComparisonCompactCard);
