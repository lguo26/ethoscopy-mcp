import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import ethoscopy as etho
import matplotlib.pyplot as plt
from ethoscopy_mcp.user_km import UserKMBackend
from ethoscopy_mcp.errors import InvalidExperimentError


def data(hours=30, nan=False):
    sid='2026-10-21_12-00-00_074abc|01'
    t=np.arange(0,hours*3600,10)
    values=np.zeros(len(t))
    if nan:values[0]=np.nan
    frame=pd.DataFrame({'t':t,'moving':values,'walk':values},index=pd.Index([sid]*len(t),name='id'))
    meta=pd.DataFrame({'species':['infected'],'machine_name':['ETHOSCOPE_074'],'region_id':[1]},index=pd.Index([sid],name='id'))
    return etho.behavpy(frame,meta,check=True)


class UserKMTests(unittest.TestCase):
    def test_short_tail_is_censored_without_native_detector(self):
        frame=data(6);before=pd.DataFrame(frame).copy()
        b=UserKMBackend(frame)
        with patch.object(type(frame),'survival_table',side_effect=AssertionError('wrong backend')):
            self.assertTrue(b.death_table(zero_run_hours=12,second_mov_column='walk').empty)
            self.assertEqual(b.full_table(zero_run_hours=12,second_mov_column='walk').E.tolist(),[0])
        pd.testing.assert_frame_equal(pd.DataFrame(frame),before)

    def test_nan_semantics_and_review_candidate_match(self):
        frame=data(30,nan=True);b=UserKMBackend(frame)
        table=b.death_table(zero_run_hours=None,second_mov_column=None)
        self.assertEqual(table['T'].tolist(),[1.])
        self.assertEqual(b.window_candidate(frame.t.to_numpy(),frame.moving.to_numpy(),24,24,.01),3600.)

    def test_death_identity_export_and_plot_share_detector(self):
        b=UserKMBackend(data())
        dead=b.death_table(zero_run_hours=12,second_mov_column='walk')
        full=b.full_table(zero_run_hours=12,second_mov_column='walk')
        self.assertEqual(dead.id.tolist(),full.id.tolist())
        self.assertEqual(full.machine_name.tolist(),['ETHOSCOPE_074'])
        self.assertEqual(dead['T'].tolist(),[0.])
        fig=b.km_survival_plot(zero_run_hours=12,second_mov_column='walk',facet_col='species',facet_arg=['infected'],facet_labels=['infected'])
        self.assertEqual(fig.axes[0].lines[0].get_ydata().tolist(),[1.,0.])
        plt.close(fig)

    def test_rejects_gaps_instead_of_silently_using_legacy_gap_rule(self):
        frame=data();frame=frame.iloc[np.r_[0:100,101:len(frame)]].copy()
        with self.assertRaisesRegex(InvalidExperimentError,'continuous 10-second'):
            UserKMBackend(frame)
