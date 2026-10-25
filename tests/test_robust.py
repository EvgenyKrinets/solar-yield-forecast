from test_site_profile import site_fixture
from solar_yield_forecast.robust import learn_profile
from solar_yield_forecast.power_archive import PowerArchive
from datetime import datetime,timezone
import pytest


def test_all_ten_days_used_with_chronological_three_day_holdout():
    actual,weather=site_fixture(days=10)
    for row in weather[3*96:]:
        row.update(cloud_cover=80,direct_radiation=200,diffuse_radiation=400)
    factors,report=learn_profile(actual,weather,1,'2026-11-01',timezone.utc)
    assert factors and report['status']=='active'
    assert report['clear_weather_days']==3
    assert report['selected_profile_days']==10
    assert report['training_days']==7 and report['validation_days']==3
    assert max(report['training_dates'])<min(report['validation_dates'])
    assert report['confidence_percent']==50
    assert report['maximum_day_weight_percent']<25


def test_two_training_day_clear_mode_is_no_longer_enabled():
    actual,weather=site_fixture(days=3)
    factors,report=learn_profile(actual,weather,1,'2026-11-01',timezone.utc)
    assert not factors and report['training_days']==0
    assert report['confidence_percent']==0 and not report['fit_performed']


def test_one_cloud_on_one_day_cannot_carve_a_repeated_notch():
    actual,weather=site_fixture(days=10)
    expected,_=learn_profile(actual,weather,1,'2026-11-01',timezone.utc)
    damaged=dict(actual)
    for stamp,(energy,coverage) in actual.items():
        if datetime.fromtimestamp(stamp,timezone.utc).day==1 and int(stamp//900)%96 in range(44,53):
            damaged[stamp]=(energy*.4,coverage)
    result,_=learn_profile(damaged,weather,1,'2026-11-01',timezone.utc)
    assert result==expected


def test_changed_validation_days_reject_old_training_bias():
    actual,weather=site_fixture(days=10,changed=True)
    assert not learn_profile(actual,weather,1,'2026-11-01',timezone.utc)[0]


def test_existing_profile_not_replaced_by_equal_candidate_and_sizes_scale():
    for capacity in (.5,16,100):
        actual,weather=site_fixture(capacity=capacity,days=10)
        factors,report=learn_profile(actual,weather,1,'2026-11-01',timezone.utc)
        assert factors
        replacement,recheck=learn_profile(actual,weather,1,'2026-11-01',timezone.utc,factors)
        assert not replacement and 'previous_profile_wape_percent' in recheck


def test_archive_keeps_completed_measured_bins_and_survives_recorder_purge():
    archive=PowerArchive()
    archive.observe(0,4);archive.observe(900,8);archive.flush(1800)
    assert archive.bins[0]==[1,900]
    restored=PowerArchive(archive.snapshot(),1801)
    assert restored.bins[0]==[1,900]
    restored.merge_recorder({0:[.1,50]},1801)
    assert restored.bins[0]==[1,900]
    restored.merge_recorder({0:[2,900]},1801)
    assert restored.bins[0]==[2,900]
    restored.flush(91*86400)
    assert 0 not in restored.bins


def test_archive_preserves_invalid_gaps_and_zero_readings():
    archive=PowerArchive()
    archive.observe(0,0);archive.observe(900,None);archive.observe(1800,4);archive.flush(3000)
    assert archive.bins[0]==[0,900]
    assert archive.bins.get(900,[0,0])[1]==0
