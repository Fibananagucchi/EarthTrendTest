"""Tests for trends.py — run with:  python -m pytest -q"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import trends


def monthly_series(years=15, trend_per_year=0.0, amp=0.2, noise=0.03, phi=0.6,
                   winter_gap=0.5, seed=0, start=2010, base=0.45):
    """NDVI-like monthly series: seasonal cycle + AR(1) noise + optional trend + cloudy winters."""
    rng = np.random.default_rng(seed)
    n = years * 12
    t = np.arange(n)
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = phi * e[i - 1] + rng.normal(0, noise)
    y = base + amp * np.sin(2 * np.pi * (t - 3) / 12) + trend_per_year * t / 12 + e
    dates = pd.date_range(f"{start}-01-01", periods=n, freq="MS") + pd.Timedelta(days=14)
    df = pd.DataFrame({"date": dates, "value": y})
    month = df["date"].dt.month
    drop = month.isin([12, 1, 2]) & (rng.random(n) < winter_gap)
    return df[~drop].reset_index(drop=True)


# ─────────────────────────────────────────────
# Correctness against independent references
# ─────────────────────────────────────────────

def _reference_hirsch_slack_var(mat):
    """Slow, loop-based Hirsch & Slack (1984) variance, written straight from the paper."""
    n, p = mat.shape
    cols = [g for g in range(p) if np.sum(~np.isnan(mat[:, g])) >= trends.MIN_PER_SEASON]
    var = 0.0
    R = {}
    for g in cols:
        x = mat[:, g]
        ng = np.sum(~np.isnan(x))
        var += trends._tie_corrected_var(x)
        R[g] = np.array([
            (ng + 1 + np.nansum(np.sign(x[j] - x))) / 2 if not np.isnan(x[j]) else (ng + 1) / 2
            for j in range(n)
        ])
    for a in cols:
        for b in cols:
            if a == b:
                continue
            xa, xb = mat[:, a], mat[:, b]
            K = 0.0
            for i in range(n - 1):
                for j in range(i + 1, n):
                    d = (xa[j] - xa[i]) * (xb[j] - xb[i])
                    if not np.isnan(d):
                        K += np.sign(d)
            na, nb = np.sum(~np.isnan(xa)), np.sum(~np.isnan(xb))
            var += (K + 4 * np.sum(R[a] * R[b]) - n * (na + 1) * (nb + 1)) / 3
    return var


def test_covariance_correction_matches_reference_implementation():
    df = monthly_series(years=9, trend_per_year=-0.01, seed=3)
    monthly = trends.to_monthly(df)
    mat, _ = trends._season_matrix(monthly, 12)
    mk = trends.mann_kendall(mat, covariance_correction=True)
    assert mk["corrected"]
    assert mk["var"] == pytest.approx(_reference_hirsch_slack_var(mat), rel=1e-9)


def test_annual_series_matches_scipy():
    rng = np.random.default_rng(1)
    years = np.arange(2000, 2021)
    y = 2.0 + 0.05 * (years - 2000) + rng.normal(0, 0.3, len(years))
    df = pd.DataFrame({"date": pd.to_datetime(years.astype(str) + "-07-01"), "value": y})
    r = trends.analyze_trend(df, alpha=0.05)
    assert r.method.startswith("Mann-Kendall")          # auto-detected annual series
    assert r.tau == pytest.approx(stats.kendalltau(years, y).statistic, abs=1e-12)
    ts = stats.theilslopes(y, years, alpha=0.95)
    assert r.slope == pytest.approx(ts.slope, rel=1e-12)
    # Same distribution-free CI construction (Sen 1968 / Gilbert 1987); allow one rank of slack
    assert r.slope_ci_low == pytest.approx(ts.low_slope, rel=0.25)
    assert r.slope_ci_high == pytest.approx(ts.high_slope, rel=0.25)


# ─────────────────────────────────────────────
# Behaviour
# ─────────────────────────────────────────────

def test_detects_known_falling_trend():
    df = monthly_series(years=15, trend_per_year=-0.02, seed=5)
    r = trends.analyze_trend(df, variable="NDVI")
    assert r.significant and r.direction == "falling"
    assert r.slope_ci_low <= -0.02 <= r.slope_ci_high
    assert r.slope == pytest.approx(-0.02, abs=0.006)
    assert r.total_change == pytest.approx(r.slope * r.span_years)


def test_detects_known_rising_trend():
    df = monthly_series(years=12, trend_per_year=0.015, seed=8)
    r = trends.analyze_trend(df)
    assert r.significant and r.direction == "rising"


def test_seasonal_cycle_alone_is_not_a_trend():
    """False-positive rate must stay near alpha on trend-free, autocorrelated, gappy data."""
    alpha, reps = 0.05, 300
    hits_corrected = hits_naive = 0
    for seed in range(reps):
        df = monthly_series(years=8, trend_per_year=0.0, seed=1000 + seed)
        monthly = trends.to_monthly(df)
        mat, _ = trends._season_matrix(monthly, 12)
        hits_corrected += trends.mann_kendall(mat, covariance_correction=True)["p"] < alpha
        hits_naive += trends.mann_kendall(mat, covariance_correction=False)["p"] < alpha
    fp_corrected = hits_corrected / reps
    fp_naive = hits_naive / reps
    assert fp_corrected <= 0.075, fp_corrected
    # documents why the correction exists: the textbook version is badly anti-conservative
    assert fp_naive > 2 * fp_corrected


def test_missing_months_are_reported():
    df = monthly_series(years=10, winter_gap=1.0, seed=2)   # every Dec-Feb missing
    r = trends.analyze_trend(df)
    assert any("calendar month" in w for w in r.warnings)
    assert np.isfinite(r.p_value)


def test_short_record_warning_and_insufficient_data():
    r = trends.analyze_trend(monthly_series(years=6, seed=4))
    assert any("Short record" in w for w in r.warnings)
    r3 = trends.analyze_trend(monthly_series(years=3, seed=4))
    assert r3.direction == "insufficient data" and not r3.significant


def test_many_ties_like_snow_cover():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2005-01-15", "2024-12-15", freq="MS") + pd.Timedelta(days=14)
    month = dates.month
    winter = np.isin(month, [11, 12, 1, 2, 3])
    years = dates.year - 2005
    snow = np.where(winter, np.clip(60 - 1.5 * years + rng.normal(0, 10, len(dates)), 0, 100), 0.0)
    r = trends.analyze_trend(pd.DataFrame({"date": dates, "value": snow}), relative_change=False)
    assert np.isfinite(r.p_value)
    assert r.direction == "falling"
    assert r.pct_change is None


def test_trend_line_runs_through_the_data():
    df = monthly_series(years=12, trend_per_year=0.01, seed=11)
    r = trends.analyze_trend(df)
    ann = trends.annual_means(trends.to_monthly(df))
    resid = ann["value"] - r.trend_line(ann["year"] + 0.5)
    assert abs(resid.median()) < 0.02


def test_annual_means_not_biased_by_missing_winters():
    df = monthly_series(years=10, noise=0.0, phi=0.0, winter_gap=0.0)
    gappy = df[~((df["date"].dt.year == 2015) & df["date"].dt.month.isin([12, 1, 2]))]
    ann = trends.annual_means(trends.to_monthly(gappy)).set_index("year")
    assert ann.loc[2015, "value"] == pytest.approx(ann.loc[2014, "value"], abs=1e-9)
    assert ann.loc[2015, "raw_mean"] > ann.loc[2014, "raw_mean"]   # a plain mean would be biased


def test_benjamini_hochberg():
    # sorted p: .01 .03 .04 .5 -> p*n/rank: .04 .06 .0533 .5 -> running min from the right
    q = trends.benjamini_hochberg([0.01, 0.04, 0.03, 0.5, np.nan])
    assert np.allclose(q[:4], [0.04, 0.16 / 3, 0.16 / 3, 0.5])
    assert np.isnan(q[4])


def test_grid_matches_single_series():
    rng = np.random.default_rng(2)
    years = np.arange(2001, 2021)
    stack = rng.normal(0, 1, (len(years), 3, 4)) + 0.1 * (years - 2001)[:, None, None]
    stack[:, 0, 0] = np.nan                                   # e.g. an ocean cell
    g = trends.mann_kendall_grid(stack, years)
    series = stack[:, 1, 2]
    df = pd.DataFrame({"date": pd.to_datetime(years.astype(str) + "-07-01"), "value": series})
    r = trends.analyze_trend(df)
    assert g["slope"][1, 2] == pytest.approx(r.slope)
    assert g["z"][1, 2] == pytest.approx(r.mk_z)
    assert np.isnan(g["slope"][0, 0]) and not g["significant"][0, 0]
