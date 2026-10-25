"""Conservative all-weather, chronological-holdout site profile learning."""
from collections import defaultdict
from datetime import datetime
from statistics import median
from .shape import clear_weather_days, interval_shape


def weighted_median(samples):
    ordered=sorted(samples)
    half=sum(w for _,w in ordered)/2
    cumulative=0
    for value,weight in ordered:
        cumulative+=weight
        if cumulative>=half:
            return value
    return 1.0


def score(days, records, factors):
    before=after=energy=0.0
    phases=defaultdict(lambda:[0.,0.,0.])
    daily={}
    for day in days:
        rows=records[day]
        shaped=[p*interval_shape(t,900,factors) for t,p,_,_ in rows]
        normalizer=sum(shaped)/sum(r[1] for r in rows)
        # Define morning/peak/evening by energy-bearing day position, not a
        # hard-coded clock hour, country or panel orientation.
        peak=max(r[1] for r in rows)
        a=b=e=0.0
        for i,((t,p,actual,_),corrected) in enumerate(zip(rows,shaped)):
            old=abs(actual-p*.25); new=abs(actual-corrected/normalizer*.25)
            phase='peak' if p>=peak*.7 else 'morning' if i<len(rows)/2 else 'evening'
            phase_row=phases[phase]
            phase_row[0]+=old;phase_row[1]+=new;phase_row[2]+=actual
            a+=old;b+=new;e+=actual
        daily[day]={'before_wape_percent':round(100*a/e,2),
                    'after_wape_percent':round(100*b/e,2), 'non_worsening':b<=a+e*.005}
        before+=a;after+=b;energy+=e
    return before/energy,after/energy,phases,daily


def learn_profile(bins, weather, factor, today, tz, previous=None):
    by_day=defaultdict(list)
    for row in weather:
        seconds=row.get('interval_seconds',3600);start=row['end']-seconds
        day=datetime.fromtimestamp(start+seconds/2,tz).date().isoformat()
        if day>=today:
            continue
        for offset in range(0,seconds,900):
            t=start+offset;actual,coverage=bins.get(t,(0,0))
            by_day[day].append((t,max(0,row['kw']*factor),actual,coverage))
    records={};diagnostics={}
    for day,rows in sorted(by_day.items()):
        rows.sort()
        peak=max((r[1] for r in rows),default=0)
        daylight=[r for r in rows if r[1]>0 and r[1]>=peak*.03]
        expected=sum(r[1] for r in daylight)
        covered=[r for r in daylight if r[3]>=885]
        coverage=sum(r[1] for r in covered)/expected if expected else 0
        reason=('no_daylight_weather' if not expected else
                'too_few_covered_intervals' if len(covered)<24 else
                'incomplete_power_coverage' if coverage<.97 else None)
        if not reason:
            actual=sum(r[2] for r in covered);predicted=sum(r[1]*.25 for r in covered)
            if not actual or not .45<=actual/predicted<=1.55:
                reason='actual_model_energy_ratio_out_of_range'
        diagnostics[day]={'status':'excluded' if reason else 'eligible','reason':reason,
            'daylight_intervals':len(daylight),'covered_intervals':len(covered),
            'energy_weighted_coverage_percent':round(100*coverage,2)}
        if not reason:
            records[day]=covered
    days=sorted(records)
    clear,weather_scores,_=clear_weather_days(weather,today,tz)
    validation_count=min(7,max(3,len(days)//4))
    report={'status':'insufficient_history','algorithm':'robust_all_weather_15min_v3',
        'history_mode':'quality_weighted_all_weather','available_days':len(days),
        'clear_weather_days':len(set(days)&clear),'selected_profile_days':len(days),
        'training_days':0,'validation_days':0,'training_dates':[],'validation_dates':[],
        'fit_performed':False,'minimum_eligible_days':7,'minimum_validation_days':3,
        'confidence_percent':0,'resolution_minutes':15,'weather_always_applied':True,
        'day_diagnostics':diagnostics,'interpolation_max_gap_minutes':10,
        'metric':'Chronological held-out 15-minute energy WAPE; retrospective, not day-ahead accuracy'}
    if len(days)<7:
        return {},report
    train,test=days[:-validation_count],days[-validation_count:]
    confidence=min(1.,len(train)/14)
    report.update(training_days=len(train),validation_days=len(test),training_dates=train,
                  validation_dates=test,fit_performed=True,confidence_percent=round(confidence*100,1))
    samples=defaultdict(list);weights={}
    for day in train:
        rows=records[day]
        # Modest bounded weights: even a clear day cannot dominate the sample.
        cloud=weather_scores.get(day,{}).get('cloud_cover_percent')
        weight=1.25 if day in clear else .75 if cloud is not None and cloud>65 else 1.
        weights[day]=weight
        scale=sum(r[2] for r in rows)/sum(r[1]*.25 for r in rows)
        peak=max(r[1] for r in rows)
        for t,p,a,_ in rows:
            if p>=peak*.08:
                samples[int(t//900)%96].append((a/(p*.25*scale),weight))
        diagnostics[day].update(role='training',weather_weight=weight,clear_weather=day in clear)
    for day in test:
        diagnostics[day].update(role='validation',clear_weather=day in clear)
    minimum=max(3,min(12,(len(train)*3+4)//5))
    raw={}
    for q,values in samples.items():
        if len(values)<minimum:
            continue
        centre=median(v for v,_ in values)
        mad=median(abs(v-centre) for v,_ in values)
        inliers=[(v,w) for v,w in values if abs(v-centre)<=max(.12,3*mad)]
        if len(inliers)<minimum:
            continue
        target=max(.65,min(1.35,weighted_median(inliers)))
        raw[q]=1+(target-1)*confidence
    report.update(minimum_interval_support=minimum,
        maximum_day_weight_percent=round(100*max(weights.values())/sum(weights.values()),1),
        factor_support_utc={str(q):len(values) for q,values in samples.items()})
    if len(raw)<20:
        report['status']='insufficient_interval_support'
        return {},report
    smooth={}
    for q in raw:
        pairs=[(raw[n%96],4-abs(n-q)) for n in range(q-3,q+4) if n%96 in raw]
        smooth[q]=sum(v*w for v,w in pairs)/sum(w for _,w in pairs)
    ordered=sorted(smooth)
    for _ in range(3):
        for keys in (ordered,ordered[::-1]):
            for left,right in zip(keys,keys[1:]):
                if right-left in (-1,1):
                    smooth[right]=max(smooth[left]-.03,min(smooth[left]+.03,smooth[right]))
    factors={'q'+str(q):round(v,6) for q,v in smooth.items()}
    before,after,phases,daily=score(test,records,factors)
    phase_ok=all(a<=b*1.03+e*.005 for b,a,e in phases.values())
    repeated=sum(d['non_worsening'] for d in daily.values())*3>=len(test)*2
    accepted=after<before*.95 and phase_ok and repeated
    report.update(before_wape_percent=round(before*100,2),after_wape_percent=round(after*100,2),
        validation_by_date=daily,validation_by_phase={key:{'before_wape_percent':round(100*b/e,2),
        'after_wape_percent':round(100*a/e,2)} for key,(b,a,e) in phases.items() if e>0})
    if previous:
        _,previous_error,previous_phases,_=score(test,records,previous)
        report['previous_profile_wape_percent']=round(previous_error*100,2)
        accepted=accepted and after<previous_error*.99 and all(
            phases[key][1]<=row[1]*1.03+row[2]*.005 for key,row in previous_phases.items())
    report['status']='active' if accepted else 'no_validated_improvement'
    return (factors if accepted else {}),report
