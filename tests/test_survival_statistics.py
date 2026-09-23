import unittest
import numpy as np
import pandas as pd
from scipy.stats import CensoredData, logrank
from ethoscopy_mcp.survival_statistics import logrank_score, holm_adjust, compare_survival
from ethoscopy_mcp.schemas import LogRankComparison
from ethoscopy_mcp.errors import InvalidExperimentError


class SurvivalStatisticsTests(unittest.TestCase):
    def test_scores_match_scipy_with_ties_and_censoring(self):
        rng = np.random.default_rng(12)
        for _ in range(20):
            a = pd.DataFrame({'T': rng.integers(0, 8, 20), 'E': rng.integers(0, 2, 20)})
            b = pd.DataFrame({'T': rng.integers(0, 8, 20), 'E': rng.integers(0, 2, 20)})
            u, v = logrank_score(a, b)
            def censored(g):
                return CensoredData(uncensored=g.loc[g.E.eq(1),'T'], right=g.loc[g.E.eq(0),'T'])
            self.assertAlmostEqual(u / np.sqrt(v), logrank(censored(a), censored(b)).statistic)

    def test_holm_known_example(self):
        np.testing.assert_allclose(holm_adjust([.01,.04,.03,.2]), [.04,.09,.09,.2])

    def test_stratification_and_unestimable_family(self):
        frame = pd.DataFrame({'id':range(8), 'T':[1,2,3,4]*2, 'E':[1,1,0,0]*2,
                              'treatment':['a','b','a','b']*2, 'temperature':[25]*4+[29]*4})
        comparisons = [LogRankComparison(name='stratified',group_labels=('a','b'),strata_columns=('temperature',)),
                       LogRankComparison(name='single',group_labels=('a','b'),filters={'temperature':25})]
        result = compare_survival(frame, comparisons)
        self.assertAlmostEqual(result.iloc[0].chi_square, 2*result.iloc[1].chi_square)
        frame['E'] = 0
        result = compare_survival(frame, comparisons)
        self.assertTrue(result.p_holm.isna().all())
        self.assertTrue(result.significant_0_05.isna().all())
        frame.loc[frame.temperature.eq(25),'treatment'] = 'a'
        with self.assertRaises(InvalidExperimentError):
            compare_survival(frame, comparisons)
