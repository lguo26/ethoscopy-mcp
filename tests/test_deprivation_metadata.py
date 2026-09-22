from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from pydantic import ValidationError

from ethoscopy_mcp.schemas import SleepDeprivationQC, DeprivationMetadata, NotebookSleepRecipe
from ethoscopy_mcp.deprivation import resolve_windows
from ethoscopy_mcp.errors import InvalidExperimentError
from test_notebook_sleep import fixture


class DeprivationMetadataTests(unittest.TestCase):
    def test_no_implicit_48_to_72_fallback(self):
        self.assertIsNone(SleepDeprivationQC(target_group_label='sleep deprived').window)
        with tempfile.TemporaryDirectory() as directory:
            service,manifest,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived')})
            with self.assertRaisesRegex(InvalidExperimentError,'No deprivation schedule'):
                service.preview_analysis(manifest,recipe)

    def test_clock_schedule_origin_baseline_and_day_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            _,_,recipe=fixture(Path(directory))
            qc=SleepDeprivationQC(target_group_label='sleep deprived',metadata=DeprivationMetadata(reference_hour=9))
            recipe=recipe.model_copy(update={'deprivation_qc':qc})
            mapping=pd.DataFrame({'subject_id':['fly'],'date':['2025-03-04'],'time':['18-02-08'],
                'baseline':[0],'stimulus_range':['2025-03-06 09:00:00  2025-03-07 09:00:00']})
            out=resolve_windows(mapping,['fly'],recipe)
            np.testing.assert_allclose(out[['qc_start_hours','qc_end_hours']].iloc[0],[48,72])
            mapping['time']='08-00-00'
            out=resolve_windows(mapping,['fly'],recipe)
            np.testing.assert_allclose(out[['qc_start_hours','qc_end_hours']].iloc[0],[72,96])
            mapping['baseline']=2
            out=resolve_windows(mapping,['fly'],recipe)
            np.testing.assert_allclose(out[['qc_start_hours','qc_end_hours']].iloc[0],[120,144])

    def test_source_metadata_windows_override_explicit_fallback_per_machine(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service,manifest,recipe=fixture(root)
            frame=pd.read_pickle(manifest.source_paths[0])
            frame.meta['time']='09-00-00'
            frame.meta['date']='2025-06-04'
            frame.meta['stimulus_range']=None
            frame.meta.loc['c','stimulus_range']='2025-06-04 10:00:00  2025-06-04 11:00:00'
            frame.meta.loc['d','stimulus_range']='2025-06-04 11:00:00  2025-06-04 12:00:00'
            frame.loc[(frame.index=='d') & frame.t.between(7200,10799),'asleep']=False
            frame.to_pickle(manifest.source_paths[0])
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',
                window={'start_hours':48,'end_hours':72},metadata={'reference_hour':9})})
            preview=service.preview_analysis(manifest,recipe)
            self.assertEqual({(x.start_hours,x.end_hours,x.animals) for x in preview.deprivation_windows},{(1,2,1),(2,3,1)})
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            audit=pd.read_csv(result.run_directory/'exclusions.csv')
            self.assertEqual(int(audit.excluded.sum()),0)
            self.assertTrue(audit.loc[audit.group.eq('control'),'qc_start_hours'].isna().all())
            self.assertTrue(audit.loc[audit.group.eq('sleep deprived'),'qc_window_source'].eq('metadata:stimulus_range').all())

    def test_acquisition_metadata_csv_and_hash_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            service,manifest,recipe=fixture(root)
            frame=pd.read_pickle(manifest.source_paths[0]);frame.meta['date']='2025-06-04';frame.meta['time']='09-00-00'
            frame.to_pickle(manifest.source_paths[0])
            source=root/'ethoscope_metadata.csv'
            schedule=pd.DataFrame({'machine_name':['M3','M4'],'date_time':['2025-06-04 09:00:00']*2,
                'stimulus_range':['2025-06-04 10:00:00  2025-06-04 11:00:00']*2})
            schedule.to_csv(source,index=False)
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',metadata={'path':source,'reference_hour':9})})
            preview=service.preview_analysis(manifest,recipe)
            self.assertEqual(len(preview.auxiliary_sources),1)
            self.assertIn('acquisition_csv=',preview.deprivation_windows[0].source)
            result=service.run_analysis(manifest,recipe,preview.recipe_hash)
            self.assertTrue(result.provenance_path.is_file())
            schedule.loc[1,'stimulus_range']='2025-06-04 11:00:00  2025-06-04 12:00:00'
            schedule.to_csv(source,index=False)
            with self.assertRaisesRegex(InvalidExperimentError,'hash'):
                service.run_analysis(manifest,recipe,preview.recipe_hash)

    def test_legacy_date_range_is_opt_in_not_acquisition_range(self):
        with tempfile.TemporaryDirectory() as directory:
            _,_,recipe=fixture(Path(directory))
            mapping=pd.DataFrame({'subject_id':['fly'],'date':['2025-03-04'],'time':['18-00-00'],'baseline':[0],
                'date_range':['2025-03-06 09:00:00  2025-03-07 09:00:00']})
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',metadata={'reference_hour':9})})
            with self.assertRaisesRegex(InvalidExperimentError,'No deprivation schedule'):
                resolve_windows(mapping,['fly'],recipe)
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',metadata={'reference_hour':9,'range_columns':['date_range']})})
            self.assertEqual(resolve_windows(mapping,['fly'],recipe).iloc[0].qc_start_hours,48)

    def test_invalid_conflicting_and_ambiguous_schedules_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            _,_,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',metadata={'reference_hour':9})})
            base={'subject_id':['fly'],'date':['2025-03-04'],'time':['18-00-00'],'baseline':[0],
                  'stimulus_range':['2025-03-06 09:00:00  2025-03-07 09:00:00']}
            for value in ['bad','2025-03-07 09:00:00  2025-03-06 09:00:00','2025-03-06 09:00:00  2025-03-07 09:00:00;2025-03-08 09:00:00  2025-03-09 09:00:00']:
                with self.subTest(value=value),self.assertRaises(InvalidExperimentError):
                    resolve_windows(pd.DataFrame({**base,'stimulus_range':[value]}),['fly'],recipe)
            with self.assertRaisesRegex(InvalidExperimentError,'Conflicting'):
                resolve_windows(pd.DataFrame({**base,'deprivation_start_hours':[1],'deprivation_end_hours':[2]}),['fly'],recipe)
            with self.assertRaisesRegex(InvalidExperimentError,'reference_hour'):
                resolve_windows(pd.DataFrame(base),['fly'],recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived')}))

    def test_explicit_zt0_and_timezone_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            _,_,recipe=fixture(Path(directory))
            recipe=recipe.model_copy(update={'deprivation_qc':SleepDeprivationQC(target_group_label='sleep deprived',metadata={'timezone':'Europe/London'})})
            mapping=pd.DataFrame({'subject_id':['fly'],'baseline':[0],'zt0':['2025-03-29 09:00:00'],
                'stimulus_range':['2025-03-30 09:00:00  2025-03-31 09:00:00']})
            out=resolve_windows(mapping,['fly'],recipe)
            np.testing.assert_allclose(out[['qc_start_hours','qc_end_hours']].iloc[0],[23,47])
