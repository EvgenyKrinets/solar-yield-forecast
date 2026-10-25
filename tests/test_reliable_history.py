from test_model import BASE
from test_site_profile import site_fixture
from solar_yield_forecast.shape import power_hours, learn_site_profile
from datetime import timezone
import importlib.util
from io import BytesIO
from zipfile import ZipFile
import pytest


def test_learning_bridges_ten_minutes_but_never_longer_or_unbounded_gaps():
    for gap in (120,300,600):
        bins=power_hours([(0,4),(100,None),(100+gap,8)],900,900)
        assert bins[0][1]==900
        expected=(4*100+6*gap+8*(800-gap))/3600
        assert bins[0][0]==pytest.approx(expected)
    assert power_hours([(0,4),(100,None),(701,8)],900,900)[0][1]==299
    assert power_hours([(0,None),(100,8)],900,900)[0][1]==800
    assert power_hours([(0,4),(100,None)],900,900)[0][1]==100


def test_gap_across_quarter_boundary_is_integrated_exactly():
    bins=power_hours([(0,4),(850,None),(950,8)],1800,900)
    assert bins[0][1]==bins[900][1]==900
    assert bins[0][0]==pytest.approx((850*4+50*5)/3600)
    assert bins[900][0]==pytest.approx((50*7+850*8)/3600)


def test_short_outage_does_not_disqualify_entire_clear_days():
    actual,weather=site_fixture()
    states=[]
    for stamp,(energy,coverage) in actual.items():
        states.append((stamp,energy*4))
        if int(stamp//900)%96==48:
            states.extend([(stamp+60,None),(stamp+180,energy*4)])
    bins=power_hours(states,max(actual)+900,900)
    _,report=learn_site_profile(bins,weather,1,'2026-10-20',timezone.utc)
    assert report['available_days']==8
    assert report['fit_performed']
    assert all(d['status']=='eligible' for d in report['day_diagnostics'].values())


def test_rejection_reasons_and_no_false_training_count():
    actual,weather=site_fixture(days=2)
    factors,report=learn_site_profile(actual,weather,1,'2026-10-20',timezone.utc)
    assert not factors and not report['fit_performed']
    assert report['training_days']==report['validation_days']==0
    _,report=learn_site_profile({},weather,1,'2026-10-20',timezone.utc)
    assert report['available_days']==0
    assert all(d['reason']=='too_few_covered_intervals' for d in report['day_diagnostics'].values())


def test_city_catalog_supplies_exact_point_timezone_and_aliases():
    spec=importlib.util.spec_from_file_location('city_catalog',BASE/'city_catalog.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fields=['295277','Dimona','Dimona','Димона,דימונה','31.07079','35.03269','P','PPL','IL','','01','','','','40000','','','Asia/Jerusalem','2026-01-01']
    stream=BytesIO()
    with ZipFile(stream,'w') as archive:
        archive.writestr('cities15000.txt','\t'.join(fields))
    place=module.decode_catalog(stream.getvalue())['IL'][0]
    assert place['latitude']==31.07079 and place['longitude']==35.03269
    assert place['time_zone']=='Asia/Jerusalem'
    assert 'Димона' in place['aliases']
