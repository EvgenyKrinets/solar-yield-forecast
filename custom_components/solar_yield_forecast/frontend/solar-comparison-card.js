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
    for(const attr of [...old.attributes])if(!next.hasAttribute(attr.name)&&!(old.tagName==='DETAILS'&&attr.name==='open'))old.removeAttribute(attr.name);
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
// Historical originals are never replaced by a current/retrospective forecast.
function solarHistoricalDays(attrs, mode='best') {
  const result={};
  const priority={day_ahead:0,morning:1,late_start:2};
  for(const row of (attrs.forecast_ledger_history||[])){
    if(!(row.kind in priority))continue;
    if(mode!=='best'&&row.kind!==mode)continue;
    if(row.kwh==null||!Number.isFinite(Number(row.kwh))||Number(row.kwh)<0)continue;
    if(!result[row.date]||priority[row.kind]<priority[result[row.date].kind])result[row.date]=row;
  }
  return result;
}
const SOLAR_TEXT = [
 ['Солнечные панели','Solar panels','פאנלים סולאריים'],['Язык','Language','שפה'],['Авто','Auto','אוטומטי'],['Нет доступного прогноза','No forecast available','אין תחזית זמינה'],
 ['Точность первоначального прогноза','Original forecast accuracy','דיוק התחזית המקורית'],
 ['Пока нет завершённых дней для сравнения.','No completed days are available for comparison yet.','עדיין אין ימים שהסתיימו לצורך השוואה.'],
 ['Нет данных за выбранный период.','No data for the selected period.','אין נתונים לתקופה שנבחרה.'],
 ['Выберите другой период или время составления прогноза.','Choose another period or forecast issue time.','בחרו תקופה אחרת או מועד אחר ליצירת התחזית.'],
 ['Данные появятся после завершения дня с заранее сохранённым прогнозом.','Results appear after a day with an advance forecast has ended.','התוצאות יופיעו לאחר סיום יום שעבורו נשמרה תחזית מראש.'],
 ['Как читать показатели','Understanding the metrics','איך לקרוא את המדדים'],
 ['Ошибка — сумма абсолютных отклонений, делённая на суммарную фактическую выработку.','Error is the sum of absolute deviations divided by total actual yield.','השגיאה היא סכום הסטיות המוחלטות חלקי סך הייצור בפועל.'],
 ['Положительное смещение означает завышенный прогноз.','Positive bias means the forecast is too high.','הטיה חיובית מציינת תחזית גבוהה מהייצור בפועל.'],
 ['Сравниваются только завершённые дни с известным итогом.','Only completed days with a known total are compared.','ההשוואה כוללת רק ימים שהסתיימו עם סיכום ידוע.'],
 ['Обновление модели не меняет сохранённые прогнозы.','Recalculation does not change saved forecasts.','חישוב מחדש אינו משנה תחזיות שנשמרו.'],
 ['Накануне, после 20:00','Previous evening, after 20:00','בערב הקודם, אחרי 20:00'],['До начала генерации','Before generation starts','לפני תחילת הייצור'],
 ['Поздний запуск — вне оценки точности','Late start — excluded from accuracy scoring','הפעלה מאוחרת — לא נכללת במדדי הדיוק'],
 ['Нет сохранённого первоначального прогноза. Исторический пересчёт не заменяет исходный прогноз.','No original forecast was saved. A retrospective calculation cannot replace it.','לא נשמרה תחזית מקורית. חישוב בדיעבד אינו מחליף אותה.'],
 ['Фиксированный прогноз','Fixed forecast','תחזית קבועה'],['Зафиксированный прогноз','Fixed forecast','תחזית קבועה'],['Зафиксированный','Fixed','קבועה'],
 ['Выработка','Yield','ייצור'],['Уточнённый итог','Updated daily estimate','הערכת ייצור יומית מעודכנת'],['О прогнозе','About this forecast','על התחזית'],
 ['Предыдущий день','Previous day','היום הקודם'],['Предыдущий период','Previous period','התקופה הקודמת'],['Следующий период','Next period','התקופה הבאה'],
 ['Выбрать дату','Choose date','בחירת תאריך'],['Сбросить масштаб','Reset zoom','איפוס זום'],['Сбросить Zoom','Reset zoom','איפוס זום'],
 ['Развернуть график','Expand chart','הגדלת הגרף'],['Свернуть','Collapse','צמצום'],['Сегодня','Today','היום'],
 ['Всё время','All time','כל התקופה'],['Неделя','Week','שבוע'],['Месяц','Month','חודש'],['Интервал','Date range','טווח תאריכים'],['День','Day','יום'],['Год','Year','שנה'],
 ['Накануне','Previous evening','בערב הקודם'],['Утром','Morning','בבוקר'],['PV · факт','PV · actual','PV · בפועל'],['PV (факт)','PV (actual)','PV (בפועל)'],
 ['Факт − прогноз','Actual − forecast','בפועל פחות התחזית'],['Факт − прогноз','Actual − forecast','בפועל פחות התחזית'],
 ['Дата','Date','תאריך'],['Прогноз','Forecast','תחזית'],['Факт','Actual','בפועל'],['Версия','Version','גרסה'],
 ['Ошибка','Error','שגיאה'],['Смещение','Bias','הטיה'],['Дней','Days','ימים'],['дней','days','ימים'],
 ['Прогноз выработки на','Yield forecast for','תחזית ייצור עבור'],['Загрузка истории…','Loading history…','טעינת היסטוריה…'],
 ['Нет данных за выбранную дату','No data for the selected date','אין נתונים לתאריך שנבחר'],
 ['Мощность вчера, сегодня и прогноз','Previous day, actual and forecast power','הספק ביום הקודם, בפועל ובתחזית'],['Выработка за выбранный период','Yield for the selected period','ייצור בתקופה שנבחרה'],
 ['Сравнение по совпадающим завершённым дням','Comparison of matching completed days','השוואת ימים תואמים שהסתיימו'],
 ['Нет подходящих пар.','No matching days.','אין ימים תואמים.'],['Факт за доступные дни','Actual yield for available days','ייצור בפועל בימים הזמינים'],
 ['Поздних запусков','Late starts','הפעלות מאוחרות'],['вне сравнения','excluded from comparison','לא נכללות בהשוואה'],
 ['Пропуски не заменяются нулями.','Missing values are not replaced with zeros.','נתונים חסרים אינם מוחלפים באפסים.'],
 ['Неполный период не является полным итогом.','A partial period is not a complete total.','תקופה חלקית אינה סיכום מלא.'],
 ['Нажмите столбец для детализации.','Select a bar for details.','לחצו על עמודה להצגת פירוט.'],
 ['Начало интервала должно быть не позже конца.','The start date must not be after the end date.','תאריך ההתחלה אינו יכול להיות אחרי תאריך הסיום.'],
 ['Выберите интервал не больше 10 лет.','Choose a range of no more than 10 years.','בחרו טווח של עד 10 שנים.'],
 ['исторический прогноз','fixed forecast','תחזית קבועה'],['текущий прогноз','current forecast','תחזית נוכחית'],['нет данных','no data','אין נתונים'],
 ['дней с данными','days with data','ימים עם נתונים'],['дней факта','actual days','ימים עם נתוני אמת'],['дней прогноза','forecast days','ימים עם תחזית'],
 ['факт','actual','בפועל'],['прогноз','forecast','תחזית'],['кВт·ч','kWh','קוט״ש'],['кВт','kW','קילוואט'],
 ['Пропуск измерений — соединение для ориентира','Missing measurements — visual guide only','מדידות חסרות — חיבור להמחשה בלבד'],
 ['Энергия за 15 мин','Energy per 15 min','אנרגיה ב־15 דקות'],['Отклонение','Deviation','סטייה'],
 ['Не удалось обновить погоду','Weather update failed','עדכון מזג האוויר נכשל'],['причина не указана','no reason provided','לא צוינה סיבה'],
 ['Срок действия предыдущего прогноза истёк.','The previous forecast has expired.','תוקף התחזית הקודמת פג.'],
 ['Показан предыдущий прогноз — данные устарели.','Showing the previous forecast — weather data is stale.','מוצגת התחזית הקודמת — נתוני מזג האוויר אינם עדכניים.'],
 ['Последняя загрузка','Last update','עדכון אחרון'],['История','History','היסטוריה'],
 ['Дальний ансамблевый прогноз — точность ниже','Long-range ensemble forecast — lower confidence','תחזית אנסמבל לטווח ארוך — ודאות נמוכה יותר'],['Основной прогноз погоды','Main weather forecast','תחזית מזג האוויר הראשית'],
 ['Помощь по графику','Chart help','עזרה לגרף'],
 ['Разведите два пальца для увеличения. Перемещайте увеличенный график пальцем. Двойное нажатие сбрасывает масштаб.','Pinch to zoom. Drag to pan a zoomed chart. Double-tap to reset.','הרחיקו שתי אצבעות להגדלה. גררו כדי להזיז גרף מוגדל. הקשה כפולה מאפסת את הזום.'],
 ['Мощность усредняется за 15 минут. Короткие пропуски до 10 минут восстанавливаются между соседними измерениями; более длинные остаются пустыми.','Power is averaged over 15 minutes. Gaps up to 10 minutes are interpolated between adjacent readings; longer gaps stay empty.','ההספק הוא ממוצע של 15 דקות. פערים עד 10 דקות מושלמים בין מדידות סמוכות; פערים ארוכים יותר נשארים ריקים.'],
 ['Полосатые столбцы — дальний прогноз с меньшей точностью.','Striped bars indicate a less certain long-range forecast.','עמודות מפוספסות מציינות תחזית רחוקה עם ודאות נמוכה יותר.'],
 ['С','From','מתאריך'],['По','To','עד תאריך']
];
function solarLanguage(hass, choice='auto') {
  const requested=choice==='auto'?String(hass?.locale?.language||hass?.language||'en').toLowerCase():choice;
  return requested.startsWith('ru')?'ru':requested.startsWith('he')?'he':'en';
}
function solarTranslate(text, language) {
  if(language==='ru')return text;
  const map=new Map(SOLAR_TEXT.map(row=>[row[0],row[language==='he'?2:1]]));
  if(map.has(text.trim()))return text.replace(text.trim(),map.get(text.trim()));
  const keys=[...map.keys()].filter(k=>k.length>2).sort((a,b)=>b.length-a.length);
  const pattern=keys.map(k=>k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|');
  return text.replace(new RegExp(pattern,'g'),key=>map.get(key));
}
function solarTranslateDOM(root, language) {
  for(const el of root.querySelectorAll('*')){
    if(['STYLE','SCRIPT'].includes(el.tagName)||el.matches('[data-user-title], .language-picker'))continue;
    for(const child of el.childNodes)if(child.nodeType===3)child.textContent=solarTranslate(child.textContent,language);
    for(const attr of ['title','aria-label'])if(el.hasAttribute(attr))el.setAttribute(attr,solarTranslate(el.getAttribute(attr),language));
  }
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
    this._forecast = null;
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
    if (!previous || previous.language!==hass.language || previous.locale?.language!==hass.locale?.language || [this.config.forecast_entity, this.config.day_forecast_entity].some(id => previous.states[id] !== hass.states[id])) this._render();
  }
  _timeZone(){
    return this.config?.time_zone||this._hass?.states?.[this.config?.day_forecast_entity]?.attributes?.site_configuration?.time_zone||this._hass?.config?.time_zone||Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';
  }
  _languageChoice(){
    if(this._chosenLanguage)return this._chosenLanguage;
    try{return this.config.language||localStorage.getItem('solar-yield-language')||'auto';}catch{return this.config.language||'auto';}
  }
  _language(){return solarLanguage(this._hass,this._languageChoice());}
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
      const historyPromise=start<end ? this._hass.callApi('GET',
        'history/period/' + encodeURIComponent(start.toISOString()) +
        '?filter_entity_id=' + encodeURIComponent(this.config.pv_entity) +
        '&end_time=' + encodeURIComponent(end.toISOString()) + '&minimal_response') : Promise.resolve([]);
      const profilePromise=this._hass.callApi('GET','solar_yield_forecast/profile/'+encodeURIComponent(this._selected));
      const [historyResult,profileResult] = await Promise.allSettled([historyPromise,profilePromise]);
      if(request!==this._request)return;
      const errors=[];
      if(historyResult.status==='fulfilled'){
        const rows=historyResult.value;
        this._history = Array.isArray(rows) ? (rows[0] || []) : [];
      }else errors.push(historyResult.reason);
      if(profileResult.status==='fulfilled'){
        const profile=profileResult.value;
        this._forecast = Array.isArray(profile?.points) ? profile.points : [];
        this._original = profile?.original || null;
      }else errors.push(profileResult.reason);
      this._error=errors.length ? errors.map(e=>e?.message||e?.body?.message||String(e)).join(' · ') : null;
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
    const dayState=this._hass?.states?.[this.config.day_forecast_entity];
    const expired=dayState?.state==='unavailable'&&dayState?.attributes?.weather_status==='stale';
    const points=expired?[]:(this._forecast ?? [...(this._hass?.states?.[this.config.forecast_entity]?.attributes?.points||[]),...(this._hass?.states?.[this.config.forecast_entity.replace(/today$/, 'tomorrow')]?.attributes?.points||[])]);
    const forecast=points.filter(p=>Number.isFinite(Date.parse(p.time)) && dayFmt.format(new Date(p.time))===today && p.power_w!==null).map(p=>{
      const d=new Date(p.time);
      const a=f.format(d).split(':').map(Number);
      return [a[0]+a[1]/60+d.getSeconds()/3600,Number(p.power_w)];
    }).filter(x=>Number.isFinite(x[0])&&Number.isFinite(x[1]));
    const series=[actual[0],actual[1],forecast].map((line,i)=>this._visible[i]?line:[]);
    const original=(this._original?.points||[]).map(p=>{
      const d=new Date(p.time),a=f.format(d).split(':').map(Number);
      return [a[0]+a[1]/60,Number(p.power_w)];
    }).filter(p=>p.every(Number.isFinite));
    this._originalSeries=original;
    this._series=series;
    const max=Math.max(1000,...series.flat().map(p=>p[1]),...(this._hideOriginal?[]:original.map(p=>p[1])))*1.08;
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
    if(!this._hideOriginal&&original.length)svg+='<path class="original-line" d="'+solarSmoothPath(original,xx,yy,this.config.smooth!==false)+'" fill="none" stroke="#a855f7" stroke-width="2.5" stroke-dasharray="7 4"><title>Зафиксированный прогноз: '+this._original.kind+'</title></path>';
    svg+='</g>';
    svg+='<line class="cursorline" x1="0" y1="'+t+'" x2="0" y2="'+(H-b)+'" stroke="currentColor" stroke-dasharray="4 4" opacity="0"/>';
    svg+='</svg>';
    return solarTranslate(svg,this._language());
  }
  _forecastSummary(esc){
    const attrs=this._hass.states[this.config.day_forecast_entity]?.attributes||{};
    const original=this._original;
    const actual=attrs.daily_actuals?.[this._selected];
    const current=this._selected===solarDay(new Date(),this._timeZone())?this._hass.states[this.config.day_forecast_entity]?.state:null;
    const fmt=v=>v!=null&&Number.isFinite(Number(v))?Number(v).toFixed(1)+' кВт·ч':'—';
    return `<div class="summary yield-summary"><div class="yield-kpi actual-kpi"><span>Выработка · кВт·ч</span><b>${fmt(actual).replace(' кВт·ч','')}</b></div><div class="yield-kpi fixed-kpi"><span>Фиксированный прогноз · кВт·ч</span><b>${fmt(original?.kwh).replace(' кВт·ч','')}</b></div></div>${current!==null?'<div class="live-estimate">Уточнённый итог <b>'+fmt(current)+'</b></div>':''}<details class="snapshot-info"><summary>О прогнозе</summary><p class="small">${original?esc(({day_ahead:'Накануне, после 20:00',morning:'До начала генерации',late_start:'Поздний запуск — вне оценки точности'})[original.kind]||original.kind)+' · '+esc(new Date(original.recorded_at).toLocaleString('ru-RU',{timeZone:this._timeZone()}))+' · v'+esc(original.version):'Нет сохранённого первоначального прогноза. Исторический пересчёт не заменяет исходный прогноз.'}</p></details>`;
  }
  _accuracy(esc){
    const attrs=this._hass.states[this.config.day_forecast_entity]?.attributes||{};
    const days=this._accuracyDays||30,kind=this._cohort||'day_ahead';
    const today=solarDay(new Date(),this._timeZone()),start=solarShift(today,-days);
    const all=(attrs.forecast_ledger_history||[]).filter(r=>r.completed&&['morning','day_ahead'].includes(r.kind));
    const rows=all.filter(r=>r.kind===kind&&r.date>=start&&r.date<today).reverse();
    if(!all.length)return '<section class="accuracy-empty"><h3>Точность первоначального прогноза</h3><p>Пока нет завершённых дней для сравнения.</p><p class="small">Данные появятся после завершения дня с заранее сохранённым прогнозом.</p></section>';
    const summary=attrs.forecast_ledger_summary?.[kind+'_'+days]||{};
    const fmt=v=>v!=null&&Number.isFinite(Number(v))?Number(v).toFixed(1):'—';
    const controls='<div class="accuracy-controls"><div role="group" aria-label="Интервал">'+[7,30].map(n=>'<button data-accuracy-days="'+n+'" aria-pressed="'+(n===days)+'">'+n+' дней</button>').join('')+'</div><div role="group" aria-label="Прогноз">'+[['day_ahead','Накануне'],['morning','Утром']].map(([k,label])=>'<button data-cohort="'+k+'" aria-pressed="'+(kind===k)+'">'+label+'</button>').join('')+'</div></div>';
    const table=rows.length?'<p>Ошибка: <b>'+fmt(summary.wape_percent)+'%</b> · Смещение: '+fmt(summary.bias_percent)+'% · Дней: '+(summary.samples||0)+'</p><div style="overflow-x:auto"><table><thead><tr><th>Дата</th><th>Прогноз</th><th>Факт</th><th>Факт − прогноз</th></tr></thead><tbody>'+rows.map(r=>'<tr><td><button data-open-day="'+esc(r.date)+'">'+esc(r.date)+'</button></td><td>'+fmt(r.kwh)+'</td><td>'+fmt(r.actual_kwh)+'</td><td>'+fmt(r.deviation_kwh)+' кВт·ч / '+fmt(r.deviation_percent)+'%</td></tr>').join('')+'</tbody></table></div>':'<p class="accuracy-empty">Нет данных за выбранный период.</p><p class="small">Выберите другой период или время составления прогноза.</p>';
    return '<section><h3>Точность первоначального прогноза</h3>'+controls+table+'<details class="chart-help"><summary>Как читать показатели</summary><p>Ошибка — сумма абсолютных отклонений, делённая на суммарную фактическую выработку.</p><p>Положительное смещение означает завышенный прогноз.</p><p>Сравниваются только завершённые дни с известным итогом.</p><p>Обновление модели не меняет сохранённые прогнозы.</p></details></section>';
  }
  _render(){
    if(!this._root||!this._hass||this._touching)return;
    const todayForecast=this._hass.states[this.config.day_forecast_entity];
    const weatherStatus=todayForecast?.attributes?.weather_status;
    const weatherUpdated=todayForecast?.attributes?.forecast_updated_at;
    const allDays=todayForecast?.state==='unavailable'&&weatherStatus==='stale'?[]:(todayForecast?.attributes?.daily_forecast||[]);
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
      .tools{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px}.tools button{font-size:13px}
      .chart-wrap{touch-action:pan-y}.chart-wrap.zoomed{touch-action:none}
      .legend{margin:16px 0;gap:8px}.legend button[hidden]{display:none}.legend button{display:flex;align-items:center;gap:8px;padding:6px}
      .toggle{width:34px;height:20px;border-radius:12px;background:var(--series);position:relative}.toggle:after{content:'';position:absolute;width:16px;height:16px;top:2px;right:2px;background:white;border-radius:50%}
      [aria-pressed=false] .toggle{background:#aaa}[aria-pressed=false] .toggle:after{right:16px}
      :host([expanded]){position:fixed;inset:0;z-index:1000;background:var(--card-background-color,white);overflow:auto}
      .tools label{min-width:0;max-width:100%}.history-mode{display:block;max-width:100%;min-height:36px;font:inherit;background:var(--card-background-color,white);color:inherit;border:1px solid var(--divider-color,#ddd);border-radius:8px}.summary{display:flex;flex-wrap:wrap;gap:16px;font-size:16px;margin:12px 0}.empty{text-align:center;padding:20px;color:var(--secondary-text-color,#777)}
      ha-card{border:0;border-radius:0;box-shadow:none;padding:24px 16px;background:var(--card-background-color,#fff)}
      ha-card>h3{font-size:22px;margin-bottom:20px;color:var(--primary-text-color,#242424)}
      .periods{gap:10px;padding-bottom:16px;margin:0 -4px 20px}
      .periods button{padding:10px 20px;min-height:46px;background:var(--secondary-background-color,#f7f7f7);font-size:15px}
      .periods button[aria-pressed=true]{color:#f58220;background:#fff3e7}
      .date-nav{margin:12px 0 22px}.date-nav input{font-size:20px;font-weight:500}.date-nav button{font-size:22px;color:var(--secondary-text-color,#666)}
      .yield-summary{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:24px 0 12px;text-align:center}
      .yield-kpi{display:flex;flex-direction:column;justify-content:center;gap:8px;min-width:0;padding:0 12px}
      .yield-kpi+ .yield-kpi{border-left:1px solid var(--divider-color,#eee)}
      .yield-kpi span{font-size:14px;line-height:1.4}.yield-kpi b{font-size:clamp(32px,6vw,58px);line-height:1.2;font-weight:750;letter-spacing:-1px}
      .actual-kpi{color:#f58220}.fixed-kpi{color:#344da1}.live-estimate{text-align:center;font-size:13px;color:var(--secondary-text-color,#777);margin:18px 0}
      .snapshot-info{font-size:12px;color:var(--secondary-text-color,#777);margin-bottom:24px}.snapshot-info .small{margin:8px 0}
      .tools{margin:8px 0}.tools button{color:var(--secondary-text-color,#777)}
      .chart-wrap{margin-top:24px}.legend{gap:8px 16px;margin:20px 0 28px}.legend button{min-height:44px;font-size:14px;color:var(--primary-text-color,#292929)}
      .toggle{width:40px;height:24px;flex:none;border-radius:20px}.toggle:after{width:20px;height:20px;right:2px;top:2px}[aria-pressed=false] .toggle:after{right:18px}
      .forecast-head,section{border-top:1px solid var(--divider-color,#eee);padding-top:24px;margin-top:28px}section h3{font-size:18px}
      th,td{padding:10px 8px;border-bottom:1px solid var(--divider-color,#eee);font-size:12px;white-space:nowrap}th{font-weight:500;color:var(--secondary-text-color,#777)}
      .period-comparison{margin:20px 0 8px;padding:16px;background:var(--secondary-background-color,#fafafa);border-radius:8px;line-height:1.7}
      @container(max-width:540px){ha-card{padding:18px 12px}.yield-kpi{padding:0 6px}.yield-kpi span{font-size:12px}.date-nav input{font-size:18px}}
      .language-bar{display:flex;justify-content:flex-end;align-items:center;gap:8px;font-size:12px;margin-bottom:12px}.language-picker{font:inherit;color:inherit;background:var(--card-background-color,white);border:1px solid var(--divider-color,#ddd);border-radius:8px;min-height:36px;padding:4px 8px}
      .accuracy-controls{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.accuracy-controls>div{display:flex;border-radius:24px;background:var(--secondary-background-color,#f6f6f6);padding:3px}.accuracy-controls button[aria-pressed=true]{background:#fff0df;color:#e87516;font-weight:600}.accuracy-controls button[aria-pressed=false]{opacity:.7}.accuracy-empty{color:var(--secondary-text-color,#777)}
      .chart-help{margin:20px 0;font-size:12px;line-height:1.7;color:var(--secondary-text-color,#777)}summary{cursor:pointer}table{width:100%;text-align:end;border-collapse:collapse}.yield-summary{direction:inherit}[dir=rtl] .yield-kpi+ .yield-kpi{border-left:0;border-right:1px solid var(--divider-color,#eee)}svg,input[type=date]{direction:ltr}
      </style><ha-card lang="${this._language()}" dir="${this._language()==='he'?'rtl':'ltr'}"><div class="language-bar"><label for="solar-language">Язык</label><select id="solar-language" class="language-picker" aria-label="Язык">${[['auto','Авто'],['ru','Русский'],['en','English'],['he','עברית']].map(([k,label])=>'<option value="'+k+'" '+(this._languageChoice()===k?'selected':'')+'>'+label+'</option>').join('')}</select></div><h3 ${this.config.title!=='Солнечные панели'?'data-user-title':''}>${esc(this.config.title)}</h3>
      <div class="periods">${[['day','День'],['week','Неделя'],['month','Месяц'],['year','Год'],['range','Интервал'],['all','Всё время']].map(([key,label])=>`<button data-period="${key}" aria-pressed="${this._period===key}">${label}</button>`).join('')}</div>
      <div class="date-nav"><button data-step="-1" aria-label="Предыдущий период" ${['all','range'].includes(this._period)?'disabled':''}>❮</button><input aria-label="Выбрать дату" type="date" value="${this._selected}"><button data-step="1" aria-label="Следующий период" ${['all','range'].includes(this._period)?'disabled':''}>❯</button></div>
      ${this._period==='range'?'<div class="tools"><label>С <input class="range-start" type="date" value="'+(this._rangeStart||solarShift(this._selected,-29))+'"></label><label>По <input class="range-end" type="date" value="'+(this._rangeEnd||this._selected)+'"></label></div>':''}
      ${this._period!=='day'?'<div class="tools"><label>Прогноз <select class="history-mode">'+[['best','Зафиксированный'],['day_ahead','Накануне'],['morning','Утром']].map(([k,label])=>'<option value="'+k+'" '+((this._historyMode||'best')===k?'selected':'')+'>'+label+'</option>').join('')+'</select></label></div>':''}
      <div class="tools"><button class="now">Сегодня</button><button class="reset">Сбросить Zoom</button><button class="expand" aria-label="Развернуть график">${this.hasAttribute('expanded')?'Свернуть':'⛶'}</button></div>
      ${this._period==='day'?this._forecastSummary(esc):''}
      <div class="chart-wrap ${this._view[1]-this._view[0]<24?'zoomed':''}">${this._period==='day'?this._svg():this._energySvg()}<div class="chart-tooltip"></div></div>
      <div class="legend">${['Предыдущий день','PV · факт','Прогноз'].map((label,i)=>`<button ${i===0&&this._period!=='day'?'hidden':''} data-toggle="${i}" aria-pressed="${this._visible[i]}" style="--series:${['#3478f6','#ff9e3d','#16a06a'][i]}"><span class="toggle"></span>${label}</button>`).join('')}<button class="original-toggle" aria-pressed="${!this._hideOriginal}" style="--series:#a855f7"><span class="toggle"></span>Фиксированный прогноз</button></div>
      ${this._period==='day'&&!this._series.some(x=>x.length)&&(this._hideOriginal||!this._originalSeries?.length)?'<div class="empty">Нет данных за выбранную дату</div>':''}
      ${weatherStatus==='stale'?'<div class="weather-warning" role="status" style="padding:12px;background:var(--warning-color,#ffb300);color:#212121;border-radius:8px">Не удалось обновить погоду: '+esc(todayForecast?.attributes?.last_refresh_error?.message||'причина не указана')+'. '+(todayForecast?.state==='unavailable'?'Срок действия предыдущего прогноза истёк.':'Показан предыдущий прогноз — данные устарели.')+' Последняя загрузка: '+esc(weatherUpdated||'—')+'</div>':''}
      ${this._loading?'<div class="small">Загрузка истории…</div>':''}
      <div class="forecast-head"><h3 class="more">Прогноз выработки на ${this._forecastRange===30?'30':'8'} дней <span class="unit">· кВт·ч</span></h3><div class="forecast-range"><button data-forecast-range="8" aria-pressed="${this._forecastRange!==30}">8 дней</button><button data-forecast-range="30" aria-pressed="${this._forecastRange===30}">Месяц</button></div></div>
      <div class="bars ${this._forecastRange===30?'month':''}">${days.map(d=>`<div role="button" tabindex="0" data-open-day="${esc(d.date)}" class="day ${d.source==='ensemble'?'ensemble':''}" title="${d.source==='ensemble'?'Дальний ансамблевый прогноз — точность ниже':'Основной прогноз погоды'}"><b>${esc(d.kwh)} </b><div class="bar" style="height:${Math.max(2,100*(Number(d.kwh)||0)/max)}px"></div><span>${esc((d.date||'').slice(5))}</span></div>`).join('')}</div>
      ${!days.length?'<p class="empty">Нет доступного прогноза</p>':''}
      ${this._accuracy(esc)}
      <details class="chart-help"><summary>Помощь по графику</summary><p>Разведите два пальца для увеличения. Перемещайте увеличенный график пальцем. Двойное нажатие сбрасывает масштаб.</p><p>Мощность усредняется за 15 минут. Короткие пропуски до 10 минут восстанавливаются между соседними измерениями; более длинные остаются пустыми.</p><p>Полосатые столбцы — дальний прогноз с меньшей точностью.</p></details>
      ${this._error?'<p class="small">История: '+esc(this._error)+'</p>':''}
      </ha-card>`;
    solarTranslateDOM(template.content,this._language());
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
        const fixed=this._hideOriginal?null:near(this._originalSeries);
        if(fixed!==null)tip.innerHTML+='<div>Фиксированный прогноз: '+(fixed/1000).toFixed(2)+' кВт</div>';
        solarTranslateDOM(tip,this._language());
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
    this._selected=day;this._period=period;this._view=[0,24];this._history=[];this._forecast=null;this._original=null;this._error=null;
    this._request=(this._request||0)+1;this._loading=false;
    this._fetch();this._render();
  }
  _bindControls(){
    this._root.querySelectorAll('[data-open-day]').forEach(el=>{const open=()=>this._select(el.dataset.openDay,'day');el.onclick=open;el.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();open();}};});
    const picker=this._root.querySelector('.language-picker');
    if(picker)picker.onchange=ev=>{this._chosenLanguage=ev.target.value;try{localStorage.setItem('solar-yield-language',this._chosenLanguage);}catch{}this._render();};
    this._root.querySelectorAll('[data-period]').forEach(el=>el.onclick=()=>this._select(this._selected,el.dataset.period));
    this._root.querySelectorAll('[data-step]').forEach(el=>el.onclick=()=>this._select(solarShift(this._selected,Number(el.dataset.step)*(this._period==='week'?7:1),this._period)));
    this._root.querySelector('input[type=date]').onchange=ev=>this._select(ev.target.value);
    for(const field of ['start','end']){
      const input=this._root.querySelector('.range-'+field);
      if(input)input.onchange=ev=>{if(/^\d{4}-\d{2}-\d{2}$/.test(ev.target.value)){this[field==='start'?'_rangeStart':'_rangeEnd']=ev.target.value;this._render();}};
    }
    const historyMode=this._root.querySelector('.history-mode');
    if(historyMode)historyMode.onchange=ev=>{this._historyMode=ev.target.value;this._render();};
    this._root.querySelector('.now').onclick=()=>this._select(solarDay(new Date(),this._timeZone()));
    this._root.querySelector('.reset').onclick=()=>{this._view=[0,24];this._render();};
    const originalToggle=this._root.querySelector('.original-toggle');
    if(originalToggle)originalToggle.onclick=()=>{this._hideOriginal=!this._hideOriginal;this._render();};
    this._root.querySelectorAll('[data-accuracy-days]').forEach(el=>el.onclick=()=>{this._accuracyDays=Number(el.dataset.accuracyDays);this._render();});
    this._root.querySelectorAll('[data-cohort]').forEach(el=>el.onclick=()=>{this._cohort=el.dataset.cohort;this._render();});
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
    const originals=solarHistoricalDays(attrs,this._historyMode||'best');
    const today=solarDay(new Date(),this._timeZone());
    let start=this._selected,end;
    if(this._period==='week'){
      const weekday=new Date(start+'T12:00:00Z').getUTCDay();start=solarShift(start,-((weekday+6)%7));end=solarShift(start,7);
    }else if(this._period==='month'){start=start.slice(0,7)+'-01';end=solarShift(start,1,'month');}
    else if(this._period==='year'){start=start.slice(0,4)+'-01-01';end=solarShift(start,1,'year');}
    else if(this._period==='range'){start=this._rangeStart||solarShift(this._selected,-29);end=solarShift(this._rangeEnd||this._selected,1);}
    else{start=Object.keys({...actual,...forecast,...originals}).sort()[0]||start;end=solarShift(Object.keys({...actual,...forecast,...originals}).sort().at(-1)||start,1);}
    if(start>=end)return '<div class="empty">Начало интервала должно быть не позже конца.</div>';
    if((Date.parse(end)-Date.parse(start))/86400000>3660)return '<div class="empty">Выберите интервал не больше 10 лет.</div>';
    const groups=new Map(),monthly=['year','all'].includes(this._period)||(Date.parse(end)-Date.parse(start))/86400000>62;
    let pairedActual=0,pairedForecast=0,pairedCount=0,lateCount=0;
    for(let day=start;day<end;day=solarShift(day,1)){
      const key=monthly?day.slice(0,7)+'-01':day;
      const g=groups.get(key)||{date:key,a:null,f:null,p:null,count:0,pc:0};
      if(actual[day]!=null&&Number.isFinite(Number(actual[day]))){g.a=(g.a??0)+Number(actual[day]);g.count++;}
      if(day>=today&&forecast[day]!=null&&Number.isFinite(Number(forecast[day])))g.f=(g.f??0)+Number(forecast[day]);
      const original=originals[day];
      if(original){
        g.p=(g.p??0)+Number(original.kwh);g.pc++;
        const valid=original.kind==='day_ahead'||original.kind==='morning';
        if(!valid)lateCount++;
        if(valid&&day<today&&actual[day]!=null&&Number.isFinite(Number(actual[day]))&&Number(actual[day])>=0){
          pairedActual+=Number(actual[day]);pairedForecast+=Number(original.kwh);pairedCount++;
        }
      }
      groups.set(key,g);
    }
    const rows=[...groups.values()],W=Math.max(240,Math.round(this.getBoundingClientRect().width||850)-32),H=300,l=46,r=12,b=50,t=26;
    const max=Math.max(1,...rows.flatMap(d=>[this._visible[1]?d.a:0,this._visible[2]?d.f:0,this._hideOriginal?0:d.p]))*1.1;
    const x=i=>l+(W-l-r)*(i+.5)/Math.max(1,rows.length),y=v=>H-b-(H-t-b)*v/max;
    const bw=Math.max(.5,Math.min(22,(W-l-r)/Math.max(1,rows.length)*.25));
    let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Выработка за выбранный период"><text x="${l}" y="16" fill="currentColor" font-size="12">кВт·ч</text>`;
    for(let i=0;i<=4;i++)svg+=`<line x1="${l}" x2="${W-r}" y1="${y(max*i/4)}" y2="${y(max*i/4)}" stroke="currentColor" opacity=".12"/><text x="${l-6}" y="${y(max*i/4)+4}" text-anchor="end" fill="currentColor" font-size="11">${(max*i/4).toFixed(0)}</text>`;
    rows.forEach((d,i)=>{
      const label=`${d.date}: факт ${d.a===null?'нет данных':d.a.toFixed(1)+' кВт·ч'}, исторический прогноз ${d.p===null?'нет данных':d.p.toFixed(1)+' кВт·ч'}, текущий прогноз ${d.f===null?'нет данных':d.f.toFixed(1)+' кВт·ч'}; дней факта: ${d.count}, дней прогноза: ${d.pc}`;
      svg+=`<g data-date="${d.date}" tabindex="0" role="button" aria-label="${label}"><title>${label}</title><rect x="${x(i)-1.5*bw}" y="${t}" width="${bw*3}" height="${H-b-t}" fill="transparent"/>`;
      if(d.a!==null&&this._visible[1])svg+=`<rect x="${x(i)-1.5*bw}" y="${y(d.a)}" width="${bw}" height="${Math.max(0,H-b-y(d.a))}" rx="2" fill="#ff9e3d"/>`;
      if(d.p!==null&&!this._hideOriginal)svg+=`<rect data-historical="true" x="${x(i)-.5*bw}" y="${y(d.p)}" width="${bw}" height="${Math.max(0,H-b-y(d.p))}" rx="2" fill="#a855f7"/>`;
      if(d.f!==null&&this._visible[2])svg+=`<rect x="${x(i)+.5*bw}" y="${y(d.f)}" width="${bw}" height="${Math.max(0,H-b-y(d.f))}" rx="2" fill="#16a06a"/>`;
      if(i%Math.max(1,Math.ceil(rows.length/(W<540?7:14)))===0)svg+=`<text x="${x(i)}" y="${H-24}" text-anchor="middle" font-size="11" fill="currentColor">${monthly?d.date.slice(2,7):d.date.slice(8)}</text>`;
      svg+='</g>';
    });
    svg+='</svg>';
    return `<div class="summary">${start} — ${solarShift(end,-1)}</div>${svg}<div class="period-comparison">Сравнение по совпадающим завершённым дням: ${pairedCount}. ${pairedCount?'Прогноз: '+pairedForecast.toFixed(1)+' кВт·ч · Факт: '+pairedActual.toFixed(1)+' кВт·ч · Факт − прогноз: '+(pairedActual-pairedForecast).toFixed(1)+' кВт·ч'+(pairedActual>0?' / '+(100*(pairedActual-pairedForecast)/pairedActual).toFixed(1)+'%':''):'Нет подходящих пар.'}</div><div class="small">Факт за доступные дни: ${rows.some(d=>d.a!==null)?rows.reduce((sum,d)=>sum+(d.a||0),0).toFixed(1)+' кВт·ч':'нет данных'}. Поздних запусков: ${lateCount} (вне сравнения). Пропуски не заменяются нулями. Неполный период не является полным итогом. Нажмите столбец для детализации.</div>`;
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

const SOLAR_PANEL_TAG='solar-yield-forecast-panel-v1-6-2';
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
      header{max-width:1280px;margin:0 auto;padding:14px 20px 0;display:flex;align-items:center;justify-content:space-between;box-sizing:border-box}
      header strong{font-size:20px;line-height:40px}
      .actions{display:flex;align-items:center;gap:8px}.action{border:0;border-radius:20px;background:var(--secondary-background-color,#eee);color:var(--primary-text-color,#212121);height:40px;padding:0 16px;display:flex;align-items:center;gap:8px;font:inherit;cursor:pointer}
      .action:hover{background:var(--divider-color,#ddd)}.action:disabled{opacity:.55;cursor:wait}
      .action[hidden]{display:none}
      main{max-width:1280px;margin:0 auto;padding:20px;box-sizing:border-box}
      @media(max-width:600px){header{padding:8px 8px 0}header strong{font-size:17px}.action{width:40px;padding:0;justify-content:center}.action span{display:none}main{padding:8px}}
    </style><header><strong></strong><div class="actions"><button class="settings action" type="button"><ha-icon icon="mdi:cog"></ha-icon><span></span></button></div></header><main></main>`;
    this.shadowRoot.querySelector('.settings').addEventListener('click',()=>this._openSettings());
  }
  set panel(value){this._panel=value;this._sync();}
  get panel(){return this._panel;}
  set hass(value){this._hass=value;this._sync();}
  get hass(){return this._hass;}
  _config(){return this._panel?.config||{};}
  _settingsLabel(){
    let choice='auto';try{choice=localStorage.getItem('solar-yield-language')||'auto';}catch{}
    const language=solarLanguage(this._hass,choice);
    return language.startsWith('ru')?'Настройки':language.startsWith('he')?'הגדרות':'Settings';
  }
  _openSettings(){
    history.pushState(null,'','/config/integrations/integration/solar_yield_forecast');
    window.dispatchEvent(new Event('location-changed'));
  }
  _sync(){
    if(!this._hass)return;
    const label=this._settingsLabel();
    this.shadowRoot.querySelector('header strong').textContent=this._config().title||'Solar Yield Forecast';
    const settings=this.shadowRoot.querySelector('.settings');
    settings.hidden=!this._hass.user?.is_admin;
    settings.title=label;settings.setAttribute('aria-label',label);
    settings.querySelector('span').textContent=label;
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
