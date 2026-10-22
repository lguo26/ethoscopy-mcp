import unittest
import json
import tempfile
from pathlib import Path
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
    def test_detector_names_preserve_identity_and_execute_same_backend(self):
        from ethoscopy_mcp import EthoscopyService, Settings, ExperimentManifest
        from ethoscopy_mcp.schemas import SurvivalRecipe
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame = data(6)
            frame.meta['date'] = '2026-10-21'
            frame.meta['baseline'] = 0
            source = root / 'source.pkl'
            frame.to_pickle(source)
            mapping = frame.meta.reset_index().rename(columns={'id': 'original_id'})
            mapping['analysis_id'] = mapping.original_id
            mapping['canonical_machine'] = mapping.machine_name
            mapping['roi'] = mapping.region_id
            mapping.to_csv(root / 'identity.csv', index=False)
            (root / 'runs').mkdir()
            service = EthoscopyService(Settings.create([root], artifact_root=root / 'runs'))
            manifest = ExperimentManifest(experiment_id='alias', source_paths=(source,))
            tables, hashes = [], []
            for name in ('km_surival', 'user_km_76e23fd'):
                recipe = SurvivalRecipe.model_validate(dict(
                    recipe_id='alias', experiment_id='alias', cohort_filters={},
                    group={'column': 'species', 'levels': [{'value': 'infected', 'label': 'infected'}]},
                    identity_overlay={'mapping_path': str(root / 'identity.csv'),
                                      'expected_dates': ['2026-10-21'], 'consistency_columns': ['species']},
                    baseline_alignment={},
                    time_alignment={'source_basis': 'stored t', 'output_basis': 'elapsed', 'subtract_hours': 0},
                    death_detection={'backend': name}, review_diagnostics=True,
                    output_requests=[{'artifact_type': 'table', 'dataset': 'individuals',
                                      'format': 'csv', 'name': 'individuals'}]))
                self.assertEqual(recipe.model_dump()['death_detection']['backend'], name)
                preview = service.preview_analysis(manifest, recipe)
                self.assertTrue(preview.ready_to_approve)
                self.assertIn('user_km_backend', {w.code for w in preview.warnings})
                result = service.run_analysis(manifest, recipe, preview.recipe_hash)
                provenance = json.loads(result.provenance_path.read_text())
                self.assertEqual(provenance['survival_backend'], name)
                self.assertEqual(provenance['user_km_source_commit'],
                                 '76e23fdd6c904eefc856ab5c7103a1a9bda0ba43')
                table = pd.read_csv(next(a.path for a in result.artifacts if a.name == 'individuals'))
                self.assertEqual(table.E.tolist(), [0])  # Six-hour tail must stay censored.
                tables.append(table)
                hashes.append(preview.recipe_hash)
            pd.testing.assert_frame_equal(tables[0], tables[1])
            self.assertNotEqual(hashes[0], hashes[1])  # Preserve the exact submitted recipe.

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
