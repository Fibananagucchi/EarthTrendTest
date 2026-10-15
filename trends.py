"""
Trend Detective — trend statistics for NASA Earth-system time series.

Answers "how much is it changing?" and "is the change significant?" for a
single time series (any variable, any region). Pure numpy/scipy, no GEE.

Methods
-------
Verdict (significance):
    Seasonal Mann-Kendall test (Hirsch, Slack & Smith 1982) with the
    Hirsch & Slack (1984) covariance correction. The test compares each
    calendar month only with the same month in other years, so the seasonal
    cycle cannot masquerade as a trend. The covariance term accounts for
    correlation between neighbouring months; without it the test flags
    12-25 % of trend-free, autocorrelated monthly series as "significant"
    at alpha = 0.05 (see tests/test_trends.py).

Magnitude:
    Seasonal Sen's slope (median of all same-month, between-year slopes) in
    units per year, with a distribution-free confidence interval
    (Gilbert 1987). Robust to outliers such as cloud-contaminated pixels.

Secondary (reported, not used for the verdict):
    Ordinary least squares on deseasonalized anomalies, with the p-value
    adjusted for lag-1 autocorrelation via an effective sample size.

Series with about one value per year are tested with the plain
(non-seasonal) Mann-Kendall test and Sen's slope.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
from scipy import stats


MIN_YEARS = 4          # below this we refuse to call a trend
SHORT_RECORD_YEARS = 8 # below this we warn about low statistical power
MIN_PER_SEASON = 3     # a calendar month needs >= 3 years to enter the test


# ─────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────

@dataclass
class TrendResult:
    variable: str
    units: str
    method: str
    alpha: float
    n_obs: int
    n_years: int
    first_year: int
    last_year: int
    span_years: float
    # Mann-Kendall
    mk_s: float
    mk_var: float
    mk_z: float
    p_value: float
    tau: float
    covariance_corrected: bool
    # Sen's slope (units / year) and confidence interval
    slope: float
    slope_ci_low: float
    slope_ci_high: float
    ci_level: float
    # Trend line: value(t) = line_level + slope * (t - t_mid), t in decimal years
    t_mid: float
    line_level: float
    # Magnitude
    mean_level: float
    total_change: float
    pct_change: float | None
    change_vs_variability: float | None
    # Secondary OLS
    ols_slope: float
    ols_p_value: float
    ols_r2: float
    lag1_autocorr: float
    # Verdict
    significant: bool
    direction: str          # "rising" | "falling" | "no significant trend" | "insufficient data"
    tendency: str           # sign of Sen's slope regardless of significance
    strength: str           # human-readable significance label
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def trend_line(self, t: np.ndarray, slope: float | None = None) -> np.ndarray:
        s = self.slope if slope is None else slope
        return self.line_level + s * (np.asarray(t, float) - self.t_mid)


# ─────────────────────────────────────────────
# Data preparation
# ─────────────────────────────────────────────

def decimal_year(dates) -> np.ndarray:
    d = pd.to_datetime(pd.Series(dates))
    start = pd.to_datetime(d.dt.year.astype(str) + "-01-01")
    end = pd.to_datetime((d.dt.year + 1).astype(str) + "-01-01")
    return (d.dt.year + (d - start) / (end - start)).to_numpy(float)


def to_monthly(df: pd.DataFrame, value_col: str = "value", date_col: str = "date") -> pd.DataFrame:
    """Average irregular observations (e.g. one row per satellite pass) to monthly means."""
    d = df[[date_col, value_col]].dropna().copy()
    d[date_col] = pd.to_datetime(d[date_col])
    d["year"] = d[date_col].dt.year
    d["month"] = d[date_col].dt.month
    m = d.groupby(["year", "month"], as_index=False)[value_col].mean()
    m = m.rename(columns={value_col: "value"})
    m["date"] = pd.to_datetime(dict(year=m["year"], month=m["month"], day=15))
    return m.sort_values("date").reset_index(drop=True)


def _season_matrix(monthly: pd.DataFrame, period: int) -> tuple[np.ndarray, np.ndarray]:
    """Rows = consecutive years (gaps kept as NaN rows), columns = seasons."""
    years = np.arange(monthly["year"].min(), monthly["year"].max() + 1)
    mat = np.full((len(years), period), np.nan)
    if period == 1:
        annual = monthly.groupby("year")["value"].mean()
        mat[annual.index.to_numpy() - years[0], 0] = annual.to_numpy()
    else:
        mat[monthly["year"].to_numpy() - years[0], monthly["month"].to_numpy() - 1] = monthly["value"].to_numpy()
    return mat, years


def climatology(monthly: pd.DataFrame) -> pd.Series:
    """Mean value for each calendar month (the seasonal cycle)."""
    return monthly.groupby("month")["value"].mean()


def deseasonalize(monthly: pd.DataFrame) -> pd.DataFrame:
    out = monthly.copy()
    out["anomaly"] = out["value"] - out["month"].map(climatology(monthly))
    return out


def annual_means(monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Seasonally adjusted annual means: mean monthly anomaly for the year plus the
    long-term level. Unlike a plain calendar-year average, a year with missing
    winter months (clouds, snow, polar night) is not biased towards summer values.
    """
    ds = deseasonalize(monthly)
    level = climatology(monthly).mean()
    g = ds.groupby("year")
    out = pd.DataFrame({
        "year": g["anomaly"].mean().index,
        "value": g["anomaly"].mean().to_numpy() + level,
        "raw_mean": g["value"].mean().to_numpy(),
        "n_months": g["value"].count().to_numpy(),
    })
    out["date"] = pd.to_datetime(out["year"].astype(str) + "-07-01")
    return out


# ─────────────────────────────────────────────
# Mann-Kendall building blocks
# ─────────────────────────────────────────────

def _sign_matrices(mat: np.ndarray) -> np.ndarray:
    """P[g, i, j] = sign(x[j, g] - x[i, g]); 0 where either value is missing."""
    x = mat.T                                  # (seasons, years)
    diff = x[:, None, :] - x[:, :, None]       # [g, i, j] = x[g, j] - x[g, i]
    return np.nan_to_num(np.sign(diff), nan=0.0)


def _tie_corrected_var(col: np.ndarray) -> float:
    v = col[~np.isnan(col)]
    n = len(v)
    _, counts = np.unique(v, return_counts=True)
    ties = np.sum(counts * (counts - 1) * (2 * counts + 5))
    return (n * (n - 1) * (2 * n + 5) - ties) / 18.0


def mann_kendall(mat: np.ndarray, covariance_correction: bool = True) -> dict:
    """
    (Seasonal) Mann-Kendall test on a years x seasons matrix with NaN gaps.
    With one column this is the ordinary Mann-Kendall test.
    """
    counts = np.sum(~np.isnan(mat), axis=0)
    keep = counts >= MIN_PER_SEASON
    mat = mat[:, keep]
    counts = counts[keep]
    n_years = mat.shape[0]
    if mat.shape[1] == 0:
        return dict(s=0.0, var=0.0, z=0.0, p=1.0, tau=0.0, corrected=False, seasons_used=0)

    P = _sign_matrices(mat)
    s_per_season = np.triu(P, k=1).sum(axis=(1, 2))   # sum over i < j
    var_diag = np.array([_tie_corrected_var(mat[:, g]) for g in range(mat.shape[1])])
    s = float(s_per_season.sum())
    var = float(var_diag.sum())

    corrected = False
    if covariance_correction and mat.shape[1] > 1:
        # Hirsch & Slack (1984), eq. for cov(S_g, S_h) allowing missing values
        K = 0.5 * np.einsum("gij,hij->gh", P, P)
        R = (counts[:, None] + 1 + P.sum(axis=1)) / 2.0          # (seasons, years)
        cov = (K + 4.0 * (R @ R.T) - n_years * np.outer(counts + 1, counts + 1)) / 3.0
        off_diag = cov.sum() - np.trace(cov)
        if var + off_diag > 0:
            var = var + off_diag
            corrected = True

    if var <= 0:
        z = 0.0
    else:
        z = (s - np.sign(s)) / np.sqrt(var)
    p = float(2.0 * stats.norm.sf(abs(z)))
    n_pairs = float(np.sum(counts * (counts - 1) / 2.0))
    tau = s / n_pairs if n_pairs else 0.0
    return dict(s=s, var=var, z=float(z), p=p, tau=float(tau), corrected=corrected,
                seasons_used=int(mat.shape[1]))


def sens_slope(mat: np.ndarray, var_s: float, alpha: float) -> tuple[float, float, float]:
    """Seasonal Sen's slope (per row step = per year) and its (1 - alpha) CI."""
    slopes = []
    idx = np.arange(mat.shape[0])
    for g in range(mat.shape[1]):
        col = mat[:, g]
        ok = ~np.isnan(col)
        if ok.sum() < 2:
            continue
        y, t = col[ok], idx[ok]
        i, j = np.triu_indices(len(y), k=1)
        slopes.append((y[j] - y[i]) / (t[j] - t[i]))
    if not slopes:
        return 0.0, np.nan, np.nan
    d = np.sort(np.concatenate(slopes))
    n = len(d)
    median = float(np.median(d))
    c = stats.norm.ppf(1 - alpha / 2) * np.sqrt(max(var_s, 0.0))
    m1 = (n - c) / 2.0
    m2 = (n + c) / 2.0
    lo_i = int(np.clip(np.floor(m1), 1, n)) - 1
    hi_i = int(np.clip(np.ceil(m2) + 1, 1, n)) - 1
    return median, float(d[lo_i]), float(d[hi_i])


def ols_on_anomalies(t: np.ndarray, anomaly: np.ndarray) -> dict:
    """OLS slope of anomalies vs time with lag-1 effective-sample-size p-value."""
    if len(t) < 4 or np.ptp(t) == 0:
        return dict(slope=np.nan, p=np.nan, r2=np.nan, r1=np.nan)
    r = stats.linregress(t, anomaly)
    resid = anomaly - (r.intercept + r.slope * t)
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 3 else 0.0
    if not np.isfinite(r1):
        r1 = 0.0
    n = len(t)
    n_eff = n * (1 - r1) / (1 + r1) if r1 > 0 else n
    n_eff = max(n_eff, 3.0)
    if r.stderr == 0:
        p = 0.0 if r.slope != 0 else 1.0
    else:
        t_stat = r.slope / r.stderr * np.sqrt((n_eff - 2) / max(n - 2, 1))
        p = float(2 * stats.t.sf(abs(t_stat), n_eff - 2))
    return dict(slope=float(r.slope), p=p, r2=float(r.rvalue ** 2), r1=r1)


def strength_label(p: float, alpha: float) -> str:
    if p < min(0.01, alpha):
        return "highly significant"
    if p < alpha:
        return "significant"
    if p < 0.10:
        return "weak evidence (not significant)"
    return "not significant"


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def analyze_trend(
    df: pd.DataFrame,
    value_col: str = "value",
    date_col: str = "date",
    alpha: float = 0.05,
    variable: str = "",
    units: str = "",
    relative_change: bool = True,
    seasonal: bool | None = None,
) -> TrendResult:
    """
    Full trend analysis of one time series.

    df: any temporal resolution; rows are averaged to monthly means first.
    seasonal: None = auto (seasonal test when there are several values per year).
    relative_change: report the change as % of the mean level (off for
        interval-scale variables such as temperature in °C or indices that
        cross zero).
    """
    monthly = to_monthly(df, value_col, date_col)
    warnings: list[str] = []
    years_with_data = monthly["year"].nunique()

    if seasonal is None:
        seasonal = len(monthly) >= 2.5 * max(years_with_data, 1)
    period = 12 if seasonal else 1

    if years_with_data < MIN_YEARS:
        return _insufficient(monthly, variable, units, alpha, years_with_data)

    mat, years = _season_matrix(monthly, period)
    mk = mann_kendall(mat, covariance_correction=True)
    if mk["seasons_used"] == 0:
        return _insufficient(monthly, variable, units, alpha, years_with_data)
    if period == 12 and mk["seasons_used"] < 12:
        warnings.append(
            f"{12 - mk['seasons_used']} calendar month(s) had too few measurements (fewer than {MIN_PER_SEASON} "
            "years — usually because of clouds, snow or darkness) and were left out."
        )
    if years_with_data < SHORT_RECORD_YEARS:
        warnings.append(
            f"Short record ({years_with_data} years): only big, steady changes can be detected. "
            "'No clear change' here does not prove that nothing changed."
        )

    slope, lo, hi = sens_slope(mat, mk["var"], alpha)

    if period == 12:
        ds = deseasonalize(monthly)
        level = float(climatology(monthly).mean())
        ann = annual_means(monthly)
    else:
        ann = monthly.groupby("year", as_index=False)["value"].mean()
        ann["date"] = pd.to_datetime(ann["year"].astype(str) + "-07-01")
        level = float(ann["value"].mean())
        ds = ann.assign(anomaly=ann["value"] - level)

    t = decimal_year(ds["date"])
    t_mid = float((t.min() + t.max()) / 2)
    anomaly_offset = float(np.median(ds["anomaly"].to_numpy() - slope * (t - t_mid)))
    line_level = level + anomaly_offset

    span = float(t.max() - t.min())
    total = slope * span
    pct = None
    if relative_change and abs(level) > 1e-9:
        pct = 100.0 * total / abs(level)

    ann_sd =float(np.std(ann["value"] - (line_level + slope * (ann["year"] + 0.5 - t_mid)), ddof=1)) \
        if len(ann) > 2 else np.nan
    change_vs_var = abs(total) / ann_sd if ann_sd and np.isfinite(ann_sd) and ann_sd > 0 else None

    ols = ols_on_anomalies(t, ds["anomaly"].to_numpy())

    significant = mk["p"] < alpha
    tendency = "rising" if slope > 0 else "falling" if slope < 0 else "flat"
    if significant and slope == 0:
        # Mann-Kendall can reject with a zero median slope when many values tie
        tendency = "rising" if mk["s"] > 0 else "falling"
    direction = tendency if significant else "no significant trend"

    if significant and np.isfinite(lo) and np.isfinite(hi) and lo <= 0 <= hi:
        warnings.append("The size of the change is uncertain — the true rate could be close to zero.")
    if np.isfinite(ols["p"]) and (ols["p"] < alpha) != significant:
        warnings.append(
            "Two statistical methods disagree on this one (linear regression vs Mann-Kendall), so treat it "
            "with care. We report the Mann-Kendall answer, which is less affected by unusual years."
        )

    method = (
        "Seasonal Mann-Kendall (Hirsch-Slack covariance-corrected) + seasonal Sen's slope"
        if period == 12 else "Mann-Kendall + Sen's slope on annual values"
    )

    return TrendResult(
        variable=variable, units=units, method=method, alpha=alpha,
        n_obs=int(len(monthly)), n_years=int(years_with_data),
        first_year=int(years.min()), last_year=int(years.max()), span_years=span,
        mk_s=mk["s"], mk_var=mk["var"], mk_z=mk["z"], p_value=mk["p"], tau=mk["tau"],
        covariance_corrected=mk["corrected"],
        slope=slope, slope_ci_low=lo, slope_ci_high=hi, ci_level=1 - alpha,
        t_mid=t_mid, line_level=line_level,
        mean_level=level, total_change=total, pct_change=pct, change_vs_variability=change_vs_var,
        ols_slope=ols["slope"], ols_p_value=ols["p"], ols_r2=ols["r2"], lag1_autocorr=ols["r1"],
        significant=significant, direction=direction, tendency=tendency,
        strength=strength_label(mk["p"], alpha), warnings=warnings,
    )


def _insufficient(monthly, variable, units, alpha, n_years) -> TrendResult:
    nan = float("nan")
    fy = int(monthly["year"].min()) if len(monthly) else 0
    ly = int(monthly["year"].max()) if len(monthly) else 0
    return TrendResult(
        variable=variable, units=units, method="—", alpha=alpha,
        n_obs=int(len(monthly)), n_years=int(n_years), first_year=fy, last_year=ly, span_years=nan,
        mk_s=nan, mk_var=nan, mk_z=nan, p_value=nan, tau=nan, covariance_corrected=False,
        slope=nan, slope_ci_low=nan, slope_ci_high=nan, ci_level=1 - alpha,
        t_mid=nan, line_level=nan, mean_level=float(monthly["value"].mean()) if len(monthly) else nan,
        total_change=nan, pct_change=None, change_vs_variability=None,
        ols_slope=nan, ols_p_value=nan, ols_r2=nan, lag1_autocorr=nan,
        significant=False, direction="insufficient data", tendency="unknown",
        strength="insufficient data",
        warnings=[f"Only {n_years} year(s) with data — at least {MIN_YEARS} are needed to look for a trend."],
    )


# ─────────────────────────────────────────────
# Many tests at once
# ─────────────────────────────────────────────

def benjamini_hochberg(p_values) -> np.ndarray:
    """False-discovery-rate adjusted p-values (q-values). NaNs pass through."""
    p = np.asarray(p_values, float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    if not ok.any():
        return q
    pv = p[ok]
    n = len(pv)
    order = np.argsort(pv)
    ranked = pv[order] * n / np.arange(1, n + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(ranked, 0, 1)
    q[ok] = out
    return q


def mann_kendall_grid(stack: np.ndarray, years: np.ndarray, alpha: float = 0.05) -> dict:
    """
    Per-cell Mann-Kendall + Sen's slope for a (years, rows, cols) stack of annual
    values — the offline twin of the per-pixel GEE trend map.
    """
    n_t = stack.shape[0]
    flat = stack.reshape(n_t, -1)
    years = np.asarray(years, float)
    i, j = np.triu_indices(n_t, k=1)
    n_cells = flat.shape[1]
    s = np.zeros(n_cells)
    slope = np.full(n_cells, np.nan)
    chunk = max(1, int(2.5e6 // max(len(i), 1)))          # bound memory: pairs x cells per chunk
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN cells (e.g. ocean)
        for c0 in range(0, n_cells, chunk):
            diffs = flat[j, c0:c0 + chunk] - flat[i, c0:c0 + chunk]      # (pairs, cells)
            s[c0:c0 + chunk] = np.nansum(np.sign(diffs), axis=0)
            slope[c0:c0 + chunk] = np.nanmedian(diffs / (years[j] - years[i])[:, None], axis=0)
        n = np.sum(~np.isnan(flat), axis=0)
        var = n * (n - 1) * (2 * n + 5) / 18.0
        z = np.where(var > 0, (s - np.sign(s)) / np.sqrt(var), 0.0)
    zcrit = stats.norm.ppf(1 - alpha / 2)
    shape = stack.shape[1:]
    return dict(
        slope=slope.reshape(shape),
        z=z.reshape(shape),
        significant=(np.abs(z) > zcrit).reshape(shape),
    )
