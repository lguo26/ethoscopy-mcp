"""Two-group log-rank tests with one Holm family per survival recipe."""
import numpy as np
import pandas as pd
from scipy.stats import chi2

from ethoscopy_mcp.errors import InvalidExperimentError


def logrank_score(a, b):
    """Return O-E and tied-event hypergeometric variance for group A."""
    score = variance = 0.0
    times = np.unique(np.r_[a.loc[a.E.eq(1), 'T'], b.loc[b.E.eq(1), 'T']])
    for time in times:
        na, nb = int(a['T'].ge(time).sum()), int(b['T'].ge(time).sum())
        da = int((a['T'].eq(time) & a.E.eq(1)).sum())
        db = int((b['T'].eq(time) & b.E.eq(1)).sum())
        n, d = na + nb, da + db
        score += da - d * na / n
        if n > 1:
            variance += na * nb * d * (n-d) / (n*n*(n-1))
    return score, variance


def holm_adjust(pvalues):
    pvalues = np.asarray(pvalues, dtype=float)
    order = np.argsort(pvalues)
    adjusted = np.empty(len(pvalues))
    adjusted[order] = np.minimum(1, np.maximum.accumulate(
        pvalues[order] * np.arange(len(pvalues), 0, -1)))
    return adjusted


def compare_survival(individuals, comparisons):
    if (not individuals.id.is_unique or not np.isfinite(individuals['T']).all()
            or individuals['T'].lt(0).any() or not individuals.E.isin([0, 1]).all()):
        raise InvalidExperimentError('Invalid survival endpoints for log-rank analysis')
    rows = []
    for comparison in comparisons:
        required = set(comparison.filters) | set(comparison.strata_columns)
        if not required <= set(individuals.columns):
            raise InvalidExperimentError('Unknown log-rank filter or stratum column')
        selected = individuals.loc[individuals.treatment.isin(comparison.group_labels)]
        for column, value in comparison.filters.items():
            selected = selected.loc[selected[column].eq(value)]
        if selected.empty or selected[list(required)].isna().any().any():
            raise InvalidExperimentError('Empty comparison or missing log-rank metadata')
        strata = (selected.groupby(list(comparison.strata_columns), dropna=False)
                  if comparison.strata_columns else [(None, selected)])
        score = variance = 0.0
        n_strata = 0
        for _, stratum in strata:
            a = stratum.loc[stratum.treatment.eq(comparison.group_labels[0])]
            b = stratum.loc[stratum.treatment.eq(comparison.group_labels[1])]
            if a.empty or b.empty:
                raise InvalidExperimentError('Every log-rank stratum must contain both groups')
            u, v = logrank_score(a, b)
            score += u
            variance += v
            n_strata += 1
        a = selected.loc[selected.treatment.eq(comparison.group_labels[0])]
        b = selected.loc[selected.treatment.eq(comparison.group_labels[1])]
        estimable = variance > 0
        statistic = score * score / variance if estimable else np.nan
        rows.append(dict(comparison=comparison.name, group_a=comparison.group_labels[0],
                         group_b=comparison.group_labels[1], n_a=len(a), n_b=len(b),
                         deaths_a=int(a.E.sum()), deaths_b=int(b.E.sum()),
                         censored_a=int(a.E.eq(0).sum()), censored_b=int(b.E.eq(0).sum()),
                         strata=n_strata, observed_minus_expected_a=score, variance=variance,
                         chi_square=statistic, df=1, p_raw=float(chi2.sf(statistic, 1)),
                         status='ok' if estimable else 'not_estimable_zero_variance'))
    result = pd.DataFrame(rows)
    # Unestimable tests remain in the planned family with p=1 for adjustment;
    # their reported p-values remain missing, never falsely "non-significant".
    result['p_holm'] = holm_adjust(result.p_raw.fillna(1))
    invalid = result.status.ne('ok')
    result.loc[invalid, 'p_holm'] = np.nan
    result['significant_0_05'] = result.p_holm.lt(.05).astype('boolean')
    result.loc[invalid, 'significant_0_05'] = pd.NA
    result['correction'] = 'Holm'
    result['family_size'] = len(comparisons)
    return result
