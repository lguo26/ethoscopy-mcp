from pathlib import Path
import tempfile
import unittest
import pandas as pd
import matplotlib.pyplot as plt

from ethoscopy_mcp import EthoscopyService, ExperimentManifest, Settings
from ethoscopy_mcp.execution import _run_recipe
from ethoscopy_mcp.errors import InvalidExperimentError
from ethoscopy_mcp.survival_review import read_endpoints
from test_preview import _write_transfer_fixture, _survival_recipe


class SurvivalReviewTests(unittest.TestCase):
    def test_overrides_reference_hash_and_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second, mapping = _write_transfer_fixture(root)
            (root/'runs').mkdir()
            service = EthoscopyService(Settings.create([root], artifact_root=root/'runs'))
            recipe = _survival_recipe(mapping).model_copy(update={'review_diagnostics': True})
            manifest = ExperimentManifest(experiment_id=recipe.experiment_id, source_paths=(first, second))
            preview = service.preview_analysis(manifest, recipe)
            table, figure = _run_recipe(preview, recipe)
            evidence = table.attrs['review_reports']['survival_review.csv']
            subject = evidence.iloc[0]
            plt.close(figure)
            endpoints = root/'review.csv'
            pd.DataFrame([dict(canonical_machine=subject.canonical_machine, roi=subject.roi,
                time_hours=0, event=0, time_basis='elapsed', reason='escaped; reviewed')]).to_csv(endpoints, index=False)
            reviewed = recipe.model_copy(update={'reviewed_endpoints_path': endpoints, 'reference_endpoints_path': endpoints})
            approved = service.preview_analysis(manifest, reviewed)
            self.assertEqual(len(approved.auxiliary_sources), 2)
            result = service.run_analysis(manifest, reviewed, approved.recipe_hash)
            report_path = next(a.path for a in result.artifacts if a.name=='survival_review.csv')
            report = pd.read_csv(report_path)
            self.assertEqual(report.reviewed.sum(), 1)
            chosen = report.loc[report.reviewed].iloc[0]
            self.assertEqual(chosen['T'], 0)
            self.assertEqual(chosen.E, 0)
            self.assertEqual(chosen.selected_minus_reference_hours, 0)
            self.assertAlmostEqual(chosen.original_T, subject.original_T)
            self.assertEqual(sum(g.animals for g in result.group_outcomes), 4)
            self.assertEqual(sum(g.detected_deaths for g in result.group_outcomes), int(report.E.sum()))
            text = endpoints.read_text();endpoints.write_text(text.replace('escaped; reviewed', 'new review reason'))
            changed = service.preview_analysis(manifest, reviewed)
            self.assertNotEqual(approved.recipe_hash, changed.recipe_hash)
            with self.assertRaises(InvalidExperimentError):
                service.run_analysis(manifest, reviewed, approved.recipe_hash)

    def test_invalid_review_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'review.csv'
            mapping = pd.DataFrame([dict(canonical_machine='A',roi='01')])
            base = dict(canonical_machine='A',roi='1',time_hours=1,event=1,time_basis='elapsed',reason='review')
            for change in [dict(event=2),dict(time_hours=float('nan')),dict(time_hours=-1),
                           dict(time_basis='days'),dict(reason=' '),dict(canonical_machine='B')]:
                pd.DataFrame([{**base,**change}]).to_csv(path,index=False)
                with self.assertRaises(InvalidExperimentError):read_endpoints(path,mapping,reviewed=True)
            pd.DataFrame([base,base]).to_csv(path,index=False)
            with self.assertRaises(InvalidExperimentError):read_endpoints(path,mapping,reviewed=True)

    def test_restart_evidence_preserves_default_and_validates_bounds(self):
        import ethoscopy as etho
        import numpy as np
        from ethoscopy_mcp.survival_review import review_survival
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = pd.DataFrame([dict(id='a', machine_name='M', region_id=1, species='PBS')]).set_index('id')
            times = np.r_[np.arange(0, 600, 10), np.arange(7200, 12000, 10)]
            frame = pd.DataFrame(dict(id='a', t=times, moving=times>=7200, walk=times>=7200)).set_index('id')
            working = etho.behavpy(frame, meta, check=True)
            recipe = _survival_recipe(root/'unused.csv').model_copy(update={'review_diagnostics':True})
            settings=dict(mov_column='moving',second_mov_column='walk',time_window=24,prop_immobile=.01,zero_run_hours=12)
            original=working.km_death_table(**settings,subject_cols=['machine_name','region_id'],meta_cols=['species']).rename(columns={'species':'treatment'})
            fig=plt.figure()
            table,fig,reports=review_survival(working,recipe,settings,original,fig)
            pd.testing.assert_frame_equal(table,original)
            evidence=reports['survival_review.csv'].iloc[0]
            self.assertEqual(evidence.original_T,0)
            self.assertGreater(evidence.post_restart_moving_samples,0)
            self.assertEqual(evidence.warning,'movement_after_restart_requires_review')
            self.assertLess(reports['survival_candidates.csv'].observed_window_span_hours.max(),1)
            path=root/'override.csv'
            pd.DataFrame([dict(canonical_machine='M',roi=1,time_hours=999,event=1,time_basis='elapsed',reason='invalid')]).to_csv(path,index=False)
            bad=recipe.model_copy(update={'reviewed_endpoints_path':path})
            with self.assertRaises(InvalidExperimentError):review_survival(working,bad,settings,original,fig)
            pd.DataFrame([dict(canonical_machine='M',roi=1,time_hours=2,event=0,time_basis='aligned',reason='escape')]).to_csv(path,index=False)
            table,fig,reports=review_survival(working,bad,settings,original,fig)
            self.assertTrue(table.empty)
            self.assertEqual(reports['survival_review.csv'].iloc[0]['T'],2)
            self.assertTrue(all(v==1 for v in fig.axes[0].lines[0].get_ydata()))
            plt.close(fig)
