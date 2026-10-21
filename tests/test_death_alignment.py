import unittest

import numpy as np
import pandas as pd

from ethoscopy_mcp import align_to_death


class DeathAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame(dict(id=['a'] * 4 + ['b'], t=[3600, 7200, 10800, 14400, 7200],
                                      asleep=[True, False, True, False, True]))
        self.events = pd.DataFrame(dict(id=['a', 'b'], E=[1, 0], T=[2, 3],
            first_sample_aligned_hours=[1, 1], time_unit=['hours'] * 2,
            time_basis=['elapsed_from_first_retained_sample'] * 2))

    def test_mcp_offset_censoring_bounds_and_immutability(self):
        before = self.data.copy(deep=True)
        endpoints = self.events.copy(deep=True)
        out = align_to_death(self.data.set_index('id'), self.events, (-2, 0))
        self.assertEqual(out.t.tolist(), [3600, 7200])
        self.assertEqual(out.time_to_death_hours.tolist(), [-2, -1])
        self.assertEqual(out.asleep.tolist(), [True, False])
        pd.testing.assert_frame_equal(self.data, before)
        pd.testing.assert_frame_equal(self.events, endpoints)

    def test_explicit_anchor_and_all_censored(self):
        explicit = self.events[['id', 'E']].assign(anchor_seconds=10800)
        pd.testing.assert_frame_equal(align_to_death(self.data, explicit), align_to_death(self.data, self.events))
        explicit['E'] = 0
        self.assertTrue(align_to_death(self.data, explicit).empty)

    def test_rejects_ambiguous_or_invalid_endpoints(self):
        invalid = [pd.concat([self.events, self.events.iloc[:1]]),
                   self.events.assign(E=2), self.events.assign(time_unit='days'),
                   self.events.drop(columns='time_basis'), self.events.assign(T=np.nan),
                   self.events.iloc[:1]]
        for events in invalid:
            with self.subTest(events=events), self.assertRaises(ValueError):
                align_to_death(self.data, events)

    def test_rejects_invalid_window_and_time(self):
        for window in [(0, -1), (-1, 1), (-np.inf, 0), (-1,)]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                align_to_death(self.data, self.events, window)
        with self.assertRaises(ValueError):
            align_to_death(self.data.assign(t=np.nan), self.events)

    def test_death_at_first_observation_has_no_predeath_window(self):
        endpoints = self.events.copy()
        endpoints.loc[endpoints.id.eq('a'), 'T'] = 0
        self.assertTrue(align_to_death(self.data, endpoints).empty)


if __name__ == '__main__':
    unittest.main()
